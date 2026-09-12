#!/usr/bin/env python3
"""Phase 2: adapter contract, invoices, tiers of truth, T0 allocation."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import db, invoice, reconcile  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.statement import write_statement  # noqa: E402
from ardoise.status import summarize  # noqa: E402
from ardoise.vendors import get_adapter, list_adapters  # noqa: E402
from ardoise.vendors.contract import CredentialNotConfigured, Event, Snapshot  # noqa: E402
from ardoise.vendors.creds import CHAIN, resolve_status  # noqa: E402


def _isolated_home() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory()


class ContractTests(unittest.TestCase):
    def test_adapters_expose_contract(self) -> None:
        for name in ("anthropic", "cursor"):
            adapter = get_adapter(name)
            self.assertTrue(adapter.name)
            self.assertTrue(adapter.tools)
            self.assertTrue(adapter.credential_spec.fields)
            caps = adapter.capabilities
            self.assertEqual(caps.capture, "yes")
            self.assertEqual(caps.test, "yes")
            result = adapter.test()
            self.assertIn(result.capabilities.capture, {"yes", "stub", "no"})
            self.assertFalse(result.cred_resolved)

    def test_event_snapshot_shapes(self) -> None:
        event = Event(
            vendor="anthropic",
            source="anthropic_t0",
            message_id="m",
            request_id="r",
            occurred_at="2026-09-01T00:00:00Z",
            billed_cents=None,
            tier="T0",
        )
        row = event.to_row()
        self.assertEqual(row["tier"], "T0")
        self.assertIn("input_tokens", row)
        self.assertIsNone(row["billed_cents"])
        snap = Snapshot(
            vendor="anthropic",
            cycle="2026-09",
            as_of="2026-09-30T00:00:00Z",
            billed_cents=1200,
            tier="T1",
        )
        self.assertEqual(snap.to_row()["billed_cents"], 1200)
        self.assertEqual(snap.to_row()["tier"], "T1")

    def test_t1_t2_stubs_raise_without_breaking_t0(self) -> None:
        anth = get_adapter("anthropic")
        cur = get_adapter("cursor")
        with self.assertRaises(CredentialNotConfigured) as ctx:
            anth.snapshot(cycle="2026-09")
        self.assertIn("credential not configured", str(ctx.exception))
        with self.assertRaises(CredentialNotConfigured):
            next(cur.pull(cycle="2026-09"))
        # T0 capture still iterates with no admin creds
        events = list(anth.capture(root=ROOT / "tests" / "missing-root"))
        self.assertEqual(events, [])

    def test_cred_chain_is_env_then_stubs(self) -> None:
        self.assertEqual(CHAIN, ("env", "op", "keychain"))
        adapter = get_adapter("anthropic")
        status = resolve_status(adapter.credential_spec)
        self.assertTrue(all(item.source is None for item in status))


class InvoiceAndReconcileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_t0(self, conn: sqlite3.Connection) -> None:
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
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "tier": "T0",
            },
        )
        db.upsert_entry(
            conn,
            {
                "vendor": "anthropic",
                "source": "anthropic_t0",
                "message_id": "m2",
                "request_id": "r2",
                "project": "acme/two",
                "model": "claude-haiku-4-5",
                "occurred_at": "2026-09-03T00:00:00Z",
                "input_tokens": 3000,
                "output_tokens": 0,
                "tier": "T0",
            },
        )

    def test_schema_tables(self) -> None:
        with db.session() as conn:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                )
            }
            for table in db.required_tables():
                self.assertIn(table, names)
            self.assertIn("entries", names)

    def test_invoice_paste_and_section_a(self) -> None:
        with db.session() as conn:
            self._seed_t0(conn)
        result = invoice.paste(path=ROOT / "tests" / "fixtures" / "invoices.jsonl")
        self.assertEqual(result["inserted"], 2)
        data = summarize("2026-09")
        self.assertAlmostEqual(data["cost_usd"], data["estimated_usd"])
        self.assertGreater(data["estimated_usd"], 0)
        tiers = {row["tier_of_truth"] for row in data["section_a"]}
        self.assertEqual(tiers, {"invoice"})
        billed = {row["vendor"]: row["billed_usd"] for row in data["section_a"]}
        self.assertAlmostEqual(billed["anthropic"], 19.50, places=2)
        self.assertAlmostEqual(billed["cursor"], 1.55, places=2)
        self.assertAlmostEqual(data["billed_usd"], 21.05, places=2)
        # T0 estimate is cents-scale list price, not the $21.05 invoice
        self.assertLess(data["estimated_usd"], 1.0)
        self.assertGreater(data["billed_usd"], data["estimated_usd"] * 10)

        written = write_statement("2026-09")
        md = Path(written["md"]).read_text(encoding="utf-8")
        html = Path(written["html"]).read_text(encoding="utf-8")
        csv_text = Path(written["csv"]).read_text(encoding="utf-8")
        for blob in (md, html, csv_text):
            self.assertIn("A", blob)
            self.assertIn("invoice", blob)
            self.assertIn("T0", blob)
            self.assertNotIn("Trivelta", blob)
        self.assertIn("A. Billed truth", md)
        self.assertIn("T0 allocation (not billed)", md)
        self.assertIn("19.50", md)
        self.assertIn("A_billed", csv_text)
        self.assertIn("T0_allocation", csv_text)

    def test_t0_is_not_section_a_without_invoice(self) -> None:
        with db.session() as conn:
            self._seed_t0(conn)
        data = summarize("2026-09")
        self.assertEqual(data["section_a"], [])
        self.assertEqual(data["billed_usd"], 0)
        self.assertGreater(data["cost_usd"], 0)
        written = write_statement("2026-09")
        md = Path(written["md"]).read_text(encoding="utf-8")
        self.assertIn("No invoice, T1 snapshot, or T2 billed events", md)
        self.assertIn("T0 allocation (not billed)", md)

    def test_prefer_invoice_over_t1_and_t2(self) -> None:
        with db.session() as conn:
            self._seed_t0(conn)
            db.upsert_entry(
                conn,
                {
                    "vendor": "anthropic",
                    "source": "anthropic_t2",
                    "message_id": "t2m",
                    "request_id": "t2r",
                    "occurred_at": "2026-09-04T00:00:00Z",
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "tier": "T2",
                    "billed_cents": 9999,
                },
            )
            db.upsert_snapshot(
                conn,
                {
                    "vendor": "anthropic",
                    "person": "",
                    "cycle": "2026-09",
                    "as_of": "2026-09-30T00:00:00Z",
                    "billed_cents": 5000,
                    "tier": "T1",
                },
            )
            db.upsert_invoice(
                conn,
                {
                    "vendor": "anthropic",
                    "person": "",
                    "cycle": "2026-09",
                    "invoice_id": "inv_win",
                    "billed_cents": 1234,
                },
            )
            billed = reconcile.billed_truth(conn, "anthropic", "", "2026-09")
            self.assertIsNotNone(billed)
            assert billed is not None
            self.assertEqual(billed.tier, "invoice")
            self.assertEqual(billed.billed_cents, 1234)

    def test_t1_when_no_invoice(self) -> None:
        with db.session() as conn:
            self._seed_t0(conn)
            db.upsert_snapshot(
                conn,
                {
                    "vendor": "anthropic",
                    "person": "",
                    "cycle": "2026-09",
                    "as_of": "2026-09-30T00:00:00Z",
                    "billed_cents": 400,
                    "tier": "T1",
                },
            )
            billed = reconcile.billed_truth(conn, "anthropic", "", "2026-09")
            rec = reconcile.reconcile(conn, "anthropic", "", "2026-09")
        self.assertEqual(billed.tier, "T1")
        self.assertEqual(rec.preferred_tier, "T1")
        alloc = sum(line.billed_cents or 0 for line in rec.lines)
        self.assertEqual(alloc, 400)
        # token share 1400 : 3000
        self.assertEqual(len(rec.lines), 2)

    def test_credentials_never_reach_ledger(self) -> None:
        with db.session() as conn:
            with self.assertRaises(ValueError):
                db.upsert_entry(
                    conn,
                    {
                        "source": "x",
                        "message_id": "m",
                        "request_id": "r",
                        "occurred_at": "2026-09-01T00:00:00Z",
                        "input_tokens": 1,
                        "api_key": "sk-secret",
                    },
                )
            with self.assertRaises(ValueError):
                db.upsert_invoice(
                    conn,
                    {
                        "vendor": "anthropic",
                        "cycle": "2026-09",
                        "invoice_id": "x",
                        "billed_cents": 1,
                        "api_key": "sk-secret",
                    },
                )


class VendorCliTests(unittest.TestCase):
    def test_vendor_test_lists_known(self) -> None:
        self.assertEqual(list_adapters(), ["anthropic", "cursor"])

    def test_cli_vendor_test(self) -> None:
        rc = cli_main(["vendor", "test", "anthropic", "--json"])
        self.assertEqual(rc, 0)


class NoTriveltaTests(unittest.TestCase):
    def test_no_trivelta_outside_pilots(self) -> None:
        # Guardrail: core/product trees only. tests/ may mention the banned name.
        roots = [ROOT / "ardoise", ROOT / "plugins", ROOT / "data", ROOT / "docs", ROOT / "bin"]
        extra = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "install.sh"]
        skip = {".git", "pilots", "__pycache__", "node_modules"}
        banned = "triv" + "elta"
        hits: list[str] = []
        files: list[Path] = [p for p in extra if p.is_file()]
        for root in roots:
            if not root.exists():
                continue
            files.extend(p for p in root.rglob("*") if p.is_file())
        for path in files:
            if any(part in skip for part in path.parts):
                continue
            if path.suffix.lower() not in {".py", ".md", ".sh", ".json", ".jsonl", ".txt", ""}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if banned in text.lower():
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
