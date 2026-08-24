from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path


class WhisperTranscriberTests(unittest.TestCase):
    def _fake_whisper(self, root: Path) -> Path:
        python_script = root / "fake-whisper.py"
        python_script.write_text(
            """#!/usr/bin/env python3
from pathlib import Path
import sys
audio = Path(sys.argv[1])
output_dir = Path(sys.argv[sys.argv.index('--output_dir') + 1])
(output_dir / (audio.stem + '.txt')).write_text('转写成功', encoding='utf-8')
""",
            encoding="utf-8",
        )
        if os.name == "nt":
            script = root / "fake-whisper.cmd"
            script.write_text(
                f'@"{sys.executable}" "{python_script}" %*\n', encoding="utf-8"
            )
        else:
            script = root / "fake-whisper"
            script.write_text(
                f"#!{sys.executable}\n" + python_script.read_text(encoding="utf-8").split("\n", 1)[1],
                encoding="utf-8",
            )
            script.chmod(0o700)
        return script

    def test_transcribes_with_private_temporary_file_and_cleans_up(self):
        from wechat_codex_bridge.transcribe import WhisperCliTranscriber

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            transcriber = WhisperCliTranscriber(
                executable=self._fake_whisper(root), runtime_dir=runtime, model="small"
            )
            text = transcriber.transcribe(
                base64.b64encode(b"audio-content").decode(),
                filename="voice.aiff",
                language="zh",
            )

            self.assertEqual(text, "转写成功")
            self.assertEqual(list(runtime.iterdir()), [])

    def test_invalid_audio_and_extension_fail_closed(self):
        from wechat_codex_bridge.transcribe import TranscriptionError, WhisperCliTranscriber

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcriber = WhisperCliTranscriber(
                executable=self._fake_whisper(root), runtime_dir=root / "runtime"
            )
            for audio, filename in (("not-base64!", "voice.wav"), (base64.b64encode(b"x").decode(), "voice.exe")):
                with self.subTest(filename=filename):
                    with self.assertRaisesRegex(TranscriptionError, "transcription_audio_invalid"):
                        transcriber.transcribe(audio, filename=filename, language="zh")


if __name__ == "__main__":
    unittest.main()
