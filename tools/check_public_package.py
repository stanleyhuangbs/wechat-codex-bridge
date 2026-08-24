#!/usr/bin/env python3
"""Reject private artifacts and unexpected members from the public package."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path


FORBIDDEN_NAMES = {
    "token", "sessions.json", "auth.json", "settings.json", "stdout.log", "stderr.log",
}
SKIP_PARTS = {".git", ".worktrees", "__pycache__", "dist", "build"}
PRIVATE_PATHS = (
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\"),
)
SECRET_VALUES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r'"(?:access_token|refresh_token)"\s*:\s*"[^"$]{12,}"', re.I),
)
EXPECTED_PACKAGE = {
    "__init__.py", "docker_admin.py", "http.py", "platform.py", "protocol.py",
    "runner.py", "sessions.py", "transcribe.py",
}


def scan_tree(root: Path) -> list[str]:
    errors: list[str] = []
    scanner = Path(__file__).resolve()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.name in FORBIDDEN_NAMES:
            errors.append(f"forbidden artifact: {relative}")
        if not path.is_file() or path.resolve() == scanner or path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in (*PRIVATE_PATHS, *SECRET_VALUES):
            if pattern.search(text):
                errors.append(f"private pattern: {relative}")
                break
    return errors


def scan_wheel(path: Path) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if any(name.startswith(("/", "../")) or "/../" in name for name in names):
            errors.append("unsafe wheel member")
        modules = {
            Path(name).name for name in names
            if name.startswith("wechat_codex_bridge/") and name.endswith(".py")
        }
        if modules != EXPECTED_PACKAGE:
            errors.append(f"unexpected package modules: {sorted(modules ^ EXPECTED_PACKAGE)}")
        if any(name.startswith(("tests/", "bridge/")) for name in names):
            errors.append("parent project or tests included in wheel")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    args = parser.parse_args()
    errors = scan_tree(args.root.resolve()) + scan_wheel(args.wheel.resolve())
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("public-package-check=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
