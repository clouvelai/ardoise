#!/usr/bin/env python3
"""Soft budgets, anomaly flags, and daily_ready shape."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import alerts, budget, db, statement as statement_mod  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.status import render_text, summarize  # noqa: E402

FIXTURES = json.loads((ROOT / "tests" / "fixtures" / "alerts.json").read_text(encoding="utf-8"))


_HOME_KEYS = (
    "HOME",
    "ARDOISE_HOME",
    "ARDOISE_LEDGER",
    "ARDOISE_QUEUE",
    "ARDOISE_STATEMENTS",
    "ARDOISE_BUDGETS",
)


class IsolatedHomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_env = {key: os.environ.get(key) for key in _HOME_KEYS}
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS", "ARDOISE_BUDGETS"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()


class BudgetStoreTests(IsolatedHomeTests):
    def test_upsert_list_idempotent(self) -> None:
        first = budget.upsert(period="monthly", metric="usd", limit=50)
        self.assertEqual(first["result"], "inserted")
        self.assertEqual(first["id"], "month:usd")
        self.assertEqual(first["period"], "month")
        again = budget.upsert(period="month", metric="usd", limit=40)
        self.assertEqual(again["result"], "updated")
        self.assertEqual(again["limit"], 40)
        rows = budget.load()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["limit"], 40)
        budget.upsert(period="day", metric="tokens", limit=1000)
        ids = [row["id"] for row in budget.load()]
        self.assertEqual(ids, ["day:tokens", "month:usd"])

    def test_corrupt_file_is_empty_not_fatal(self) -> None:
        path = Path(os.environ["ARDOISE_HOME"]) / "budgets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not-json", encoding="utf-8")
        self.assertEqual(budget.load(), [])

    def test_evaluate_states(self) -> None:
        caps = [{"period": "month", "metric": "usd", "limit": 50}]
        ok = budget.evaluate(
            caps,
            used_usd_month=10,
            used_usd_day=1,
            used_tokens_month=0,
            used_tokens_day=0,
            usd_basis="billed",
        )[0]
        self.assertEqual(ok["state"], "ok")
        self.assertAlmostEqual(ok["remaining"], 40)
        warn = budget.evaluate(
            caps,
            used_usd_month=40,
            used_usd_day=1,
            used_tokens_month=0,
            used_tokens_day=0,
            usd_basis="billed",
        )[0]
        self.assertEqual(warn["state"], "warn")
        over = budget.evaluate(
            caps,
            used_usd_month=50,
            used_usd_day=1,
            used_tokens_month=0,
            used_tokens_day=0,
            usd_basis="billed",
        )[0]
        self.assertEqual(over["state"], "over")
        self.assertAlmostEqual(over["remaining"], 0)


class AnomalyTests(unittest.TestCase):
    def test_day_spike_from_fixture(self) -> None:
        flags = alerts.detect_anomalies(FIXTURES["day_spike"], month="2026-08")
        kinds = [item["kind"] for item in flags]
        self.assertIn("day_spike", kinds)
        spike = next(item for item in flags if item["kind"] == "day_spike")
        self.assertEqual(spike["detail"]["day"], "2026-08-08")
        self.assertGreaterEqual(spike["detail"]["ratio"], 3.0)
        self.assertEqual(spike["detail"]["prior_days"], 4)

    def test_session_outlier_from_fixture(self) -> None:
        flags = alerts.detect_anomalies(FIXTURES["session_outlier"], month="2026-08")
        kinds = [item["kind"] for item in flags]
        self.assertEqual(kinds, ["session_outlier"])
        self.assertEqual(flags[0]["detail"]["session_id"], "delta")
        self.assertGreaterEqual(flags[0]["detail"]["ratio"], 3.0)

    def test_quiet_fixture_has_no_flags(self) -> None:
        flags = alerts.detect_anomalies(FIXTURES["quiet"], month="2026-08")
        self.assertEqual(flags, [])

    def test_insufficient_baseline_is_quiet(self) -> None:
        lines = [
            {"occurred_at": "2026-08-01T00:00:00Z", "cost_usd": 1.0, "session_id": "a", "message_id": "a"},
            {"occurred_at": "2026-08-08T00:00:00Z", "cost_usd": 9.0, "session_id": "b", "message_id": "b"},
        ]
        self.assertEqual(alerts.detect_anomalies(lines, month="2026-08"), [])

    def test_below_min_usd_is_quiet(self) -> None:
        lines = [
            {"occurred_at": f"2026-08-0{d}T00:00:00Z", "cost_usd": 0.01, "session_id": f"s{d}", "message_id": f"m{d}"}
            for d in range(1, 6)
        ]
        lines.append(
            {
                "occurred_at": "2026-08-08T00:00:00Z",
                "cost_usd": 0.04,
                "session_id": "spike",
                "message_id": "ms",
            }
        )
        self.assertEqual(alerts.detect_anomalies(lines, month="2026-08"), [])


class DailyReadyTests(unittest.TestCase):
    def test_shape_and_budget_flag(self) -> None:
        payload = alerts.daily_ready(
            month="2026-08",
            lines=FIXTURES["day_spike"],
            budgets=[{"period": "month", "metric": "usd", "limit": 2.0}],
            billed_usd=0,
            estimated_usd=8.0,
            invoice_grade=False,
            as_of=datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(payload["schema"], alerts.DAILY_READY_SCHEMA)
        self.assertEqual(payload["month"], "2026-08")
        self.assertEqual(payload["day"], "2026-08-08")
        self.assertEqual(payload["as_of"], "2026-08-08T18:00:00Z")
        self.assertEqual(len(payload["budgets"]), 1)
        self.assertEqual(payload["budgets"][0]["state"], "over")
        kinds = {item["kind"] for item in payload["flags"]}
        self.assertIn("budget_over", kinds)
        self.assertIn("day_spike", kinds)

    def test_monthly_usd_prefers_invoice_grade(self) -> None:
        payload = alerts.daily_ready(
            month="2026-09",
            lines=[],
            budgets=[{"period": "month", "metric": "usd", "limit": 50}],
            billed_usd=21.05,
            estimated_usd=0.02,
            invoice_grade=True,
            as_of=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        row = payload["budgets"][0]
        self.assertEqual(row["basis"], "billed")
        self.assertAlmostEqual(row["used"], 21.05)
        self.assertEqual(row["state"], "ok")


class StatusAndStatementTests(IsolatedHomeTests):
    def _seed_spike(self) -> None:
        with db.session() as conn:
            for row in FIXTURES["day_spike"]:
                db.upsert_entry(
                    conn,
                    {
                        "vendor": "anthropic",
                        "source": "anthropic_t0",
                        "message_id": row["message_id"],
                        "request_id": row["request_id"],
                        "project": "acme/one",
                        "model": "claude-haiku-4-5",
                        "occurred_at": row["occurred_at"],
                        "input_tokens": int(row.get("input_tokens") or 0),
                        "output_tokens": int(row.get("output_tokens") or 0),
                        "cost_usd": row["cost_usd"],
                        "session_id": row["session_id"],
                        "tier": "T0",
                    },
                )

    def test_status_shows_budget_and_anomaly(self) -> None:
        self._seed_spike()
        budget.upsert(period="month", metric="usd", limit=2.0)
        data = summarize("2026-08", now=datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc))
        self.assertTrue(data["ok"])
        self.assertEqual(data["daily_ready"]["schema"], alerts.DAILY_READY_SCHEMA)
        self.assertEqual(data["budgets"][0]["state"], "over")
        kinds = {item["kind"] for item in data["flags"]}
        self.assertIn("budget_over", kinds)
        self.assertIn("day_spike", kinds)
        text = render_text(data)
        self.assertIn("budget   month usd", text)
        self.assertIn("over", text)
        self.assertIn("alerts", text)
        self.assertIn("day_spike", " ".join(item["kind"] for item in data["flags"]))

    def test_statement_alerts_strip_skips_section_a_clutter(self) -> None:
        self._seed_spike()
        budget.upsert(period="month", metric="usd", limit=2.0)
        written = statement_mod.write_statement("2026-08")
        md = Path(written["md"]).read_text(encoding="utf-8")
        html = Path(written["html"]).read_text(encoding="utf-8")
        self.assertIn("## Alerts", md)
        self.assertIn("Soft budgets and anomaly flags", md)
        self.assertIn("2026-08-08", md)
        self.assertIn('aria-label="Alerts"', html)
        self.assertIn("A. Vendor lines", md)
        a_idx = md.index("## A. Vendor lines")
        self.assertLess(md.index("## Alerts"), a_idx)
        section_a = md[a_idx : md.index("## B.")]
        self.assertNotIn("day_spike", section_a)
        self.assertNotIn("budget_over", section_a)

    def test_status_zero_without_budgets_is_quiet(self) -> None:
        data = summarize("2026-08")
        self.assertEqual(data["budgets"], [])
        self.assertEqual(data["flags"], [])
        text = render_text(data)
        self.assertNotIn("budget   ", text)
        self.assertNotIn("alerts   ", text)


class BudgetCliTests(IsolatedHomeTests):
    def test_set_list_and_status_never_block(self) -> None:
        with patch("sys.stdout", new=StringIO()) as out:
            rc = cli_main(["budget", "set", "--period", "month", "--usd", "0.01", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["result"], "inserted")
        with patch("sys.stdout", new=StringIO()) as out:
            rc = cli_main(["budget", "list", "--json"])
        self.assertEqual(rc, 0)
        listed = json.loads(out.getvalue())
        self.assertEqual(listed["budgets"][0]["limit"], 0.01)
        with db.session() as conn:
            db.upsert_entry(
                conn,
                {
                    "source": "anthropic_t0",
                    "message_id": "cli1",
                    "request_id": "cli1",
                    "occurred_at": "2026-09-02T00:00:00Z",
                    "input_tokens": 1000,
                    "output_tokens": 400,
                    "model": "claude-sonnet-4-6",
                    "cost_usd": 12.0,
                },
            )
        with patch("sys.stdout", new=StringIO()) as out:
            rc = cli_main(["status", "--json", "--month", "2026-09"])
        self.assertEqual(rc, 0)
        status = json.loads(out.getvalue())
        self.assertEqual(status["budgets"][0]["state"], "over")
        self.assertTrue(any(item["kind"] == "budget_over" for item in status["flags"]))

    def test_set_rejects_both_metrics(self) -> None:
        with patch("sys.stderr", new=StringIO()) as err:
            rc = cli_main(["budget", "set", "--period", "day", "--usd", "1", "--tokens", "2"])
        self.assertEqual(rc, 2)
        self.assertIn("exactly one", err.getvalue())


if __name__ == "__main__":
    unittest.main()
