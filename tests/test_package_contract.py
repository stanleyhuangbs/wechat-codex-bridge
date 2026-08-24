from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageContractTests(unittest.TestCase):
    def test_standalone_package_identity_and_zero_runtime_dependencies(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["name"], "wechat-codex-bridge")
        self.assertEqual(data["project"]["requires-python"], ">=3.11")
        self.assertEqual(data["project"]["dependencies"], [])
        self.assertEqual(
            data["project"]["scripts"],
            {
                "wechat-codex-bridge": "wechat_codex_bridge.http:main",
                "wechat-codex-bridge-admin": "wechat_codex_bridge.docker_admin:main",
            },
        )

    def test_repository_does_not_package_parent_projects(self):
        names = {
            path.name
            for path in (ROOT / "src").iterdir()
            if path.is_dir()
        }

        self.assertEqual(names, {"wechat_codex_bridge"})


if __name__ == "__main__":
    unittest.main()
