"""Authenticated OpenAI-compatible facade for current-user Codex."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping, Sequence

from .platform import discover_codex, is_safe_bind_host, private_file_policy
from .runner import CodexRunnerError, CurrentUserCodexRunner
from .transcribe import TranscriptionError, WhisperCliTranscriber


_MAX_BODY_BYTES = 80 * 1024 * 1024
_MAX_MESSAGES = 32
_MAX_TEXT_BYTES = 48 * 1024
_MAX_IMAGES = 8
_DEFAULT_QUEUE_TIMEOUT_SECONDS = 120.0
_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class BridgeHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self, address, handler, *, token, runner, transcriber, max_concurrency,
        queue_timeout,
    ):
        self.token = token
        self.runner = runner
        self.transcriber = transcriber
        self.pool = threading.BoundedSemaphore(max(1, min(int(max_concurrency), 16)))
        self.active_scopes: set[str] = set()
        self.active_scopes_condition = threading.Condition()
        self.queue_timeout = max(0.1, min(float(queue_timeout), _DEFAULT_QUEUE_TIMEOUT_SECONDS))
        super().__init__(address, handler)

    def reserve_scope(self, scope: str) -> bool:
        deadline = time.monotonic() + self.queue_timeout
        with self.active_scopes_condition:
            while scope in self.active_scopes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self.active_scopes_condition.wait(remaining)
            self.active_scopes.add(scope)
        remaining = deadline - time.monotonic()
        if remaining > 0 and self.pool.acquire(timeout=remaining):
            return True
        with self.active_scopes_condition:
            self.active_scopes.remove(scope)
            self.active_scopes_condition.notify_all()
        return False

    def release_scope(self, scope: str) -> None:
        with self.active_scopes_condition:
            if scope in self.active_scopes:
                self.active_scopes.remove(scope)
                self.pool.release()
                self.active_scopes_condition.notify_all()


class CodexHttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "WeChatCodexBridge"
    sys_version = ""

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_GET(self) -> None:
        if not self._authorized():
            self._error(401, "unauthorized", "authentication required")
        elif self.path != "/healthz":
            self._error(404, "not_found", "not found")
        else:
            self._json(200, {
                "status": "ok", "account_mode": "current-user",
                "transcription": self.server.transcriber is not None,
            })

    def do_POST(self) -> None:
        if not self._authorized():
            self._error(401, "unauthorized", "authentication required")
            return
        if self.headers.get_content_type() != "application/json":
            self._error(400, "invalid_request", "invalid request")
            return
        if self.path == "/v1/chat/completions":
            self._chat()
        elif self.path == "/transcribe":
            self._transcribe()
        else:
            self._error(404, "not_found", "not found")

    def _chat(self) -> None:
        try:
            scope, messages, images, stream, model = self._normalize_request(self._read_json())
        except (ValueError, TypeError, json.JSONDecodeError):
            self._error(400, "invalid_request", "invalid request")
            return
        if not self.server.reserve_scope(scope):
            self._error(409, "scope_busy", "conversation is busy")
            return
        try:
            reply = self.server.runner.run(scope, messages, images=images)
        except CodexRunnerError as exc:
            self._runner_error(str(exc))
            return
        except Exception:
            self._error(502, "backend_error", "bridge backend unavailable")
            return
        finally:
            self.server.release_scope(scope)
        if stream:
            self._sse(reply.text, model)
        else:
            self._completion(reply.text, model)

    def _transcribe(self) -> None:
        if self.server.transcriber is None:
            self._error(503, "transcription_unavailable", "transcription unavailable")
            return
        try:
            payload = self._read_json()
            audio = payload.get("audio_base64")
            filename = payload.get("filename", "voice.wav")
            language = payload.get("language", "zh")
            if not all(isinstance(value, str) for value in (audio, filename, language)):
                raise ValueError("transcription invalid")
            text = self.server.transcriber.transcribe(
                audio, filename=filename, language=language
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            self._error(400, "invalid_request", "invalid request")
            return
        except TranscriptionError as exc:
            if str(exc) == "transcription_timeout":
                self._error(504, "timeout", "transcription timed out")
            elif str(exc) == "transcription_audio_invalid":
                self._error(400, "invalid_request", "invalid request")
            else:
                self._error(503, "transcription_unavailable", "transcription unavailable")
            return
        self._json(200, {"text": text})

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        candidate = header[7:] if header.startswith("Bearer ") else ""
        return hmac.compare_digest(candidate, self.server.token)

    def _read_json(self) -> Mapping[str, object]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("length missing")
        length = int(raw_length)
        if length <= 0 or length > _MAX_BODY_BYTES:
            raise ValueError("length invalid")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("body incomplete")
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise ValueError("body invalid")
        return payload

    def _normalize_request(self, payload: Mapping[str, object]):
        scope = payload.get("user")
        if not isinstance(scope, str) or not _SCOPE_PATTERN.fullmatch(scope):
            raise ValueError("scope invalid")
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list) or not 1 <= len(raw_messages) <= _MAX_MESSAGES:
            raise ValueError("messages invalid")
        messages: list[dict[str, str]] = []
        images: list[str] = []
        text_bytes = 0
        for raw in raw_messages:
            if not isinstance(raw, Mapping) or raw.get("role") not in {"system", "user", "assistant"}:
                raise ValueError("message invalid")
            content = raw.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if not isinstance(part, Mapping):
                        raise ValueError("part invalid")
                    if part.get("type") == "text" and isinstance(part.get("text"), str):
                        parts.append(str(part["text"]))
                    elif part.get("type") == "image_url":
                        image_url = part.get("image_url")
                        if not isinstance(image_url, Mapping) or not isinstance(image_url.get("url"), str):
                            raise ValueError("image invalid")
                        url = str(image_url["url"])
                        if not url.startswith("data:image/"):
                            raise ValueError("remote image rejected")
                        images.append(url)
                    else:
                        raise ValueError("part invalid")
                text = "\n".join(parts)
            else:
                raise ValueError("content invalid")
            text = text.strip()
            if not text and raw.get("role") == "user":
                text = "请分析所附图片。" if images else ""
            if text:
                text_bytes += len(text.encode("utf-8"))
                if text_bytes > _MAX_TEXT_BYTES:
                    raise ValueError("text too large")
                messages.append({"role": str(raw["role"]), "content": text})
        if not messages or not any(item["role"] == "user" for item in messages):
            raise ValueError("user message missing")
        if len(images) > _MAX_IMAGES:
            raise ValueError("images invalid")
        stream = payload.get("stream", False)
        model = payload.get("model", "codex-current")
        if not isinstance(stream, bool) or not isinstance(model, str) or not model.strip() or len(model) > 100:
            raise ValueError("request invalid")
        return scope, messages, images, stream, model.strip()

    def _runner_error(self, code: str) -> None:
        if code == "codex_timeout":
            self._error(504, "timeout", "bridge request timed out")
        elif code in {"codex_unavailable", "codex_not_logged_in"}:
            self._error(503, "backend_unavailable", "bridge backend unavailable")
        elif code in {"codex_scope_invalid", "codex_prompt_invalid", "codex_prompt_too_large", "codex_images_invalid", "codex_image_invalid"}:
            self._error(400, "invalid_request", "invalid request")
        else:
            self._error(502, "backend_error", "bridge backend unavailable")

    def _completion(self, text: str, model: str) -> None:
        self._json(200, {
            "id": "chatcmpl-wechat-codex", "object": "chat.completion",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        })

    def _sse(self, text: str, model: str) -> None:
        chunk = {
            "id": "chatcmpl-wechat-codex", "object": "chat.completion.chunk",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
        }
        terminal = {
            "id": "chatcmpl-wechat-codex", "object": "chat.completion.chunk",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        body = (
            f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"data: {json.dumps(terminal, ensure_ascii=False, separators=(',', ':'))}\n\n"
            "data: [DONE]\n\n"
        ).encode("utf-8")
        self._send(200, body, "text/event-stream; charset=utf-8", {"Cache-Control": "no-cache"})

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": {"message": message, "type": "bridge_error", "code": code}})

    def _json(self, status: int, payload: Mapping[str, object]) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), "application/json; charset=utf-8")

    def _send(self, status, body, content_type, extra_headers=None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


def create_server(
    host: str, port: int, *, token: str, runner, transcriber=None,
    max_concurrency: int = 2,
    queue_timeout: float = _DEFAULT_QUEUE_TIMEOUT_SECONDS,
    local_addresses: set[str] | None = None,
) -> BridgeHttpServer:
    known_local = {"127.0.0.1", "::1"} if local_addresses is None else local_addresses
    if not is_safe_bind_host(host, local_addresses=known_local):
        raise ValueError("bridge_bind_invalid")
    if not isinstance(token, str) or len(token) < 16 or len(token) > 512:
        raise ValueError("bridge_token_invalid")
    return BridgeHttpServer(
        (host, int(port)), CodexHttpHandler, token=token, runner=runner,
        transcriber=transcriber, max_concurrency=max_concurrency,
        queue_timeout=queue_timeout,
    )


def _private_token(path: Path) -> str:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("bridge_token_path_invalid")
    if private_file_policy().kind == "posix-mode" and path.stat().st_mode & 0o077:
        raise ValueError("bridge_token_permissions_invalid")
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 16 or len(token) > 512:
        raise ValueError("bridge_token_invalid")
    return token


def _known_local_addresses() -> set[str]:
    addresses = {"127.0.0.1", "::1"}
    try:
        addresses.update(
            item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None)
        )
    except OSError:
        pass
    return addresses


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local current-user Codex bridge for WeChat")
    parser.add_argument("--bind", default=os.environ.get("WECHAT_CODEX_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WECHAT_CODEX_PORT", "18791")))
    parser.add_argument("--token-path", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--codex", type=Path)
    parser.add_argument("--whisper", type=Path)
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--queue-timeout", type=float, default=_DEFAULT_QUEUE_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    runner = CurrentUserCodexRunner(
        executable=discover_codex(args.codex), workspace=args.workspace,
        state_dir=args.state_dir, timeout=args.timeout,
    )
    transcriber = None
    try:
        transcriber = WhisperCliTranscriber(
            executable=args.whisper, runtime_dir=args.state_dir / "transcribe",
            model=args.whisper_model,
        )
    except TranscriptionError as exc:
        if str(exc) != "transcription_executable_unavailable":
            raise
    with create_server(
        args.bind, args.port, token=_private_token(args.token_path), runner=runner,
        transcriber=transcriber, max_concurrency=args.max_concurrency,
        queue_timeout=args.queue_timeout,
        local_addresses=_known_local_addresses(),
    ) as server:
        server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
