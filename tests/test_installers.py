from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    ROOT / "deploy/macos/install.sh", ROOT / "deploy/macos/uninstall.sh",
    ROOT / "deploy/macos/ai.wechat-codex-bridge.plist.template",
    ROOT / "deploy/windows/Install-WeChatCodexBridge.ps1",
    ROOT / "deploy/windows/Uninstall-WeChatCodexBridge.ps1",
    ROOT / "deploy/linux/install.sh", ROOT / "deploy/linux/uninstall.sh",
    ROOT / "deploy/linux/wechat-codex-bridge.service.template",
]


class InstallerContractTests(unittest.TestCase):
    def test_all_platform_assets_exist(self):
        self.assertEqual([str(path.relative_to(ROOT)) for path in ASSETS if not path.is_file()], [])

    def test_installers_manage_only_the_codex_bridge(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in ASSETS).lower()
        self.assertIn("wechat-codex-bridge", combined)
        for protected in ("docker restart", "docker rm", "launchctl.*openclaw", "systemctl.*dify"):
            self.assertNotIn(protected, combined)

    def test_windows_uses_current_user_acl_and_task(self):
        body = ASSETS[3].read_text(encoding="utf-8")
        self.assertIn("icacls", body.lower())
        self.assertIn("New-ScheduledTaskPrincipal", body)
        self.assertIn("$env:USERNAME", body)
        self.assertNotIn("SYSTEM", body)

    def test_linux_uses_user_systemd_and_no_wildcard_bind(self):
        body = ASSETS[5].read_text(encoding="utf-8") + ASSETS[7].read_text(encoding="utf-8")
        self.assertIn("systemctl --user", body)
        self.assertNotIn("0.0.0.0", body)
        self.assertIn("__BIND_HOST__", body)

    def test_uninstallers_preserve_private_state_and_releases(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in (ASSETS[1], ASSETS[4], ASSETS[6]))
        for term in ("recovery", "token", "state", "releases"):
            self.assertIn(term, combined)


if __name__ == "__main__":
    unittest.main()
