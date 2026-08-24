from __future__ import annotations

import json
import unittest


class CodexProtocolTests(unittest.TestCase):
    def test_parses_thread_and_final_message_only_after_normal_completion(self):
        from wechat_codex_bridge.protocol import parse_codex_jsonl

        payload = "\n".join(
            json.dumps(item)
            for item in (
                {"type": "thread.started", "thread_id": "thread-1"},
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "中间"}},
                {"type": "agent_message", "message": "最终回答"},
                {"type": "turn.completed", "usage": {"input_tokens": 10}},
            )
        )

        result = parse_codex_jsonl(payload)

        self.assertEqual(result.thread_id, "thread-1")
        self.assertEqual(result.final_text, "最终回答")
        self.assertTrue(result.completed)
        self.assertEqual(result.unknown_events, 0)

    def test_unknown_events_are_counted_but_not_returned(self):
        from wechat_codex_bridge.protocol import parse_codex_jsonl

        result = parse_codex_jsonl(
            "\n".join((
                '{"type":"future.event","secret":"do-not-return"}',
                '{"type":"thread.started","thread_id":"t"}',
                '{"type":"agent_message","message":"ok"}',
                '{"type":"turn.completed"}',
            ))
        )

        self.assertEqual(result.final_text, "ok")
        self.assertEqual(result.unknown_events, 1)

    def test_terminal_error_is_classified_without_raw_error_text(self):
        from wechat_codex_bridge.protocol import CodexProtocolError, parse_codex_jsonl

        with self.assertRaises(CodexProtocolError) as raised:
            parse_codex_jsonl(
                '{"type":"turn.failed","error":{"message":"private backend detail"}}'
            )

        self.assertEqual(str(raised.exception), "codex_turn_failed")
        self.assertNotIn("private", str(raised.exception))

    def test_missing_terminal_event_is_rejected(self):
        from wechat_codex_bridge.protocol import CodexProtocolError, parse_codex_jsonl

        with self.assertRaisesRegex(CodexProtocolError, "codex_stream_incomplete"):
            parse_codex_jsonl(
                '{"type":"agent_message","message":"not yet final"}'
            )

    def test_oversized_stream_is_rejected_before_json_decode(self):
        from wechat_codex_bridge.protocol import CodexProtocolError, parse_codex_jsonl

        with self.assertRaisesRegex(CodexProtocolError, "codex_stream_too_large"):
            parse_codex_jsonl("x" * 65, max_bytes=64)


if __name__ == "__main__":
    unittest.main()
