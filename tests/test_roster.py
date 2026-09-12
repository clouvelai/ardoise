#!/usr/bin/env python3
"""Phase 3: view-only roster / seat / person filters."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import config as config_mod, db, invoice, roster  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
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
        person: str,
        project: str,
        vendor: str = "anthropic",
        source: str = "anthropic_t0",
        cost: float = 1.0,
        day: str = "2026-09-02",
        billed_cents: int | None = None,
        tier: str = "T0",
    ) -> None:
        db.upsert_entry(
            conn,
            {
                "vendor": vendor,
                "source": source,
                "message_id": mid,
                "request_id": f"r-{mid}",
                "project": project,
                "person": person,
                "model": "claude-sonnet-4-6",
                "occurred_at": f"{day}T12:00:00Z",
                "input_tokens": 100,
                "output_tokens": 40,
                "cost_usd": cost,
                "tier": tier,
                "billed_cents": billed_cents,
            },
        )

    def _seed_multi_seat(self) -> None:
        with db.session() as conn:
            self._entry(conn, mid="alice-a", person="alice", project="acme/one", cost=2.0)
            self._entry(conn, mid="alice-b", person="alice", project="acme/two", cost=1.0, day="2026-09-03")
            self._entry(
                conn,
                mid="bob-a",
                person="bob",
                project="acme/ops",
                vendor="cursor",
                source="cursor",
                cost=0.5,
            )
            self._entry(conn, mid="org-a", person="", project="acme/shared", cost=0.25)
            db.upsert_snapshot(
                conn,
                {
                    "vendor": "anthropic",
                    "person": "alice",
                    "cycle": "2026-09",
                    "as_of": "2026-09-15T00:00:00Z",
                    "billed_cents": 800,
                    "tier": "T1",
                },
            )
        result = invoice.paste(path=ROOT / "tests" / "fixtures" / "multi_seat_invoices.jsonl")
        self.assertEqual(result["inserted"], 3)
        # Idempotent re-paste must not grow the table.
        again = invoice.paste(path=ROOT / "tests" / "fixtures" / "multi_seat_invoices.jsonl")
        self.assertEqual(again["inserted"], 0)
        self.assertEqual(again["updated"], 3)


class ConfigRosterTests(IsolatedHome):
    def test_parses_list_and_alias_map(self) -> None:
        self._write_config({"roster": ["alice", "bob"]})
        cfg = config_mod.load()
        self.assertEqual(set(cfg["roster"]), {"alice", "bob"})
        self._write_config({"roster": {"alice": ["alice@acme.com"], "default": ["org"]}})
        cfg = config_mod.load()
        self.assertEqual(cfg["roster"]["alice"], ["alice@acme.com"])
        self.assertEqual(cfg["roster"][""], ["org"])


class FilterTests(IsolatedHome):
    def test_includes_one_seat_and_excludes_others(self) -> None:
        self._seed_multi_seat()
        full = summarize("2026-09")
        self.assertGreaterEqual(len(full["section_a"]), 3)
        people = {row["person"] for row in full["section_a"]}
        self.assertEqual(people, {"alice", "bob", ""})
        self.assertAlmostEqual(full["billed_usd"], 64.99, places=2)

        alice = summarize("2026-09", person="alice")
        self.assertEqual({row["person"] for row in alice["section_a"]}, {"alice"})
        self.assertTrue(all(row.get("person") == "alice" for row in alice["lines"]))
        self.assertAlmostEqual(alice["billed_usd"], 40.0, places=2)
        self.assertEqual(alice["month_entries"], 2)
        self.assertEqual(alice["entries"], full["entries"])
        self.assertTrue(alice["filter"]["view_only"])
        self.assertNotIn("bob", json.dumps(alice["section_a"]))
        self.assertNotIn("bob", json.dumps(alice["lines"]))

        bob = summarize("2026-09", person="BOB")
        self.assertEqual({row["person"] for row in bob["section_a"]}, {"bob"})
        self.assertAlmostEqual(bob["billed_usd"], 15.0, places=2)
        self.assertEqual(bob["month_entries"], 1)

        unnamed = summarize("2026-09", person="default")
        self.assertEqual({row["person"] for row in unnamed["section_a"]}, {""})
        self.assertAlmostEqual(unnamed["billed_usd"], 9.99, places=2)

    def test_unknown_seat_is_empty_soft_note_exit_zero(self) -> None:
        self._seed_multi_seat()
        before = summarize("2026-09")
        data = summarize("2026-09", person="nobody")
        self.assertEqual(data["section_a"], [])
        self.assertEqual(data["lines"], [])
        self.assertEqual(data["billed_usd"], 0)
        self.assertTrue(any("nobody" in note for note in data["notes"]))
        self.assertTrue(any("view only" in note for note in data["notes"]))
        self.assertEqual(data["entries"], before["entries"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["status", "--json", "--month", "2026-09", "--person", "nobody"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["section_a"], [])

    def test_config_alias_resolves_to_canonical(self) -> None:
        with db.session() as conn:
            self._entry(
                conn,
                mid="alias-1",
                person="alice@acme.com",
                project="acme/one",
                cost=3.0,
            )
            db.upsert_invoice(
                conn,
                {
                    "vendor": "anthropic",
                    "cycle": "2026-09",
                    "person": "alice@acme.com",
                    "usd_cents": 2500,
                    "source": "paste",
                },
            )
        self._write_config({"roster": {"alice": ["alice@acme.com"]}})
        data = summarize("2026-09", person="alice")
        self.assertEqual(data["filter"]["canonical"], "alice")
        self.assertTrue(data["filter"]["matched"])
        self.assertEqual(len(data["section_a"]), 1)
        self.assertEqual(data["section_a"][0]["person"], "alice@acme.com")
        self.assertAlmostEqual(data["billed_usd"], 25.0, places=2)
        names = [row["person"] for row in data["roster"]]
        self.assertIn("alice", names)
        self.assertNotIn("alice@acme.com", names)

    def test_status_text_lists_roster_and_filter(self) -> None:
        self._seed_multi_seat()
        text = render_text(summarize("2026-09"))
        self.assertIn("roster", text)
        self.assertIn("alice", text)
        self.assertIn("bob", text)
        filtered = render_text(summarize("2026-09", person="alice"))
        self.assertIn("filter   alice", filtered)
        self.assertIn("view only", filtered)
        self.assertIn("by person", filtered)


class StatementFilterTests(IsolatedHome):
    def test_md_html_csv_respect_filter_and_stay_sparse(self) -> None:
        self._seed_multi_seat()
        written = write_statement("2026-09", person="alice")
        self.assertIn("2026-09--alice.md", written["md"])
        md = Path(written["md"]).read_text(encoding="utf-8")
        html = Path(written["html"]).read_text(encoding="utf-8")
        csv_text = Path(written["csv"]).read_text(encoding="utf-8")
        for blob in (md, html, csv_text):
            self.assertIn("alice", blob)
            self.assertNotIn("bob", blob)
            self.assertNotIn("inv_bob", blob)
            self.assertNotIn("acme/ops", blob)
            self.assertNotIn("Trivelta", blob)
        self.assertIn("Seat **alice**", md)
        self.assertIn("view only", md)
        self.assertIn("badge seat", html)
        self.assertIn("view only", html)
        self.assertNotIn("roster table", html.lower())
        self.assertLess(html.lower().count("<table"), 3)
        self.assertIn("seat filter alice", csv_text)
        self.assertIn("A_vendor", csv_text)
        org = write_statement("2026-09")
        self.assertTrue(org["md"].endswith("2026-09.md"))
        org_md = Path(org["md"]).read_text(encoding="utf-8")
        self.assertIn("alice", org_md)
        self.assertIn("bob", org_md)

    def test_statement_rerun_is_idempotent(self) -> None:
        self._seed_multi_seat()
        first = write_statement("2026-09", person="alice")
        md1 = Path(first["md"]).read_text(encoding="utf-8")
        html1 = Path(first["html"]).read_text(encoding="utf-8")
        csv1 = Path(first["csv"]).read_text(encoding="utf-8")
        with db.session() as conn:
            events = db.count_entries(conn)
            invoices = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        second = write_statement("2026-09", person="alice")
        self.assertEqual(first["md"], second["md"])
        self.assertEqual(md1, Path(second["md"]).read_text(encoding="utf-8"))
        self.assertEqual(html1, Path(second["html"]).read_text(encoding="utf-8"))
        self.assertEqual(csv1, Path(second["csv"]).read_text(encoding="utf-8"))
        with db.session() as conn:
            self.assertEqual(db.count_entries(conn), events)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], invoices)

    def test_cli_aliases_do_not_write_ledger(self) -> None:
        self._seed_multi_seat()
        with db.session() as conn:
            before = db.count_entries(conn)
        out_dir = Path(os.environ["ARDOISE_HOME"]) / "statements"
        for flag in ("--person", "--seat", "--roster"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["status", "--json", "--month", "2026-09", flag, "alice"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["filter"]["canonical"], "alice")
            self.assertAlmostEqual(payload["billed_usd"], 40.0, places=2)
            stmt = io.StringIO()
            with redirect_stdout(stmt):
                rc = cli_main(["statement", "2026-09", flag, "alice", "--out-dir", str(out_dir)])
            self.assertEqual(rc, 0)
            written = json.loads(stmt.getvalue())
            self.assertTrue(written["md"].endswith("2026-09--alice.md"))
        with db.session() as conn:
            self.assertEqual(db.count_entries(conn), before)


class RosterUnitTests(unittest.TestCase):
    def test_fold_and_slug(self) -> None:
        self.assertEqual(roster.fold("Default"), "")
        self.assertEqual(roster.fold("Alice"), "alice")
        self.assertEqual(roster.slug("alice@acme.com"), "alice@acme.com")
        self.assertEqual(roster.slug("Ada Lovelace"), "Ada-Lovelace")
        self.assertEqual(roster.statement_stem("2026-09", "alice"), "2026-09--alice")
        self.assertEqual(roster.statement_stem("2026-09", None), "2026-09")


if __name__ == "__main__":
    unittest.main()
