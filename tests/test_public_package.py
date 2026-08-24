from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicPackageTests(unittest.TestCase):
    def test_public_tree_has_no_private_runtime_artifacts(self):
        forbidden = {"token", "sessions.json", "auth.json", "settings.json", "stdout.log", "stderr.log"}
        self.assertEqual([str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.name in forbidden], [])

    def test_workflow_runs_all_three_operating_systems(self):
        text = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
        for image in ("ubuntu-latest", "macos-latest", "windows-latest"):
            self.assertIn(image, text)
        for command in ("unittest discover", "compileall", "pip wheel", "check_public_package.py"):
            self.assertIn(command, text)

    def test_scanner_exists(self):
        self.assertTrue((ROOT / "tools/check_public_package.py").is_file())


if __name__ == "__main__":
    unittest.main()
