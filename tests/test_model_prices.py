#!/usr/bin/env python3
"""Cursor model extraction + Grok/Composer list-price lookup."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import db  # noqa: E402
from ardoise.adapters.cloud_agent import parse_line  # noqa: E402
from ardoise.adapters.hook_event import event_to_entry  # noqa: E402
from ardoise.backfill import backfill  # noqa: E402
from ardoise.estimate import price_ask  # noqa: E402
from ardoise.model import UNKNOWN, extract_model, persist_model  # noqa: E402
from ardoise.prices import lookup, normalize_model, price_usd, rates_for  # noqa: E402
from ardoise.privacy import usage_only_event  # noqa: E402
from ardoise.vendors.cursor import parse_cursor_line, parse_event  # noqa: E402


class ExtractTests(unittest.TestCase):
    def test_skips_legacy_default_for_model_id(self) -> None:
        self.assertEqual(
            extract_model({"model": "default", "model_id": "grok-4.6"}),
            "grok-4.6",
        )
        self.assertEqual(
            persist_model({"model": "default", "model_id": "grok-4.6"}),
            "grok-4.6",
        )

    def test_prefers_full_cursor_slug_over_short_id(self) -> None:
        self.assertEqual(
            extract_model(
                {
                    "model": "cursor-grok-4.6-high",
                    "model_id": "grok-4.6",
                }
            ),
            "cursor-grok-4.6-high",
        )

    def test_nested_message_model(self) -> None:
        self.assertEqual(
            extract_model(
                {
                    "model": "auto",
                    "message": {"model": "composer-2.5", "usage": {"input_tokens": 1}},
                }
            ),
            "composer-2.5",
        )

    def test_appends_fast_when_hook_named_it(self) -> None:
        self.assertEqual(
            extract_model(
                {
                    "model": "default",
                    "model_id": "grok-4.6",
                    "model_params": [{"id": "fast", "value": "true"}],
                }
            ),
            "grok-4.6-fast",
        )

    def test_unknown_when_only_placeholder(self) -> None:
        self.assertIsNone(extract_model({"model": "default"}))
        self.assertEqual(persist_model({"model": "default"}), UNKNOWN)
        self.assertEqual(persist_model({}), UNKNOWN)


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HOME")
        self._old_ardoise = os.environ.get("ARDOISE_HOME")
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_CONFIG"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_ardoise is None:
            os.environ.pop("ARDOISE_HOME", None)
        else:
            os.environ["ARDOISE_HOME"] = self._old_ardoise
        self.tmp.cleanup()


class HookAndBackfillTests(IsolatedHome):
    def test_hook_default_persists_model_id(self) -> None:
        raw = {
            "hook_event_name": "stop",
            "model": "default",
            "model_id": "grok-4.6",
            "generation_id": "req_default_grok",
            "message_id": "msg_default_grok",
            "timestamp": "2026-09-14T12:00:00Z",
            "input_tokens": 1000,
            "output_tokens": 100,
        }
        safe = usage_only_event(raw)
        self.assertEqual(safe["model"], "grok-4.6")
        entry = event_to_entry(raw, default_source="cursor")
        assert entry is not None
        self.assertEqual(entry["model"], "grok-4.6")
        self.assertEqual(entry["source"], "cursor")

    def test_parse_cursor_line_keeps_nested_slug(self) -> None:
        entry = parse_cursor_line(
            {
                "model": "default",
                "requestId": "req_nested",
                "message": {
                    "id": "msg_nested",
                    "model": "cursor-grok-4.6-high",
                    "usage": {"input_tokens": 40, "output_tokens": 8},
                },
            }
        )
        assert entry is not None
        self.assertEqual(entry["model"], "cursor-grok-4.6-high")
        self.assertEqual(entry["source"], "cursor")

    def test_cloud_sidecar_replaces_placeholder(self) -> None:
        entry = parse_line(
            {
                "type": "assistant",
                "model": "default",
                "requestId": "req_side",
                "message": {"id": "msg_side", "usage": {"input_tokens": 10, "output_tokens": 2}},
            },
            inherited={"model": "cursor-grok-4.6-high"},
        )
        assert entry is not None
        self.assertEqual(entry["model"], "cursor-grok-4.6-high")

    def test_backfill_persists_extracted_model(self) -> None:
        claude = Path(self.tmp.name) / "empty-claude"
        cursor = Path(self.tmp.name) / "cursor"
        dest = cursor / "projects" / "app"
        dest.mkdir(parents=True)
        claude.mkdir()
        (dest / "chat.jsonl").write_text(
            json.dumps(
                {
                    "hook_event_name": "afterAgentResponse",
                    "model": "default",
                    "model_id": "grok-4.6",
                    "timestamp": "2026-09-14T10:00:00Z",
                    "requestId": "req_bf",
                    "message_id": "msg_bf",
                    "input_tokens": 1000,
                    "output_tokens": 400,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        result = backfill(claude=claude, cursor=cursor)
        self.assertGreaterEqual(result["inserted"], 1)
        with db.session() as conn:
            row = conn.execute(
                "SELECT model, cost_usd FROM events WHERE message_id = 'msg_bf'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["model"], "grok-4.6")
        self.assertAlmostEqual(float(row["cost_usd"]), 0.0044, places=6)


class PriceLookupTests(unittest.TestCase):
    def test_grok_standard_and_fast(self) -> None:
        std = lookup("cursor-grok-4.6-high")
        self.assertFalse(std["unknown"])
        self.assertEqual(std["key"], "grok-4-6")
        self.assertEqual(std["rates"]["input"], 2.0)
        self.assertEqual(std["rates"]["output"], 6.0)
        self.assertEqual(std["rates"]["cache_read"], 0.5)
        self.assertEqual(std["rates"]["cache_write_5m"], 0.0)

        fast = lookup("cursor-grok-4.6-high-fast")
        self.assertEqual(fast["key"], "grok-4-6-fast")
        self.assertEqual(fast["rates"]["input"], 4.0)
        self.assertEqual(fast["rates"]["output"], 12.0)

        short = lookup("grok-4.6")
        self.assertEqual(short["key"], "grok-4-6")
        self.assertAlmostEqual(
            price_usd(model="cursor-grok-4.6-high", input_tokens=1000, output_tokens=400),
            0.0044,
            places=6,
        )
        self.assertAlmostEqual(
            price_usd(model="cursor-grok-4.6-high-fast", input_tokens=1000, output_tokens=400),
            0.0088,
            places=6,
        )

    def test_composer_official_rates(self) -> None:
        std = lookup("composer-2.5")
        self.assertEqual(std["key"], "composer-2-5")
        self.assertEqual(std["rates"]["input"], 0.5)
        self.assertEqual(std["rates"]["output"], 2.5)
        fast = lookup("composer-2.5-fast")
        self.assertEqual(fast["key"], "composer-2-5-fast")
        self.assertEqual(fast["rates"]["input"], 3.0)
        self.assertEqual(fast["rates"]["output"], 15.0)

    def test_placeholder_is_zero_not_sonnet(self) -> None:
        for name in (None, "", "default", "auto", UNKNOWN):
            looked = lookup(name)
            self.assertTrue(looked["unknown"], name)
            self.assertEqual(looked["key"], UNKNOWN)
            self.assertEqual(looked["rates"]["input"], 0.0)
            self.assertEqual(looked["rates"]["output"], 0.0)
            self.assertEqual(price_usd(model=name, input_tokens=1000, output_tokens=400), 0.0)
        sonnet = rates_for("claude-sonnet-4-6")
        self.assertEqual(sonnet["input"], 3.0)
        self.assertEqual(sonnet["output"], 15.0)
        self.assertNotEqual(rates_for("default")["input"], sonnet["input"])

    def test_unlisted_sku_does_not_inherit_sonnet(self) -> None:
        looked = lookup("definitely-not-a-real-model-xyz")
        self.assertTrue(looked["unknown"])
        self.assertEqual(looked["rates"]["input"], 0.0)
        self.assertEqual(normalize_model("default"), UNKNOWN)

    def test_estimate_exposes_rate_key(self) -> None:
        data = price_ask(model="cursor-grok-4.6-high", input_tokens=1000, output_tokens=400, with_gate=False)
        self.assertAlmostEqual(data["usd"], 0.0044, places=6)
        self.assertEqual(data["rate_key"], "grok-4-6")
        self.assertFalse(data["unknown"])
        empty = price_ask(model="default", input_tokens=1000, output_tokens=400, with_gate=False)
        self.assertTrue(empty["unknown"])
        self.assertEqual(empty["usd"], 0.0)

    def test_t2_parse_uses_extracted_model(self) -> None:
        row = parse_event(
            {
                "timestamp": "2026-09-14T00:00:00Z",
                "model": "default",
                "model_id": "grok-4.6",
                "tokenUsage": {"inputTokens": 1000, "outputTokens": 400},
            }
        )
        assert row is not None
        self.assertEqual(row["model"], "grok-4.6")
        self.assertAlmostEqual(float(row["cost_usd"]), 0.0044, places=6)


if __name__ == "__main__":
    unittest.main()
