from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class CurrentUserCodexRunnerTests(unittest.TestCase):
    def _fake_codex(self, root: Path, *, mode: str = "ok") -> tuple[Path, Path]:
        capture = root / "capture.jsonl"
        python_script = root / "fake-codex.py"
        source = f'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

capture = Path({str(capture)!r})
record = {{
    "argv": sys.argv[1:],
    "stdin": sys.stdin.read(),
    "home": os.environ.get("HOME"),
    "codex_home": os.environ.get("CODEX_HOME"),
    "bridge_secret": os.environ.get("WECHAT_CODEX_BRIDGE_TOKEN"),
    "image_exists": [Path(value).is_file() for index, value in enumerate(sys.argv) if index > 0 and sys.argv[index - 1] == "--image"],
    "image_paths": [value for index, value in enumerate(sys.argv) if index > 0 and sys.argv[index - 1] == "--image"],
}}
with capture.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False) + "\\n")
mode = {mode!r}
if mode == "timeout":
    time.sleep(5)
elif mode == "error":
    print("private stderr", file=sys.stderr)
    raise SystemExit(7)
elif "resume" in sys.argv and mode == "missing-on-resume":
    print("thread not found", file=sys.stderr)
    raise SystemExit(1)
else:
    if "resume" not in sys.argv:
        print(json.dumps({{"type": "thread.started", "thread_id": "thread-new"}}))
    print(json.dumps({{"type": "agent_message", "message": "Codex 当前账号回复"}}))
    print(json.dumps({{"type": "turn.completed"}}))
'''
        python_script.write_text(source, encoding="utf-8")
        if os.name == "nt":
            script = root / "fake-codex.cmd"
            script.write_text(
                f'@"{sys.executable}" "{python_script}" %*\n', encoding="utf-8"
            )
        else:
            script = root / "fake-codex"
            script.write_text(f"#!{sys.executable}\n" + source.split("\n", 1)[1], encoding="utf-8")
            script.chmod(0o700)
        return script, capture

    def _runner(self, root: Path, executable: Path, **kwargs):
        from wechat_codex_bridge.runner import CurrentUserCodexRunner

        workspace = root / "workspace"
        state = root / "state"
        workspace.mkdir(mode=0o700)
        return CurrentUserCodexRunner(
            executable=executable,
            workspace=workspace,
            state_dir=state,
            environment={
                "HOME": "/private-test-home",
                "CODEX_HOME": "/private-test-home/.codex",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8",
                "WECHAT_CODEX_BRIDGE_TOKEN": "must-not-reach-codex",
            },
            **kwargs,
        )

    def test_fresh_and_resume_commands_are_platform_neutral(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, _ = self._fake_codex(root)
            runner = self._runner(root, executable)

            fresh = runner.command(thread_id=None, image_paths=[])
            resumed = runner.command(thread_id="thread-1", image_paths=[])

        self.assertEqual(fresh[0], str(runner.executable))
        self.assertEqual(fresh[1:3], ["exec", "--json"])
        self.assertIn("resume", resumed)
        self.assertNotIn("--ephemeral", fresh + resumed)

    def test_subprocess_transport_is_explicit_utf8(self):
        from subprocess import CompletedProcess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, _ = self._fake_codex(root)
            runner = self._runner(root, executable)
            output = "\n".join(
                (
                    json.dumps({"type": "thread.started", "thread_id": "thread-new"}),
                    json.dumps({"type": "agent_message", "message": "中文回复"}, ensure_ascii=False),
                    json.dumps({"type": "turn.completed"}),
                )
            )
            with patch(
                "wechat_codex_bridge.runner.subprocess.run",
                return_value=CompletedProcess([], 0, output, ""),
            ) as invoked:
                reply = runner.run("scope", [{"role": "user", "content": "中文问题"}])

        self.assertEqual(reply.text, "中文回复")
        transport_call = next(
            call for call in invoked.call_args_list if "input" in call.kwargs
        )
        self.assertEqual(transport_call.kwargs["encoding"], "utf-8")
        self.assertEqual(transport_call.kwargs["errors"], "strict")

    @unittest.skipIf(os.name == "nt", "POSIX fake Codex process fixture")
    def test_fresh_then_resume_uses_current_home_and_read_only_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, capture = self._fake_codex(root)
            runner = self._runner(root, executable)

            first = runner.run("wechat-scope", [{"role": "user", "content": "第一问"}])
            second = runner.run("wechat-scope", [{"role": "user", "content": "第二问"}])
            records = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(first.text, "Codex 当前账号回复")
        self.assertFalse(first.resumed)
        self.assertTrue(second.resumed)
        self.assertEqual(records[0]["home"], "/private-test-home")
        self.assertEqual(records[0]["codex_home"], "/private-test-home/.codex")
        self.assertIsNone(records[0]["bridge_secret"])
        self.assertIn("read-only", records[0]["argv"])
        self.assertNotIn("第一问", records[0]["argv"])
        self.assertIn("第一问", records[0]["stdin"])
        self.assertIn("resume", records[1]["argv"])
        self.assertIn("thread-new", records[1]["argv"])

    @unittest.skipIf(os.name == "nt", "POSIX fake Codex process fixture")
    def test_different_scopes_create_independent_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, capture = self._fake_codex(root)
            runner = self._runner(root, executable)
            runner.run("scope-a", [{"role": "user", "content": "A"}])
            runner.run("scope-b", [{"role": "user", "content": "B"}])
            records = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]

        self.assertNotIn("resume", records[0]["argv"])
        self.assertNotIn("resume", records[1]["argv"])

    @unittest.skipIf(os.name == "nt", "POSIX fake Codex process fixture")
    def test_data_url_image_is_private_during_run_and_removed_afterward(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, capture = self._fake_codex(root)
            runner = self._runner(root, executable)
            image = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nsmall").decode()

            runner.run("scope", [{"role": "user", "content": "看图"}], images=[image])
            record = json.loads(capture.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["image_exists"], [True])
            for path in record["image_paths"]:
                self.assertFalse(Path(path).exists())

    @unittest.skipIf(os.name == "nt", "POSIX fake Codex process fixture")
    def test_default_runner_accepts_six_video_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, capture = self._fake_codex(root)
            runner = self._runner(root, executable)
            frame = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nframe").decode()

            runner.run(
                "video-scope",
                [{"role": "user", "content": "理解视频"}],
                images=[frame] * 6,
            )
            record = json.loads(capture.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(len(record["image_paths"]), 6)

    def test_prompt_and_image_limits_fail_closed(self):
        from wechat_codex_bridge.runner import CodexRunnerError

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, _ = self._fake_codex(root)
            runner = self._runner(root, executable, max_prompt_bytes=1024, max_images=0)
            with self.assertRaisesRegex(CodexRunnerError, "codex_prompt_too_large"):
                runner.run("scope", [{"role": "user", "content": "x" * 2000}])
            with self.assertRaisesRegex(CodexRunnerError, "codex_images_invalid"):
                runner.run("scope", [{"role": "user", "content": "x"}], images=["x"])

    @unittest.skipIf(os.name == "nt", "POSIX fake Codex process fixture")
    def test_timeout_and_backend_failure_do_not_expose_details(self):
        from wechat_codex_bridge.runner import CodexRunnerError

        for mode, code in (("timeout", "codex_timeout"), ("error", "codex_unavailable")):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                executable, _ = self._fake_codex(root, mode=mode)
                runner = self._runner(root, executable, timeout=0.1 if mode == "timeout" else 2.0)
                with self.assertRaises(CodexRunnerError) as raised:
                    runner.run("scope", [{"role": "user", "content": "hello"}])
                self.assertEqual(str(raised.exception), code)
                self.assertNotIn("private", str(raised.exception))

    @unittest.skipIf(os.name == "nt", "POSIX fake Codex process fixture")
    def test_missing_resumed_thread_is_archived_and_retried_once_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable, capture = self._fake_codex(root, mode="missing-on-resume")
            runner = self._runner(root, executable)
            runner.run("scope", [{"role": "user", "content": "first"}])
            reply = runner.run("scope", [{"role": "user", "content": "second"}])
            records = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]

        self.assertFalse(reply.resumed)
        self.assertEqual(len(records), 3)
        self.assertIn("resume", records[1]["argv"])
        self.assertNotIn("resume", records[2]["argv"])


if __name__ == "__main__":
    unittest.main()
