from __future__ import annotations

import base64
import json
import threading
import unittest
import urllib.error
import urllib.request


class _FakeReply:
    text = "可见最终回复"
    resumed = False


class _FakeRunner:
    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.release = None

    def run(self, scope, messages, *, images=()):
        self.calls.append((scope, messages, list(images)))
        self.started.set()
        if self.release is not None:
            self.release.wait(3)
        return _FakeReply()


class _FakeTranscriber:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio_base64, *, filename, language):
        self.calls.append((audio_base64, filename, language))
        return "语音内容"


class CodexHttpTests(unittest.TestCase):
    token = "private-test-token"

    def setUp(self):
        from wechat_codex_bridge.http import create_server

        self.runner = _FakeRunner()
        self.transcriber = _FakeTranscriber()
        self.server = create_server(
            "127.0.0.1", 0, token=self.token, runner=self.runner,
            transcriber=self.transcriber, local_addresses={"127.0.0.1"},
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def _request(self, path, *, method="GET", payload=None, token=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {token or self.token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.headers, exc.read()
            finally:
                exc.close()

    def _chat_payload(self, image_count=0):
        content = [{"type": "text", "text": "理解媒体"}]
        content.extend(
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + ("A" * 200_000)}}
            for _ in range(image_count)
        )
        return {
            "model": "codex-current",
            "user": "wechat-scope-1",
            "messages": [{"role": "user", "content": content}],
        }

    def test_server_rejects_wildcard_and_accepts_verified_local_gateway(self):
        from wechat_codex_bridge.http import create_server

        with self.assertRaisesRegex(ValueError, "bridge_bind_invalid"):
            create_server(
                "0.0.0.0", 0, token=self.token, runner=self.runner,
                local_addresses={"0.0.0.0"},
            )
        server = create_server(
            "127.0.0.1", 0, token=self.token, runner=self.runner,
            local_addresses={"127.0.0.1", "172.19.0.1"},
        )
        server.server_close()

    def test_health_requires_authentication(self):
        status, _, body = self._request("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["account_mode"], "current-user")
        status, _, _ = self._request("/healthz", token="wrong-token-value")
        self.assertEqual(status, 401)

    def test_accepts_robot_sized_image_and_six_video_frames(self):
        status, _, body = self._request(
            "/v1/chat/completions", method="POST", payload=self._chat_payload(image_count=6)
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(len(self.runner.calls[0][2]), 6)
        self.assertEqual(self.runner.calls[0][1][-1]["content"], "理解媒体")

    def test_rejects_more_than_eight_frames(self):
        status, _, body = self._request(
            "/v1/chat/completions", method="POST", payload=self._chat_payload(image_count=9)
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_request")

    def test_transcribe_uses_same_bearer_token(self):
        audio = base64.b64encode(b"voice-bytes").decode()
        status, _, body = self._request(
            "/transcribe", method="POST",
            payload={"audio_base64": audio, "filename": "voice.wav", "language": "zh"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"text": "语音内容"})
        self.assertEqual(self.transcriber.calls, [(audio, "voice.wav", "zh")])

    def test_same_scope_requests_wait_instead_of_returning_busy(self):
        self.runner.release = threading.Event()
        first = {}
        second = {}

        first_worker = threading.Thread(
            target=lambda: first.setdefault(
                "result",
                self._request(
                    "/v1/chat/completions", method="POST", payload=self._chat_payload()
                ),
            )
        )
        first_worker.start()
        self.assertTrue(self.runner.started.wait(2))

        second_worker = threading.Thread(
            target=lambda: second.setdefault(
                "result",
                self._request(
                    "/v1/chat/completions", method="POST", payload=self._chat_payload()
                ),
            )
        )
        second_worker.start()
        second_worker.join(0.2)
        self.assertTrue(second_worker.is_alive(), "second request should queue")

        self.runner.release.set()
        first_worker.join(3)
        second_worker.join(3)

        self.assertEqual(first["result"][0], 200)
        self.assertEqual(second["result"][0], 200)
        self.assertEqual(len(self.runner.calls), 2)

    def test_queue_timeout_is_capped_at_120_seconds(self):
        from wechat_codex_bridge.http import create_server

        server = create_server(
            "127.0.0.1", 0, token=self.token, runner=self.runner,
            queue_timeout=999, local_addresses={"127.0.0.1"},
        )
        try:
            self.assertEqual(server.queue_timeout, 120.0)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
