"""Dry-run-first administration for one local Docker WeChat robot."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import platform as host_platform
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .http import _private_token
from .platform import write_private_text


class AdminError(RuntimeError):
    """A stable, non-sensitive administration failure."""


@dataclass(frozen=True)
class RobotTarget:
    container: str
    database: str
    mysql_container: str
    network: str
    gateway: str


@dataclass(frozen=True)
class BridgeEndpoint:
    bind_host: str
    container_base_url: str


CommandRunner = Callable[..., str]
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SETTING_FIELDS = (
    "chat_ai_enabled", "chat_base_url", "chat_api_key", "chat_model", "image_recognition_model",
)


def run_command(argv: Sequence[str], *, input_text: str | None = None) -> str:
    try:
        completed = subprocess.run(
            list(argv), input=input_text, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdminError("docker_command_unavailable") from exc
    if completed.returncode != 0:
        raise AdminError("docker_command_failed")
    if len(completed.stdout.encode("utf-8")) > 1024 * 1024:
        raise AdminError("docker_response_too_large")
    return completed.stdout


def discover_target(run: CommandRunner = run_command) -> RobotTarget:
    output = run(["docker", "ps", "--filter", "name=^/client_", "--format", "{{.Names}}"])
    clients = [line.strip() for line in output.splitlines() if line.strip()]
    if len(clients) != 1 or not _SAFE_NAME.fullmatch(clients[0]):
        raise AdminError("target_robot_ambiguous")
    container = clients[0]
    try:
        inspected = json.loads(run(["docker", "inspect", container]))[0]
        environment = inspected["Config"]["Env"]
        networks = inspected["NetworkSettings"]["Networks"]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
        raise AdminError("target_robot_invalid") from exc
    selected: dict[str, str] = {}
    for item in environment if isinstance(environment, list) else []:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            if key in {"MYSQL_DB", "MYSQL_HOST"}:
                selected[key] = value
    candidates = []
    if isinstance(networks, Mapping):
        for name, metadata in networks.items():
            gateway = metadata.get("Gateway") if isinstance(metadata, Mapping) else None
            if isinstance(name, str) and isinstance(gateway, str) and gateway:
                candidates.append((name, gateway))
    database = selected.get("MYSQL_DB", "")
    mysql_container = selected.get("MYSQL_HOST", "")
    if (
        not _SAFE_NAME.fullmatch(database)
        or not _SAFE_NAME.fullmatch(mysql_container)
        or len(candidates) != 1
        or not _SAFE_NAME.fullmatch(candidates[0][0])
    ):
        raise AdminError("target_robot_invalid")
    network, gateway = candidates[0]
    try:
        address = ipaddress.ip_address(gateway)
    except ValueError as exc:
        raise AdminError("target_robot_invalid") from exc
    if address.version != 4 or not address.is_private or address.is_loopback:
        raise AdminError("target_robot_invalid")
    return RobotTarget(container, database, mysql_container, network, gateway)


def endpoint_for(target: RobotTarget, *, system: str | None = None) -> BridgeEndpoint:
    current = host_platform.system() if system is None else system
    if current in {"Darwin", "Windows"}:
        return BridgeEndpoint("127.0.0.1", "http://host.docker.internal:18791")
    if current == "Linux":
        try:
            address = ipaddress.ip_address(target.gateway)
        except ValueError as exc:
            raise AdminError("bridge_endpoint_unavailable") from exc
        if address.version == 4 and address.is_private and not address.is_loopback:
            return BridgeEndpoint(target.gateway, f"http://{target.gateway}:18791")
    raise AdminError("bridge_endpoint_unavailable")


def snapshot_settings(target: RobotTarget, backup_dir: Path, run: CommandRunner = run_command) -> Path:
    query = (
        "SELECT JSON_OBJECT('chat_ai_enabled',chat_ai_enabled,'chat_base_url',chat_base_url,"
        "'chat_api_key',chat_api_key,'chat_model',chat_model,"
        "'image_recognition_model',image_recognition_model) FROM global_settings "
        "HAVING (SELECT COUNT(*) FROM global_settings)=1;\n"
    )
    try:
        settings = json.loads(_mysql(target, query, run).strip())
    except (json.JSONDecodeError, TypeError) as exc:
        raise AdminError("settings_snapshot_invalid") from exc
    if not isinstance(settings, dict) or set(settings) != set(_SETTING_FIELDS):
        raise AdminError("settings_snapshot_invalid")
    if backup_dir.exists() and backup_dir.is_symlink():
        raise AdminError("backup_path_unsafe")
    target_hash = hashlib.sha256(
        f"{target.container}\x1f{target.database}".encode()
    ).hexdigest()[:16]
    path = backup_dir / f"settings-{int(time.time())}-{target_hash}.json"
    payload = json.dumps(
        {"version": 1, "database": target.database, "settings": settings},
        ensure_ascii=False, sort_keys=True, indent=2,
    ) + "\n"
    write_private_text(path, payload)
    return path


def configure_settings(
    target: RobotTarget, *, token: str, base_url: str, model: str,
    apply: bool, run: CommandRunner = run_command,
) -> str:
    if not apply:
        return "dry-run"
    if not isinstance(token, str) or not 16 <= len(token) <= 512:
        raise AdminError("bridge_token_invalid")
    allowed_urls = {
        "http://host.docker.internal:18791",
        f"http://{target.gateway}:18791",
    }
    if base_url not in allowed_urls or model != "codex-current":
        raise AdminError("bridge_endpoint_invalid")
    _apply_settings(target, {
        "chat_ai_enabled": 1, "chat_base_url": base_url, "chat_api_key": token,
        "chat_model": model, "image_recognition_model": model,
    }, run)
    return "applied"


def rollback_settings(
    target: RobotTarget, backup: Path, *, apply: bool, run: CommandRunner = run_command,
) -> str:
    if not apply:
        return "dry-run"
    backup = Path(backup)
    if not backup.is_absolute() or backup.is_symlink() or not backup.is_file() or backup.stat().st_size > 64 * 1024:
        raise AdminError("backup_path_unsafe")
    try:
        payload = json.loads(backup.read_text(encoding="utf-8"))
        settings = payload["settings"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AdminError("backup_invalid") from exc
    if payload.get("version") != 1 or payload.get("database") != target.database:
        raise AdminError("backup_target_mismatch")
    if not isinstance(settings, dict) or set(settings) != set(_SETTING_FIELDS):
        raise AdminError("backup_invalid")
    _apply_settings(target, settings, run)
    return "restored"


def _apply_settings(target: RobotTarget, settings: Mapping[str, object], run: CommandRunner) -> None:
    enabled = int(settings["chat_ai_enabled"]) if isinstance(settings["chat_ai_enabled"], bool) else settings["chat_ai_enabled"]
    if not isinstance(enabled, int) or enabled not in {0, 1}:
        raise AdminError("settings_value_invalid")
    assignments = [f"chat_ai_enabled={enabled}"]
    for field in _SETTING_FIELDS[1:]:
        value = settings[field]
        if value is None:
            assignments.append(f"{field}=NULL")
        elif isinstance(value, str) and len(value) <= 4096:
            assignments.append(f"{field}={_sql_text(value)}")
        else:
            raise AdminError("settings_value_invalid")
    sql = (
        "START TRANSACTION;\nSET @bridge_row_count=(SELECT COUNT(*) FROM global_settings);\n"
        f"UPDATE global_settings SET {','.join(assignments)} WHERE @bridge_row_count=1;\n"
        "SELECT ROW_COUNT();\nCOMMIT;\n"
    )
    result = _mysql(target, sql, run).strip().splitlines()
    if not result or result[-1].strip() != "1":
        raise AdminError("settings_update_not_single_row")


def _sql_text(value: str) -> str:
    return f"CONVERT(0x{value.encode('utf-8').hex()} USING utf8mb4)"


def _mysql(target: RobotTarget, sql: str, run: CommandRunner) -> str:
    if not _SAFE_NAME.fullmatch(target.database) or not _SAFE_NAME.fullmatch(target.mysql_container):
        raise AdminError("target_robot_invalid")
    return run([
        "docker", "exec", "-i", target.mysql_container, "sh", "-c",
        'exec env MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --batch --skip-column-names --raw "$1"',
        "wechat-codex-bridge-mysql", target.database,
    ], input_text=sql)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage one Docker WeChat Codex bridge target")
    parser.add_argument("--runtime-root", type=Path, default=Path.home() / ".wechat-codex-bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("discover")
    subparsers.add_parser("snapshot")
    configure = subparsers.add_parser("configure")
    configure.add_argument("--token-path", type=Path, required=True)
    configure.add_argument("--apply", action="store_true")
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("backup", type=Path)
    rollback.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    target = discover_target()
    endpoint = endpoint_for(target)
    target_hash = hashlib.sha256(f"{target.container}\x1f{target.database}".encode()).hexdigest()[:16]
    if args.command == "discover":
        print(json.dumps({"target": target_hash, "bind": endpoint.bind_host, "base_url": endpoint.container_base_url}))
    elif args.command == "snapshot":
        path = snapshot_settings(target, args.runtime_root / "backups")
        print(json.dumps({"backup": str(path)}))
    elif args.command == "configure":
        if not args.apply:
            print(json.dumps({"result": "dry-run", "target": target_hash}))
            return 0
        backup = snapshot_settings(target, args.runtime_root / "backups")
        result = configure_settings(
            target, token=_private_token(args.token_path), base_url=endpoint.container_base_url,
            model="codex-current", apply=True,
        )
        print(json.dumps({"result": result, "target": target_hash, "backup": str(backup)}))
    elif args.command == "rollback":
        result = rollback_settings(target, args.backup, apply=args.apply)
        print(json.dumps({"result": result, "target": target_hash}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
