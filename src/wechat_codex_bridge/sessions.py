"""Private, bounded session catalog for persistent Codex threads."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path


class SessionCatalogError(RuntimeError):
    """A stable, non-sensitive catalog failure."""


@dataclass(frozen=True)
class SessionIdentity:
    scope_hash: str
    workspace: str
    policy_fingerprint: str
    key: str

    @classmethod
    def create(
        cls,
        scope: str,
        workspace: Path | str,
        policy_fingerprint: str,
    ) -> "SessionIdentity":
        if not isinstance(scope, str) or not scope.strip() or len(scope) > 256:
            raise ValueError("session_scope_invalid")
        if not isinstance(policy_fingerprint, str) or not policy_fingerprint.strip():
            raise ValueError("session_policy_invalid")
        try:
            workspace_real = str(Path(workspace).resolve(strict=True))
        except OSError as exc:
            raise ValueError("session_workspace_invalid") from exc
        scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        material = "\x1f".join(
            (scope_hash, "codex", workspace_real, policy_fingerprint)
        )
        key = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return cls(scope_hash, workspace_real, policy_fingerprint, key)


@dataclass(frozen=True)
class SessionEntry:
    key: str
    scope_hash: str
    workspace: str
    policy_fingerprint: str
    thread_id: str
    status: str
    updated_at: int


class SessionCatalog:
    def __init__(
        self,
        path: Path | str,
        *,
        max_entries: int = 1000,
        max_bytes: int = 1024 * 1024,
    ):
        self.path = Path(path)
        self.max_entries = max(1, min(int(max_entries), 10_000))
        self.max_bytes = max(1024, min(int(max_bytes), 8 * 1024 * 1024))
        if self.path.exists() and self.path.is_symlink():
            raise SessionCatalogError("session_catalog_unsafe")
        self._entries = self._load()

    def active_for(self, identity: SessionIdentity) -> SessionEntry | None:
        entry = self._entries.get(identity.key)
        if not entry or entry.status != "active":
            return None
        if (
            entry.scope_hash != identity.scope_hash
            or entry.workspace != identity.workspace
            or entry.policy_fingerprint != identity.policy_fingerprint
        ):
            return None
        return entry

    def upsert_active(
        self,
        identity: SessionIdentity,
        thread_id: str,
        *,
        updated_at: int | None = None,
    ) -> SessionEntry:
        if not isinstance(thread_id, str) or not thread_id.strip() or len(thread_id) > 256:
            raise ValueError("session_thread_invalid")
        entry = SessionEntry(
            key=identity.key,
            scope_hash=identity.scope_hash,
            workspace=identity.workspace,
            policy_fingerprint=identity.policy_fingerprint,
            thread_id=thread_id.strip(),
            status="active",
            updated_at=int(time.time() if updated_at is None else updated_at),
        )
        self._entries[identity.key] = entry
        self._gc()
        self._persist()
        return entry

    def archive_active(
        self, identity: SessionIdentity, *, updated_at: int | None = None
    ) -> bool:
        entry = self._entries.get(identity.key)
        if not entry or entry.status != "active":
            return False
        self._entries[identity.key] = SessionEntry(
            **{
                **asdict(entry),
                "status": "archived",
                "updated_at": int(time.time() if updated_at is None else updated_at),
            }
        )
        self._persist()
        return True

    def _load(self) -> dict[str, SessionEntry]:
        if not self.path.exists():
            return {}
        try:
            metadata = self.path.lstat()
            if not self.path.is_file() or metadata.st_size > self.max_bytes:
                return {}
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {}
        if not isinstance(raw, list):
            return {}
        entries: dict[str, SessionEntry] = {}
        for item in raw:
            entry = self._normalize(item)
            if entry is not None:
                entries[entry.key] = entry
        return entries

    def _normalize(self, raw: object) -> SessionEntry | None:
        if not isinstance(raw, dict) or set(raw) != {
            "key",
            "scope_hash",
            "workspace",
            "policy_fingerprint",
            "thread_id",
            "status",
            "updated_at",
        }:
            return None
        if not all(
            isinstance(raw[name], str)
            for name in (
                "key",
                "scope_hash",
                "workspace",
                "policy_fingerprint",
                "thread_id",
                "status",
            )
        ) or not isinstance(raw["updated_at"], int):
            return None
        if raw["status"] not in {"active", "archived"}:
            return None
        return SessionEntry(**raw)

    def _gc(self) -> None:
        ordered = sorted(
            self._entries.values(), key=lambda item: item.updated_at, reverse=True
        )[: self.max_entries]
        self._entries = {entry.key: entry for entry in ordered}

    def _persist(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        payload = (
            json.dumps(
                [asdict(entry) for entry in self._entries.values()],
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        if len(payload.encode("utf-8")) > self.max_bytes:
            raise SessionCatalogError("session_catalog_too_large")
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
