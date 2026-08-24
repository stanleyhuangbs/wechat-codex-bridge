"""Bounded parser for the Codex CLI JSONL protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass


class CodexProtocolError(RuntimeError):
    """A stable, non-sensitive Codex protocol failure."""


@dataclass(frozen=True)
class CodexRunResult:
    thread_id: str | None
    final_text: str
    completed: bool
    unknown_events: int = 0


def parse_codex_jsonl(
    payload: str,
    *,
    max_bytes: int = 256 * 1024,
    max_lines: int = 4096,
    max_response_bytes: int = 64 * 1024,
) -> CodexRunResult:
    if len(payload.encode("utf-8")) > max_bytes:
        raise CodexProtocolError("codex_stream_too_large")

    thread_id: str | None = None
    final_text: str | None = None
    completed = False
    unknown_events = 0
    lines = payload.splitlines()
    if len(lines) > max_lines:
        raise CodexProtocolError("codex_stream_too_large")

    known_nonterminal = {"turn.started", "item.started", "error"}
    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except (json.JSONDecodeError, TypeError) as exc:
            raise CodexProtocolError("codex_protocol_invalid") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
            raise CodexProtocolError("codex_protocol_invalid")
        event_type = raw["type"]
        if event_type == "thread.started":
            candidate = raw.get("thread_id", raw.get("threadId"))
            if not isinstance(candidate, str) or not candidate.strip():
                raise CodexProtocolError("codex_protocol_invalid")
            thread_id = candidate.strip()
        elif event_type == "agent_message":
            candidate = raw.get("message", raw.get("text"))
            if isinstance(candidate, str) and candidate.strip():
                final_text = candidate.strip()
        elif event_type == "item.completed":
            item = raw.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                candidate = item.get("text", item.get("message"))
                if isinstance(candidate, str) and candidate.strip():
                    final_text = candidate.strip()
        elif event_type == "turn.completed":
            completed = True
        elif event_type == "turn.failed":
            raise CodexProtocolError("codex_turn_failed")
        elif event_type in known_nonterminal:
            continue
        else:
            unknown_events += 1

    if not completed:
        raise CodexProtocolError("codex_stream_incomplete")
    if not final_text:
        raise CodexProtocolError("codex_response_invalid")
    if len(final_text.encode("utf-8")) > max_response_bytes:
        raise CodexProtocolError("codex_response_too_large")
    return CodexRunResult(
        thread_id=thread_id,
        final_text=final_text,
        completed=True,
        unknown_events=unknown_events,
    )
