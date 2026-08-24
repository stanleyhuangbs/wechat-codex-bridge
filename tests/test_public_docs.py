from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicDocsTests(unittest.TestCase):
    def test_required_docs_exist(self):
        required = ["README.md", "SECURITY.md", "docs/architecture.md", "docs/installation.md", "docs/verification.md", "docs/rollback.md"]
        self.assertEqual([name for name in required if not (ROOT / name).is_file()], [])

    def test_readme_names_required_robot_and_optional_artifact_bridge(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("stanleyhuangbs/wechat-robot-client-local", text)
        self.assertIn("stanleyhuangbs/wechat-agent-bridge", text)
        self.assertRegex(text.lower(), r"optional|可选")
        self.assertIn("wechat-agent-bridge` 不是必装", text)

    def test_verification_matrix_does_not_overclaim_ci(self):
        text = (ROOT / "docs/verification.md").read_text(encoding="utf-8")
        for label in ("Contract-tested", "Host-verified", "Docker-verified", "WeChat-verified"):
            self.assertIn(label, text)
        self.assertIn("CI 不等于真实 Codex 登录", text)

    def test_relative_markdown_links_resolve(self):
        missing = []
        for document in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]:
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                clean = target.split("#", 1)[0]
                if clean and not (document.parent / clean).resolve().exists():
                    missing.append(f"{document.name}:{target}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
