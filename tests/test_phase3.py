#!/usr/bin/env python3
"""Phase 3: soft caps, anomaly notes, per-session estimate stub."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import anomaly, budget, config as config_mod, db  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.estimate import from_stdin, price_ask  # noqa: E402
from ardoise.statement import write_statement  # noqa: E402
from ardoise.status import render_text, summarize  # noqa: E402


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS", "ARDOISE_CONFIG"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_config(self, payload: dict) -> Path:
        home = Path(os.environ["ARDOISE_HOME"])
        home.mkdir(parents=True, exist_ok=True)
        path = home / "config.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _entry(
        self,
        conn: sqlite3.Connection,
        *,
        mid: str,
        day: str,
        cost: float,
        project: str = "acme/one",
        person: str = "",
        input_tokens: int = 1,
        output_tokens: int = 1,
    ) -> None:
        db.upsert_entry(
            conn,
            {
                "vendor": "anthropic",
                "source": "anthropic_t0",
                "message_id": mid,
                "request_id": f"r-{mid}",
                "project": project,
                "person": person,
                "model": "claude-sonnet-4-6",
                "occurred_at": f"{day}T12:00:00Z",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
                "tier": "T0",
            },
        )


class ConfigTests(IsolatedHome):
    def test_missing_config_is_empty(self) -> None:
        cfg = config_mod.load()
        self.assertFalse(cfg["loaded"])
        self.assertFalse(config_mod.has_soft_caps(cfg))
        self.assertEqual(cfg["anomalies"]["day_multiple"], 3.0)

    def test_invalid_json_does_not_raise(self) -> None:
        path = self._write_config({"budgets": {"monthly_usd": 10}})
        path.write_text("{not-json", encoding="utf-8")
        cfg = config_mod.load()
        self.assertFalse(config_mod.has_soft_caps(cfg))
        self.assertIn("invalid JSON", cfg["load_error"] or "")

    def test_parses_person_and_project_caps(self) -> None:
        self._write_config(
            {
                "budgets": {
                    "monthly_usd": 100,
                    "person": {"default": 80, "alice": 40},
                    "project": {"clouvelai/ardoise": 25},
                }
            }
        )
        cfg = config_mod.load()
        self.assertTrue(config_mod.has_soft_caps(cfg))
        self.assertEqual(cfg["budgets"]["monthly_usd"], 100)
        self.assertEqual(cfg["budgets"]["person"][""], 80)
        self.assertEqual(cfg["budgets"]["person"]["alice"], 40)
        self.assertEqual(cfg["budgets"]["project"]["clouvelai/ardoise"], 25)


class BudgetTests(IsolatedHome):
    def test_status_json_vs_cap_and_over_flag(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="m1", day="2026-09-02", cost=12.0, project="acme/one")
            self._entry(conn, mid="m2", day="2026-09-03", cost=8.0, project="acme/two")
        self._write_config(
            {
                "budgets": {
                    "monthly_usd": 10,
                    "person": {"": 5},
                    "project": {"acme/one": 5},
                }
            }
        )
        data = summarize("2026-09")
        self.assertTrue(data["budgets"]["configured"])
        self.assertTrue(data["budgets"]["over_cap"])
        self.assertFalse(data["budgets"]["blocks"])
        kinds = {row["kind"]: row for row in data["budgets"]["checks"]}
        self.assertAlmostEqual(kinds["month"]["pct"], 200.0, places=1)
        self.assertTrue(kinds["month"]["over"])
        self.assertTrue(kinds["project"]["over"])
        self.assertTrue(kinds["person"]["over"])
        text = render_text(data)
        self.assertIn("OVER", text)
        self.assertIn("never blocks", text)
        self.assertIn("200%", text)

    def test_under_cap_shows_pct_without_over(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="m1", day="2026-09-02", cost=2.0)
        self._write_config({"budgets": {"monthly_usd": 20}})
        data = summarize("2026-09")
        check = data["budgets"]["checks"][0]
        self.assertFalse(check["over"])
        self.assertAlmostEqual(check["pct"], 10.0, places=1)
        self.assertFalse(data["budgets"]["over_cap"])
        self.assertEqual(data["notes"], [])
        self.assertIn("10%", render_text(data))
        self.assertNotIn("OVER", render_text(data))

    def test_status_exit_zero_when_over_cap(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="m1", day="2026-09-02", cost=9.0)
        self._write_config({"budgets": {"monthly_usd": 1}})
        rc = cli_main(["status", "--json", "--month", "2026-09"])
        self.assertEqual(rc, 0)

    def test_prefers_billed_truth_for_month_cap(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="m1", day="2026-09-02", cost=0.05)
            db.upsert_invoice(
                conn,
                {
                    "vendor": "anthropic",
                    "person": "",
                    "cycle": "2026-09",
                    "invoice_id": "inv_cap",
                    "billed_cents": 2105,
                },
            )
        self._write_config({"budgets": {"monthly_usd": 10}})
        data = summarize("2026-09")
        self.assertEqual(data["budgets"]["basis"], "billed")
        self.assertAlmostEqual(data["budgets"]["spent_usd"], 21.05, places=2)
        self.assertTrue(data["budgets"]["over_cap"])


class AnomalyTests(IsolatedHome):
    def test_day_spend_above_trailing_median(self) -> None:
        with db.session() as conn:
            for i in range(1, 6):
                self._entry(conn, mid=f"d{i}", day=f"2026-09-0{i}", cost=2.0)
            self._entry(conn, mid="spike", day="2026-09-06", cost=20.0)
        data = summarize("2026-09")
        kinds = [item["kind"] for item in data["anomalies"]]
        self.assertIn("day_spend_spike", kinds)
        spike = next(item for item in data["anomalies"] if item["kind"] == "day_spend_spike")
        self.assertEqual(spike["day"], "2026-09-06")
        self.assertGreater(spike["multiple"], 3)
        self.assertTrue(any("2026-09-06" in note for note in data["notes"]))
        written = write_statement("2026-09")
        md = Path(written["md"]).read_text(encoding="utf-8")
        self.assertIn("Notes (soft)", md)
        self.assertIn("never block", md)
        self.assertIn("2026-09-06", md)

    def test_quiet_days_do_not_flag(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="a", day="2026-09-01", cost=0.02)
            self._entry(conn, mid="b", day="2026-09-02", cost=0.03)
        data = summarize("2026-09")
        self.assertEqual(data["anomalies"], [])

    def test_project_share_spike(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="big", day="2026-09-02", cost=9.0, project="acme/one")
            self._entry(conn, mid="sml", day="2026-09-03", cost=1.0, project="acme/two")
        data = summarize("2026-09")
        shares = [item for item in data["anomalies"] if item["kind"] == "project_share_spike"]
        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0]["project"], "acme/one")
        self.assertGreaterEqual(shares[0]["share"], 0.75)
        html = Path(write_statement("2026-09")["html"]).read_text(encoding="utf-8")
        self.assertIn("acme/one", html)
        self.assertIn("Notes (soft)", html)

    def test_single_project_is_not_a_share_spike(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="only", day="2026-09-02", cost=12.0, project="acme/one")
        flags = anomaly.scan(None, month="2026-09", lines=summarize("2026-09")["lines"])
        self.assertFalse(any(item["kind"] == "project_share_spike" for item in flags))


class EstimateTests(IsolatedHome):
    def test_prices_from_table(self) -> None:
        data = price_ask(
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=400,
            with_gate=False,
        )
        self.assertTrue(data["ok"])
        self.assertFalse(data["blocks"])
        self.assertAlmostEqual(data["usd"], 0.009, places=6)

    def test_cli_json_and_stdin(self) -> None:
        rc = cli_main(
            [
                "estimate",
                "--model",
                "claude-sonnet-4-6",
                "--input-tokens",
                "1000",
                "--output-tokens",
                "400",
                "--json",
            ]
        )
        self.assertEqual(rc, 0)
        payload = json.dumps(
            {"model": "claude-haiku-4-5", "input_tokens": 500, "output_tokens": 100}
        )
        with patch("sys.stdin", io.StringIO(payload)):
            rc = cli_main(["estimate", "--stdin", "--json"])
        self.assertEqual(rc, 0)

    def test_bad_stdin_still_exits_zero(self) -> None:
        data = from_stdin(io.StringIO("not-json"))
        self.assertFalse(data["ok"])
        self.assertFalse(data["blocks"])
        with patch("sys.stdin", io.StringIO("")):
            self.assertEqual(cli_main(["estimate", "--stdin", "--json"]), 0)

    def test_gate_stub_never_blocks_when_over_cap(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="m1", day="2026-09-02", cost=9.0)
        self._write_config({"budgets": {"monthly_usd": 1}})
        data = price_ask(model="claude-sonnet-4-6", input_tokens=1000, output_tokens=400, month="2026-09")
        self.assertFalse(data["blocks"])
        self.assertFalse(data["gate"]["blocks"])
        self.assertEqual(data["gate"]["mode"], "stub")
        self.assertTrue(data["gate"]["would_exceed_soft_cap"])

    def test_status_estimate_flag(self) -> None:
        rc = cli_main(["status", "--json", "--month", "2026-09", "--estimate"])
        self.assertEqual(rc, 0)


class StatementNotesTests(IsolatedHome):
    def test_statement_includes_soft_cap_note(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="m1", day="2026-09-02", cost=4.0, project="acme/one")
            self._entry(conn, mid="m2", day="2026-09-03", cost=1.0, project="acme/two")
        self._write_config({"budgets": {"monthly_usd": 2, "project": {"acme/one": 1}}})
        written = write_statement("2026-09")
        md = Path(written["md"]).read_text(encoding="utf-8")
        csv_text = Path(written["csv"]).read_text(encoding="utf-8")
        self.assertIn("Notes (soft)", md)
        self.assertIn("over (warn only", md)
        self.assertIn("notes", csv_text)
        self.assertNotIn("Trivelta", md)


class MonthSpendTests(IsolatedHome):
    def test_month_spend_estimated_without_invoice(self) -> None:
        summary = {"section_a": [], "billed_usd": 0, "estimated_usd": 1.25, "cost_usd": 1.25}
        spent, basis = budget.month_spend(summary)
        self.assertEqual(basis, "estimated")
        self.assertAlmostEqual(spent, 1.25)


if __name__ == "__main__":
    unittest.main()
