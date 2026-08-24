from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class _FakeCommands:
    def __init__(self, *, clients=None, inspect_payload=None, sql_results=None):
        self.clients = ["client_robot1"] if clients is None else clients
        self.inspect_payload = inspect_payload or [{
            "Config": {"Env": ["MYSQL_DB=robot_database", "MYSQL_HOST=wechat-admin-mysql", "PASSWORD=secret"]},
            "NetworkSettings": {"Networks": {"wechat-robot": {"Gateway": "172.19.0.1"}}},
        }]
        self.sql_results = list(sql_results or [])
        self.calls = []

    def __call__(self, argv, *, input_text=None):
        self.calls.append((list(argv), input_text))
        if argv[:2] == ["docker", "ps"]:
            return "\n".join(self.clients) + ("\n" if self.clients else "")
        if argv[:2] == ["docker", "inspect"]:
            return json.dumps(self.inspect_payload)
        if argv[:2] == ["docker", "exec"]:
            return self.sql_results.pop(0)
        raise AssertionError(argv)


class DockerAdminTests(unittest.TestCase):
    def test_discovers_unique_target_and_private_gateway_without_secrets(self):
        from wechat_codex_bridge.docker_admin import discover_target

        target = discover_target(_FakeCommands())

        self.assertEqual(target.container, "client_robot1")
        self.assertEqual(target.database, "robot_database")
        self.assertEqual(target.network, "wechat-robot")
        self.assertEqual(target.gateway, "172.19.0.1")
        self.assertNotIn("secret", repr(target))

    def test_refuses_zero_or_multiple_clients(self):
        from wechat_codex_bridge.docker_admin import AdminError, discover_target

        for clients in ([], ["client_a", "client_b"]):
            with self.subTest(clients=clients):
                with self.assertRaisesRegex(AdminError, "target_robot_ambiguous"):
                    discover_target(_FakeCommands(clients=clients))

    def test_endpoint_uses_desktop_hostname_on_mac_and_windows(self):
        from wechat_codex_bridge.docker_admin import BridgeEndpoint, RobotTarget, endpoint_for

        target = RobotTarget("client_a", "robot_a", "mysql", "wechat-robot", "172.19.0.1")
        expected = BridgeEndpoint("127.0.0.1", "http://host.docker.internal:18791")
        self.assertEqual(endpoint_for(target, system="Darwin"), expected)
        self.assertEqual(endpoint_for(target, system="Windows"), expected)

    def test_endpoint_uses_exact_gateway_on_linux(self):
        from wechat_codex_bridge.docker_admin import BridgeEndpoint, RobotTarget, endpoint_for

        target = RobotTarget("client_a", "robot_a", "mysql", "wechat-robot", "172.19.0.1")
        self.assertEqual(
            endpoint_for(target, system="Linux"),
            BridgeEndpoint("172.19.0.1", "http://172.19.0.1:18791"),
        )

    def test_snapshot_and_configure_keep_secret_out_of_argv(self):
        from wechat_codex_bridge.docker_admin import RobotTarget, configure_settings, snapshot_settings

        target = RobotTarget("client_robot1", "robot_database", "wechat-admin-mysql", "net", "172.19.0.1")
        old = {
            "chat_ai_enabled": 1, "chat_base_url": "http://old", "chat_api_key": "old-secret",
            "chat_model": "old-model", "image_recognition_model": "old-vision",
        }
        commands = _FakeCommands(sql_results=[json.dumps(old) + "\n", "1\n"])
        with tempfile.TemporaryDirectory() as tmp:
            backup = snapshot_settings(target, Path(tmp), commands)
            payload = json.loads(backup.read_text(encoding="utf-8"))
            result = configure_settings(
                target, token="new-private-token-value",
                base_url="http://host.docker.internal:18791", model="codex-current",
                apply=True, run=commands,
            )

        self.assertEqual(payload["settings"], old)
        self.assertEqual(result, "applied")
        argv, sql = commands.calls[-1]
        self.assertNotIn("new-private-token-value", " ".join(argv))
        self.assertIn("UPDATE global_settings", sql)

    def test_configure_is_dry_run_by_default(self):
        from wechat_codex_bridge.docker_admin import RobotTarget, configure_settings

        commands = _FakeCommands()
        target = RobotTarget("client", "database", "mysql", "net", "172.19.0.1")
        self.assertEqual(
            configure_settings(
                target, token="x" * 32, base_url="http://172.19.0.1:18791",
                model="codex-current", apply=False, run=commands,
            ),
            "dry-run",
        )
        self.assertEqual(commands.calls, [])


if __name__ == "__main__":
    unittest.main()
