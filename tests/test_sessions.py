from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path


class CodexSessionCatalogTests(unittest.TestCase):
    def test_persists_hashed_scope_with_owner_only_permissions(self):
        from wechat_codex_bridge.sessions import SessionCatalog, SessionIdentity

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            path = root / "sessions.json"
            identity = SessionIdentity.create(
                scope="wechat-private-scope",
                workspace=workspace,
                policy_fingerprint="read-only-current-user-v1",
            )
            SessionCatalog(path).upsert_active(identity, "thread-1")

            raw = path.read_text(encoding="utf-8")
            entry = SessionCatalog(path).active_for(identity)
            mode = stat.S_IMODE(path.stat().st_mode)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.thread_id, "thread-1")
        self.assertNotIn("wechat-private-scope", raw)
        if os.name != "nt":
            self.assertEqual(mode, 0o600)

    def test_scope_workspace_and_policy_must_all_match(self):
        from wechat_codex_bridge.sessions import SessionCatalog, SessionIdentity

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            other = root / "other"
            workspace.mkdir()
            other.mkdir()
            path = root / "sessions.json"
            catalog = SessionCatalog(path)
            original = SessionIdentity.create("scope-1", workspace, "policy-1")
            catalog.upsert_active(original, "thread-1")

            self.assertIsNone(catalog.active_for(SessionIdentity.create("scope-2", workspace, "policy-1")))
            self.assertIsNone(catalog.active_for(SessionIdentity.create("scope-1", other, "policy-1")))
            self.assertIsNone(catalog.active_for(SessionIdentity.create("scope-1", workspace, "policy-2")))

    def test_archive_prevents_resume_and_preserves_entry(self):
        from wechat_codex_bridge.sessions import SessionCatalog, SessionIdentity

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            catalog = SessionCatalog(root / "sessions.json")
            identity = SessionIdentity.create("scope", workspace, "policy")
            catalog.upsert_active(identity, "thread-1")
            self.assertTrue(catalog.archive_active(identity))

            self.assertIsNone(catalog.active_for(identity))
            payload = json.loads((root / "sessions.json").read_text(encoding="utf-8"))

        self.assertEqual(payload[0]["status"], "archived")

    def test_corrupt_catalog_fails_closed_to_fresh_session(self):
        from wechat_codex_bridge.sessions import SessionCatalog, SessionIdentity

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            path = root / "sessions.json"
            path.write_text("not-json", encoding="utf-8")
            identity = SessionIdentity.create("scope", workspace, "policy")

            self.assertIsNone(SessionCatalog(path).active_for(identity))

    @unittest.skipIf(os.name == "nt", "symlink creation is not guaranteed for normal Windows users")
    def test_symlink_catalog_is_rejected(self):
        from wechat_codex_bridge.sessions import SessionCatalog, SessionCatalogError

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.json"
            target.write_text("[]", encoding="utf-8")
            link = root / "sessions.json"
            os.symlink(target, link)

            with self.assertRaisesRegex(SessionCatalogError, "session_catalog_unsafe"):
                SessionCatalog(link)

    def test_gc_bounds_entries(self):
        from wechat_codex_bridge.sessions import SessionCatalog, SessionIdentity

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            catalog = SessionCatalog(root / "sessions.json", max_entries=2)
            for index in range(3):
                catalog.upsert_active(
                    SessionIdentity.create(f"scope-{index}", workspace, "policy"),
                    f"thread-{index}",
                    updated_at=index + 1,
                )

            payload = json.loads((root / "sessions.json").read_text(encoding="utf-8"))

        self.assertEqual(len(payload), 2)
        self.assertEqual({entry["thread_id"] for entry in payload}, {"thread-1", "thread-2"})


if __name__ == "__main__":
    unittest.main()
