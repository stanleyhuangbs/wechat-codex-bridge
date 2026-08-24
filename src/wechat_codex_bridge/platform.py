"""Cross-platform discovery, bind-safety, and private-file helpers."""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class PlatformError(RuntimeError):
    """A stable, non-sensitive platform integration failure."""


@dataclass(frozen=True)
class PrivateFilePolicy:
    kind: Literal["posix-mode", "windows-acl"]


def private_file_policy() -> PrivateFilePolicy:
    return PrivateFilePolicy("windows-acl" if os.name == "nt" else "posix-mode")


def discover_codex(explicit: Path | str | None = None) -> Path:
    candidate = str(explicit) if explicit is not None else shutil.which("codex")
    if not candidate:
        raise PlatformError("codex_executable_unavailable")
    try:
        resolved = Path(candidate).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PlatformError("codex_executable_invalid") from exc
    if not resolved.is_file():
        raise PlatformError("codex_executable_invalid")
    if os.name != "nt" and not os.access(resolved, os.X_OK):
        raise PlatformError("codex_executable_invalid")
    return resolved


def is_safe_bind_host(host: str, *, local_addresses: set[str]) -> bool:
    """Allow only an exact address owned by this host, never a wildcard."""
    return host not in {"0.0.0.0", "::", ""} and host in local_addresses


def _apply_windows_acl(path: Path) -> None:
    user = getpass.getuser()
    if not user:
        raise PlatformError("private_acl_identity_unavailable")
    result = subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{user}:(F)",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise PlatformError("private_acl_failed")


def restrict_private_path(path: Path | str, *, directory: bool = False) -> None:
    """Apply the current platform's current-user-only policy to an existing path."""
    target = Path(path)
    if private_file_policy().kind == "windows-acl":
        _apply_windows_acl(target)
    else:
        os.chmod(target, 0o700 if directory else 0o600)


def ensure_private_directory(path: Path | str) -> Path:
    directory = Path(path)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    restrict_private_path(directory, directory=True)
    return directory


def write_private_text(path: Path | str, text: str) -> None:
    """Atomically replace a UTF-8 file and restrict it to the current user."""
    destination = Path(path)
    ensure_private_directory(destination.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        if private_file_policy().kind == "posix-mode":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if private_file_policy().kind == "windows-acl":
            restrict_private_path(temporary)
        os.replace(temporary, destination)
        if private_file_policy().kind == "windows-acl":
            restrict_private_path(destination)
        else:
            os.chmod(destination, 0o600)
            try:
                directory_fd = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
