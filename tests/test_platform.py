from __future__ import annotations

import stat
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class PlatformContractTests(unittest.TestCase):
    def test_discovers_explicit_absolute_codex(self):
        from wechat_codex_bridge.platform import discover_codex

        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "codex"
            executable.write_text("stub", encoding="utf-8")
            executable.chmod(0o700)

            self.assertEqual(discover_codex(executable), executable.resolve())

    def test_missing_codex_fails_with_stable_error(self):
        from wechat_codex_bridge.platform import PlatformError, discover_codex

        with patch("wechat_codex_bridge.platform.shutil.which", return_value=None):
            with self.assertRaisesRegex(PlatformError, "codex_executable_unavailable"):
                discover_codex()

    def test_rejects_public_or_nonlocal_bind_addresses(self):
        from wechat_codex_bridge.platform import is_safe_bind_host

        local = {"127.0.0.1", "172.19.0.1", "0.0.0.0"}
        self.assertTrue(is_safe_bind_host("127.0.0.1", local_addresses=local))
        self.assertTrue(is_safe_bind_host("172.19.0.1", local_addresses=local))
        self.assertFalse(is_safe_bind_host("0.0.0.0", local_addresses=local))
        self.assertFalse(is_safe_bind_host("::", local_addresses={"::"}))
        self.assertFalse(is_safe_bind_host("192.0.2.10", local_addresses=local))

    @patch("wechat_codex_bridge.platform.os.name", "nt")
    def test_windows_private_file_policy_uses_acl_not_posix_mode(self):
        from wechat_codex_bridge.platform import private_file_policy

        self.assertEqual(private_file_policy().kind, "windows-acl")

    @unittest.skipIf(os.name == "nt", "POSIX mode bits do not represent Windows ACLs")
    def test_private_text_is_atomic_and_owner_only_on_posix(self):
        from wechat_codex_bridge.platform import write_private_text

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private" / "token.txt"
            write_private_text(path, "first")
            write_private_text(path, "second")

            self.assertEqual(path.read_text(encoding="utf-8"), "second")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*")), [])


if __name__ == "__main__":
    unittest.main()
