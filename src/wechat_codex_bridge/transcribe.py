"""Optional local Whisper CLI adapter for WeChat voice and video audio."""

from __future__ import annotations

import base64
import binascii
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

from .platform import ensure_private_directory, restrict_private_path


class TranscriptionError(RuntimeError):
    """A stable, non-sensitive transcription failure."""


_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".amr", ".silk"}
_LANGUAGE = re.compile(r"^[A-Za-z-]{2,16}$")
_SAFE_ENV_KEYS = {
    "HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP", "USERPROFILE",
    "LOCALAPPDATA", "APPDATA", "SystemRoot", "PATHEXT", "ComSpec",
    "XDG_CACHE_HOME", "HF_HOME",
}


class WhisperCliTranscriber:
    def __init__(
        self,
        *,
        executable: Path | str | None,
        runtime_dir: Path | str,
        model: str = "small",
        timeout: float = 300.0,
        max_audio_bytes: int = 50 * 1024 * 1024,
        environment: Mapping[str, str] | None = None,
    ):
        candidate = str(executable) if executable is not None else shutil.which("whisper")
        if not candidate:
            raise TranscriptionError("transcription_executable_unavailable")
        try:
            resolved = Path(candidate).expanduser().resolve(strict=True)
        except OSError as exc:
            raise TranscriptionError("transcription_executable_invalid") from exc
        if not resolved.is_file() or (os.name != "nt" and not os.access(resolved, os.X_OK)):
            raise TranscriptionError("transcription_executable_invalid")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", model):
            raise ValueError("transcription_model_invalid")
        self.executable = resolved
        self.runtime_dir = ensure_private_directory(runtime_dir)
        self.model = model
        self.timeout = max(1.0, min(float(timeout), 600.0))
        self.max_audio_bytes = max(1024, min(int(max_audio_bytes), 70 * 1024 * 1024))
        source = os.environ if environment is None else environment
        self.environment = {
            key: str(value) for key, value in source.items()
            if key in _SAFE_ENV_KEYS and value is not None
        }

    def transcribe(self, audio_base64: str, *, filename: str, language: str) -> str:
        if not isinstance(audio_base64, str) or not audio_base64:
            raise TranscriptionError("transcription_audio_invalid")
        suffix = Path(filename if isinstance(filename, str) else "").suffix.lower()
        if suffix not in _AUDIO_EXTENSIONS or not isinstance(language, str) or not _LANGUAGE.fullmatch(language):
            raise TranscriptionError("transcription_audio_invalid")
        try:
            audio = base64.b64decode(audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise TranscriptionError("transcription_audio_invalid") from exc
        if not audio or len(audio) > self.max_audio_bytes:
            raise TranscriptionError("transcription_audio_invalid")

        with tempfile.TemporaryDirectory(prefix="transcribe-", dir=self.runtime_dir) as temporary:
            request_dir = Path(temporary)
            restrict_private_path(request_dir, directory=True)
            audio_path = request_dir / f"audio{suffix}"
            descriptor = os.open(audio_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(audio)
                handle.flush()
                os.fsync(handle.fileno())
            restrict_private_path(audio_path)
            try:
                completed = subprocess.run(
                    [
                        str(self.executable), str(audio_path), "--model", self.model,
                        "--language", language, "--task", "transcribe",
                        "--output_dir", str(request_dir), "--output_format", "txt",
                        "--verbose", "False", "--fp16", "False",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=self.environment,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise TranscriptionError("transcription_timeout") from exc
            except OSError as exc:
                raise TranscriptionError("transcription_unavailable") from exc
            if completed.returncode != 0:
                raise TranscriptionError("transcription_unavailable")
            outputs = list(request_dir.glob("*.txt"))
            if len(outputs) != 1 or outputs[0].stat().st_size > 1024 * 1024:
                raise TranscriptionError("transcription_result_invalid")
            text = outputs[0].read_text(encoding="utf-8").strip()
            if not text:
                raise TranscriptionError("transcription_result_invalid")
            return text
