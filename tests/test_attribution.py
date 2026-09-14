#!/usr/bin/env python3
"""Phase 3: attribute spend by agent / skill / effort when the transcript names them."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import attribution, db  # noqa: E402
from ardoise.adapters.hook_event import event_to_entry  # noqa: E402
from ardoise.privacy import usage_only_event  # noqa: E402
from ardoise.queue import enqueue  # noqa: E402
from ardoise.statement import write_statement  # noqa: E402
from ardoise.status import render_text, summarize  # noqa: E402
from ardoise.vendors.anthropic import parse_t0_line  # noqa: E402
from ardoise.vendors.cursor import parse_cursor_line  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "attribution_t0.jsonl"
HOOK = ROOT / "tests" / "fixtures" / "hook_event_attributed.json"


def _lines() -> list[dict]:
    rows = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line.replace("/WORKSPACE", str(ROOT))))
    return rows


class ExtractTests(unittest.TestCase):
    def test_claude_code_keys(self) -> None:
        found = attribution.extract(_lines()[0])
        self.assertEqual(found["agent"], "Explore")
        self.assertEqual(found["skill"], "session-retrospective")
        self.assertEqual(found["effort"], "high")

    def test_alias_and_nested_skill_object(self) -> None:
        found = attribution.extract(_lines()[1])
        self.assertEqual(found["agent"], "generalPurpose")
        self.assertEqual(found["skill"], "connect-recommend")
        self.assertEqual(found["effort"], "medium")

    def test_nested_attribution_object(self) -> None:
        found = attribution.extract(_lines()[2])
        self.assertEqual(found, {"agent": "bugbot", "skill": "stripe-docs", "effort": "low"})

    def test_missing_and_blank_stay_unattributed(self) -> None:
        found = attribution.extract(_lines()[3])
        self.assertEqual(found, {"agent": None, "skill": None, "effort": None})
        self.assertIsNone(attribution.extract({})["agent"])
        self.assertIsNone(attribution.extract(None)["agent"])

    def test_does_not_invent_from_prompt_text(self) -> None:
        raw = {
            "prompt": "Use the Explore agent and the foo skill at high effort",
            "content": "agent=Explore skill=foo effort=high",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        self.assertEqual(attribution.extract(raw), {"agent": None, "skill": None, "effort": None})

    def test_bot_name_and_model_params_effort(self) -> None:
        found = attribution.extract(
            {
                "botName": "captain",
                "model_params": [{"id": "effort", "value": "high"}],
            }
        )
        self.assertEqual(found["agent"], "captain")
        self.assertEqual(found["effort"], "high")

    def test_cloud_run_wrapper_does_not_use_job_title(self) -> None:
        found = attribution.extract(
            {
                "agent": {
                    "id": "bc-00000000-0000-0000-0000-000000000001",
                    "name": "Fix the billing success page",
                    "status": "FINISHED",
                    "env": {"type": "cloud"},
                }
            }
        )
        self.assertIsNone(found["agent"])
        named = attribution.extract(
            {
                "agent": {
                    "id": "bc-00000000-0000-0000-0000-000000000001",
                    "name": "Fix the billing success page",
                    "status": "FINISHED",
                    "env": {"type": "cloud"},
                    "agentName": "Craie",
                }
            }
        )
        self.assertEqual(named["agent"], "Craie")

    def test_rejects_secret_like_values(self) -> None:
        found = attribution.extract({"agent": "sk-ant-oat01-secret", "skill": "ok", "effort": "low"})
        self.assertIsNone(found["agent"])
        self.assertEqual(found["skill"], "ok")

    def test_parse_t0_and_cursor_lines(self) -> None:
        parsed = [parse_t0_line(obj) or parse_cursor_line(obj) for obj in _lines()]
        self.assertTrue(all(parsed))
        self.assertEqual(parsed[0]["agent"], "Explore")
        self.assertEqual(parsed[3]["agent"], None)
        self.assertEqual(parsed[3]["skill"], None)
        self.assertEqual(parsed[3]["effort"], None)
        self.assertEqual(parsed[4]["source"], "cursor")
        self.assertEqual(parsed[4]["agent"], "composer")
        self.assertEqual(parsed[4]["skill"], "stripe-apps")
        self.assertEqual(parsed[4]["effort"], "xhigh")

    def test_hook_payload_and_queue_keep_ids_drop_prompt(self) -> None:
        raw = json.loads(HOOK.read_text(encoding="utf-8"))
        safe = usage_only_event(raw)
        self.assertNotIn("prompt", safe)
        self.assertEqual(safe["agent"], "Explore")
        self.assertEqual(safe["skill"], "transcript-analysis")
        self.assertEqual(safe["effort"], "high")
        entry = event_to_entry(raw, default_source="hook")
        assert entry is not None
        self.assertEqual(entry["agent"], "Explore")
        self.assertEqual(entry["message_id"], "msg_hook_attr")
        with tempfile.TemporaryDirectory() as tmp:
            path = enqueue(raw, directory=Path(tmp))
            body = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("HOOK_SECRET_DO_NOT_STORE", path.read_text(encoding="utf-8"))
            self.assertEqual(body["agent"], "Explore")
            self.assertEqual(body["skill"], "transcript-analysis")


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in ("ARDOISE_LEDGER", "ARDOISE_QUEUE", "ARDOISE_STATEMENTS", "ARDOISE_CONFIG"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ingest(self) -> None:
        with db.session() as conn:
            for obj in _lines():
                entry = parse_t0_line(obj) or parse_cursor_line(obj)
                assert entry is not None
                db.upsert_entry(conn, entry)


class PersistAndStatusTests(IsolatedHome):
    def test_schema_adds_columns_and_entries_view(self) -> None:
        with db.session() as conn:
            ev = {str(row[1]) for row in conn.execute("PRAGMA table_info(events)")}
            for col in ("agent", "skill", "effort"):
                self.assertIn(col, ev)
            cols = [d[0] for d in conn.execute("SELECT * FROM entries LIMIT 0").description]
            for col in ("agent", "skill", "effort"):
                self.assertIn(col, cols)
            ver = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            self.assertEqual(str(ver[0]), "4")

    def test_upgrade_from_pre_v4_events(self) -> None:
        path = Path(os.environ["ARDOISE_HOME"]) / "legacy.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(str(path))
        raw.executescript(
            """
            CREATE TABLE events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              vendor TEXT NOT NULL DEFAULT 'unknown',
              source TEXT NOT NULL,
              person TEXT NOT NULL DEFAULT '',
              cycle TEXT NOT NULL DEFAULT '',
              message_id TEXT NOT NULL,
              request_id TEXT NOT NULL,
              project TEXT,
              model TEXT,
              occurred_at TEXT NOT NULL,
              input_tokens INTEGER NOT NULL DEFAULT 0,
              output_tokens INTEGER NOT NULL DEFAULT 0,
              cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
              cache_read_tokens INTEGER NOT NULL DEFAULT 0,
              cache_creation_5m_tokens INTEGER NOT NULL DEFAULT 0,
              cache_creation_1h_tokens INTEGER NOT NULL DEFAULT 0,
              billed_cents INTEGER,
              cost_usd REAL NOT NULL DEFAULT 0,
              tier TEXT NOT NULL DEFAULT 'T0',
              session_id TEXT,
              cwd TEXT,
              ingested_at TEXT NOT NULL,
              UNIQUE(message_id, request_id)
            );
            """
        )
        raw.commit()
        raw.close()
        conn = db.connect(path)
        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(events)")}
        self.assertTrue({"agent", "skill", "effort"} <= cols)
        conn.close()

    def test_persist_and_never_invent(self) -> None:
        self._ingest()
        with db.session() as conn:
            rows = {
                str(r["message_id"]): dict(r)
                for r in conn.execute("SELECT * FROM events").fetchall()
            }
        self.assertEqual(rows["msg_attr_aaa"]["agent"], "Explore")
        self.assertEqual(rows["msg_attr_aaa"]["skill"], "session-retrospective")
        self.assertEqual(rows["msg_attr_aaa"]["effort"], "high")
        self.assertIsNone(rows["msg_attr_ddd"]["agent"])
        self.assertIsNone(rows["msg_attr_ddd"]["skill"])
        self.assertIsNone(rows["msg_attr_ddd"]["effort"])
        self.assertEqual(rows["msg_attr_cur"]["agent"], "composer")

    def test_skip_fills_empty_attribution(self) -> None:
        with db.session() as conn:
            db.upsert_entry(
                conn,
                {
                    "source": "anthropic_t0",
                    "message_id": "m-fill",
                    "request_id": "r-fill",
                    "occurred_at": "2026-09-12T12:00:00Z",
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "cost_usd": 0.01,
                },
            )
            kind = db.upsert_entry(
                conn,
                {
                    "source": "anthropic_t0",
                    "message_id": "m-fill",
                    "request_id": "r-fill",
                    "occurred_at": "2026-09-12T12:00:00Z",
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "cost_usd": 0.01,
                    "agentId": "Explore",
                    "skill": "later-skill",
                    "effort": "low",
                },
            )
            self.assertEqual(kind, "skipped")
            row = conn.execute(
                "SELECT agent, skill, effort FROM events WHERE message_id = 'm-fill'"
            ).fetchone()
            self.assertEqual(row["agent"], "Explore")
            self.assertEqual(row["skill"], "later-skill")
            self.assertEqual(row["effort"], "low")

    def test_status_and_statement_quiet_breakdown(self) -> None:
        self._ingest()
        data = summarize("2026-09")
        agents = {row["agent"] for row in data["by_agent"]}
        self.assertIn("Explore", agents)
        self.assertIn(attribution.UNATTRIBUTED, agents)
        self.assertTrue(any(row["skill"] == "session-retrospective" for row in data["by_skill"]))
        text = render_text(data)
        self.assertIn("attribution (when present)", text)
        self.assertIn("Explore", text)
        self.assertNotIn("HOOK_SECRET", text)
        written = write_statement("2026-09")
        md = Path(written["md"]).read_text(encoding="utf-8")
        html = Path(written["html"]).read_text(encoding="utf-8")
        csv_text = Path(written["csv"]).read_text(encoding="utf-8")
        self.assertIn("## Attribution", md)
        self.assertIn("Explore", md)
        self.assertIn("session-retrospective", md)
        self.assertIn("## From", md)
        self.assertIn("| Description | Quantity | Rate | Amount |", md)
        # Attribution lives in its own section, not the Orb line table
        before_attr = md.split("## Attribution")[0]
        self.assertNotIn("Explore", before_attr)
        self.assertIn('section class="quiet"', html)
        self.assertIn("agent,skill,effort", csv_text.splitlines()[0])
        self.assertIn("Explore", csv_text)
        # Line table stays sparse — no attribution columns on meters
        table = html.split('<table class="lines">')[1].split("</table>")[0]
        self.assertNotIn("explore", table.lower())
        self.assertNotIn("session-retrospective", table.lower())


if __name__ == "__main__":
    unittest.main()
