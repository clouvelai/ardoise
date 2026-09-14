#!/usr/bin/env python3
"""Reprice existing ledger events from the current price book."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import db  # noqa: E402
from ardoise.cli import build_parser, main as cli_main  # noqa: E402
from ardoise.model import UNKNOWN  # noqa: E402
from ardoise.prices import price_usd  # noqa: E402
from ardoise.reprice import reprice  # noqa: E402


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

    def _insert(
        self,
        *,
        mid: str,
        model: str,
        occurred_at: str,
        cost_usd: float,
        input_tokens: int = 1000,
        output_tokens: int = 400,
        tier: str = "T0",
        billed_cents: int | None = None,
    ) -> None:
        with db.session() as conn:
            db.upsert_entry(
                conn,
                {
                    "vendor": "cursor",
                    "source": "cursor",
                    "message_id": mid,
                    "request_id": f"req-{mid}",
                    "project": "clouvelai/ardoise",
                    "model": model,
                    "occurred_at": occurred_at,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost_usd,
                    "tier": tier,
                    "billed_cents": billed_cents,
                },
            )


class RepriceTests(IsolatedHome):
    def test_known_model_reprices_from_book(self) -> None:
        want = price_usd(model="cursor-grok-4.6-high", input_tokens=1000, output_tokens=400)
        self.assertAlmostEqual(want, 0.0044, places=6)
        self._insert(
            mid="grok-stale",
            model="cursor-grok-4.6-high",
            occurred_at="2026-09-10T12:00:00Z",
            cost_usd=0.009,  # leftover Sonnet 1k/400
        )
        first = reprice()
        self.assertEqual(first["updated"], 1)
        self.assertEqual(first["skipped"], 0)
        self.assertEqual(first["unknown"], 0)
        with db.session() as conn:
            row = conn.execute(
                "SELECT cost_usd FROM events WHERE message_id = 'grok-stale'"
            ).fetchone()
        self.assertAlmostEqual(float(row["cost_usd"]), want, places=6)

        again = reprice()
        self.assertEqual(again["updated"], 0)
        self.assertEqual(again["skipped"], 1)
        self.assertEqual(again["unknown"], 0)

    def test_unknown_stays_honest_zero(self) -> None:
        self._insert(
            mid="unknown-stale",
            model=UNKNOWN,
            occurred_at="2026-09-11T12:00:00Z",
            cost_usd=0.009,
        )
        self._insert(
            mid="unknown-already",
            model="default",
            occurred_at="2026-09-11T13:00:00Z",
            cost_usd=0.0,
        )
        result = reprice()
        self.assertEqual(result["unknown"], 2)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["skipped"], 1)
        with db.session() as conn:
            stale = conn.execute(
                "SELECT cost_usd FROM events WHERE message_id = 'unknown-stale'"
            ).fetchone()
            already = conn.execute(
                "SELECT cost_usd FROM events WHERE message_id = 'unknown-already'"
            ).fetchone()
        self.assertAlmostEqual(float(stale["cost_usd"]), 0.0, places=8)
        self.assertAlmostEqual(float(already["cost_usd"]), 0.0, places=8)

    def test_month_filter(self) -> None:
        self._insert(
            mid="sept",
            model="cursor-grok-4.6-high",
            occurred_at="2026-09-02T12:00:00Z",
            cost_usd=9.0,
        )
        self._insert(
            mid="aug",
            model="cursor-grok-4.6-high",
            occurred_at="2026-08-20T12:00:00Z",
            cost_usd=9.0,
        )
        sept = reprice(month="2026-09")
        self.assertEqual(sept["month"], "2026-09")
        self.assertEqual(sept["scanned"], 1)
        self.assertEqual(sept["updated"], 1)
        with db.session() as conn:
            rows = {
                r["message_id"]: float(r["cost_usd"])
                for r in conn.execute("SELECT message_id, cost_usd FROM events")
            }
        self.assertAlmostEqual(rows["sept"], 0.0044, places=6)
        self.assertAlmostEqual(rows["aug"], 9.0, places=6)

        rest = reprice()
        self.assertEqual(rest["updated"], 1)
        self.assertEqual(rest["skipped"], 1)
        with db.session() as conn:
            aug = conn.execute(
                "SELECT cost_usd FROM events WHERE message_id = 'aug'"
            ).fetchone()
        self.assertAlmostEqual(float(aug["cost_usd"]), 0.0044, places=6)

    def test_billed_t2_not_overwritten(self) -> None:
        self._insert(
            mid="t2-billed",
            model="cursor-grok-4.6-high",
            occurred_at="2026-09-12T12:00:00Z",
            cost_usd=1.23,
            tier="T2",
            billed_cents=123,
        )
        result = reprice()
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 1)
        with db.session() as conn:
            row = conn.execute(
                "SELECT cost_usd FROM events WHERE message_id = 't2-billed'"
            ).fetchone()
        self.assertAlmostEqual(float(row["cost_usd"]), 1.23, places=6)


class RepriceCliTests(IsolatedHome):
    def test_cli_json_and_help(self) -> None:
        help_text = build_parser().format_help()
        self.assertIn("reprice", help_text)
        self._insert(
            mid="cli-grok",
            model="grok-4.6",
            occurred_at="2026-09-14T12:00:00Z",
            cost_usd=0.0,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["reprice", "--month", "2026-09", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "reprice")
        self.assertEqual(payload["month"], "2026-09")
        self.assertEqual(payload["updated"], 1)
        self.assertEqual(payload["unknown"], 0)
        self.assertIn("skipped", payload)

    def test_bad_month_exits(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(cli_main(["reprice", "--month", "09-2026"]), 2)
        self.assertIn("YYYY-MM", err.getvalue())


if __name__ == "__main__":
    unittest.main()
