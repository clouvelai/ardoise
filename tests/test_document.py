#!/usr/bin/env python3
"""Orb-floor spend document: parties, period, qty×rate, reconciliation footer."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import db, document, invoice  # noqa: E402
from ardoise.statement import write_statement  # noqa: E402
from ardoise.status import summarize  # noqa: E402


class PeriodAndPartyTests(unittest.TestCase):
    def test_month_period_strips_day_zero(self) -> None:
        period = document.month_period("2026-09")
        self.assertEqual(period["start"], "Sep 1, 2026")
        self.assertEqual(period["end"], "Sep 30, 2026")
        self.assertEqual(period["label"], "Sep 1, 2026 – Sep 30, 2026")

    def test_format_date_strips_day_zero(self) -> None:
        stamp = datetime(2026, 9, 4, tzinfo=timezone.utc)
        self.assertEqual(document.format_date(stamp), "Sep 4, 2026")

    def test_party_from_config_accepts_list_or_multiline(self) -> None:
        listed = document.party_from_config(
            {"name": "Acme", "address": ["1 Main", "Portland"], "email": "ops@acme.test"}
        )
        self.assertEqual(listed["address"], ["1 Main", "Portland"])
        block = document.party_from_config({"name": "Acme", "address": "1 Main\n\nPortland\n"})
        self.assertEqual(block["address"], ["1 Main", "Portland"])
        self.assertEqual(document.party_from_config(None)["name"], "")


class BuildDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed(self) -> None:
        with db.session() as conn:
            db.upsert_entry(
                conn,
                {
                    "vendor": "anthropic",
                    "source": "anthropic_t0",
                    "message_id": "m1",
                    "request_id": "r1",
                    "project": "acme/one",
                    "model": "claude-sonnet-4-6",
                    "occurred_at": "2026-09-02T00:00:00Z",
                    "input_tokens": 1000,
                    "output_tokens": 400,
                    "tier": "T0",
                },
            )

    def test_estimate_has_qty_rate_and_no_reconciliation(self) -> None:
        self._seed()
        doc = document.build_document(
            summarize("2026-09"),
            now=datetime(2026, 9, 14, tzinfo=timezone.utc),
        )
        self.assertEqual(doc["title"], "Statement")
        self.assertEqual(doc["from"]["name"], "Ardoise")
        self.assertFalse(doc["invoice_grade"])
        self.assertFalse(doc["totals"]["show_reconciliation"])
        group = doc["groups"][0]
        self.assertEqual(group["vendor"], "anthropic")
        self.assertEqual(group["period_label"], "Sep 1, 2026 – Sep 30, 2026")
        meters = group["models"][0]["lines"]
        kinds = {row["description"] for row in meters}
        self.assertIn("Input tokens", kinds)
        self.assertTrue(any(row.get("quantity") for row in meters))
        self.assertTrue(any("/ MTok" in str(row.get("rate_label")) for row in meters))
        self.assertNotIn("Amount due", str(doc))
        self.assertNotIn("Trivelta", str(doc))
        written = write_statement("2026-09")
        html = Path(written["html"]).read_text(encoding="utf-8")
        md = Path(written["md"]).read_text(encoding="utf-8")
        self.assertIn("$0.0090", html)
        self.assertNotIn(">$0.01<", html)
        self.assertIn('badge badge-estimate">Estimate<', html)
        self.assertNotIn('badge badge-billed">', html)
        self.assertIn("Print statement", html)
        self.assertIn("Copy totals into your invoice", html)
        self.assertIn("| Truth | Estimate |", md)
        self.assertNotIn("Invoice client", html)
        self.assertNotIn("invoice-grade", html)

    def test_invoice_grade_adds_adjustment_and_totals(self) -> None:
        self._seed()
        invoice.paste(path=ROOT / "tests" / "fixtures" / "invoices.jsonl")
        doc = document.build_document(summarize("2026-09"))
        self.assertTrue(doc["invoice_grade"])
        self.assertEqual(doc["total_usd"], 21.05)
        self.assertTrue(doc["totals"]["show_reconciliation"])
        self.assertAlmostEqual(doc["totals"]["total_usd"], 21.05, places=2)
        self.assertGreater(abs(float(doc["totals"]["adjustment_usd"])), 1)
        vendors = {row["vendor"] for row in doc["groups"]}
        self.assertEqual(vendors, {"anthropic", "cursor"})
        self.assertTrue(any(row.get("adjustment") for row in doc["groups"]))

    def test_html_print_floor_and_section_period(self) -> None:
        self._seed()
        invoice.paste(path=ROOT / "tests" / "fixtures" / "invoices.jsonl")
        html = Path(write_statement("2026-09")["html"]).read_text(encoding="utf-8")
        self.assertIn("Spend statement", html)
        self.assertIn("group-period", html)
        self.assertIn("tbody class=\"section\"", html)
        self.assertIn("table-header-group", html)
        self.assertIn("table-footer-group", html)
        self.assertIn("@page", html)
        self.assertIn("counter(page)", html)
        self.assertIn("List price", html)
        self.assertIn("Reconciling adjustment", html)
        self.assertIn("<tfoot>", html)
        self.assertIn('badge badge-billed">Billed<', html)
        self.assertNotIn('badge badge-estimate">', html)
        self.assertIn("Print statement", html)
        self.assertIn("Copy totals into your invoice", html)
        self.assertNotIn("Invoice client", html)
        self.assertNotIn("invoice-grade", html)
        self.assertNotIn("Amount due", html)
        self.assertNotIn("#fffbeb", html)
