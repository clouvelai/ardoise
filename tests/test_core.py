#!/usr/bin/env python3
"""Stdlib unit tests for Ardoise Phase 1."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise.adapters.anthropic_t0 import parse_t0_line  # noqa: E402
from ardoise.prices import normalize_model, price_usd  # noqa: E402
from ardoise.privacy import is_dropped_key, scrub  # noqa: E402
from ardoise.project import owner_repo_from_url  # noqa: E402
from ardoise.queue import enqueue  # noqa: E402


class PriceTests(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize_model("claude-haiku-4-5-20251001"), "claude-haiku-4-5")
        self.assertEqual(normalize_model("composer-2.5"), "composer-2-5")
        self.assertEqual(normalize_model("cursor-grok-4.6-high"), "grok-4-6-high")
        self.assertEqual(normalize_model("Grok 4.6"), "grok-4-6")
        self.assertEqual(normalize_model("claude-4.5-sonnet"), "claude-sonnet-4-5")
        self.assertEqual(normalize_model("default"), "unknown")
        self.assertEqual(normalize_model("inherit"), "unknown")
        self.assertEqual(normalize_model(None), "unknown")

    def test_sonnet_46_stream_final(self) -> None:
        usd = price_usd(
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=400,
            cache_read_tokens=10000,
            cache_creation_tokens=2000,
        )
        self.assertAlmostEqual(usd, 0.0195, places=6)

    def test_haiku(self) -> None:
        usd = price_usd(model="claude-haiku-4-5", input_tokens=500, output_tokens=100)
        self.assertAlmostEqual(usd, 0.001, places=6)


class ProjectTests(unittest.TestCase):
    def test_https(self) -> None:
        self.assertEqual(
            owner_repo_from_url("https://github.com/clouvelai/ardoise.git"),
            "clouvelai/ardoise",
        )

    def test_ssh(self) -> None:
        self.assertEqual(
            owner_repo_from_url("git@github.com:clouvelai/Arbusteia.git"),
            "clouvelai/Arbusteia",
        )


class PrivacyTests(unittest.TestCase):
    def test_keeps_token_counts(self) -> None:
        self.assertFalse(is_dropped_key("input_tokens"))
        self.assertFalse(is_dropped_key("cache_read_input_tokens"))
        self.assertTrue(is_dropped_key("prompt"))
        self.assertTrue(is_dropped_key("access_token"))

    def test_scrub_drops_prompt(self) -> None:
        cleaned = scrub({"prompt": "SECRET", "model": "x", "usage": {"input_tokens": 1}})
        self.assertNotIn("prompt", cleaned)
        self.assertEqual(cleaned["usage"]["input_tokens"], 1)


class AdapterTests(unittest.TestCase):
    def test_parse_fixture_dedupe_keys(self) -> None:
        path = ROOT / "tests" / "fixtures" / "anthropic_t0.jsonl"
        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            obj = json.loads(line.replace("/WORKSPACE", str(ROOT)))
            parsed = parse_t0_line(obj)
            if parsed:
                entries.append(parsed)
        self.assertEqual(len(entries), 3)
        keys = {(e["message_id"], e["request_id"]) for e in entries}
        self.assertEqual(keys, {("msg_01AAA", "req_01AAA"), ("msg_01BBB", "req_01BBB")})
        finals = [e for e in entries if e["message_id"] == "msg_01AAA"]
        self.assertEqual(max(e["output_tokens"] for e in finals), 400)


class QueueTests(unittest.TestCase):
    def test_enqueue_strips_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            path = enqueue(
                {"prompt": "HOOK_SECRET", "model": "x", "usage": {"output_tokens": 2}},
                directory=dest,
            )
            body = path.read_text(encoding="utf-8")
            self.assertNotIn("HOOK_SECRET", body)
            self.assertNotIn("prompt", json.loads(body))


if __name__ == "__main__":
    unittest.main()
