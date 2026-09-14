#!/usr/bin/env python3
"""Cursor T2 scaffold tests — fixture JSON only, no live Admin API key."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import db  # noqa: E402
from ardoise.adapters.cloud_agent import named_run_agents  # noqa: E402
from ardoise.adapters.hook_event import event_to_entry  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.privacy import usage_only_event  # noqa: E402
from ardoise.vendors import cursor as cursor_t2  # noqa: E402
from ardoise.vendors.cursor import UNATTRIBUTED  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


CLOUD = ROOT / "tests" / "fixtures" / "cloud_agent"


def _usage_events(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "totalUsageEventsCount": len(rows),
        "pagination": {
            "numPages": 1,
            "currentPage": 1,
            "pageSize": 25,
            "hasNextPage": False,
            "hasPreviousPage": False,
        },
        "usageEvents": rows,
    }


class FixtureTransport:
    """Replay Admin API fixture JSON. Records calls for assertions."""

    def __init__(self, events: dict[str, Any] | None = None) -> None:
        self.members = _load("cursor_t2_members.json")
        self.events = events if events is not None else _load("cursor_t2_events.json")
        self.spend = _load("cursor_t2_spend.json")
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path, body))
        if path == "/teams/members":
            return self.members
        if path == "/teams/spend":
            return self.spend
        if path == "/teams/filtered-usage-events":
            return self.events
        raise KeyError(path)


class CursorT2Tests(unittest.TestCase):
    def test_capabilities_without_cred(self) -> None:
        caps = cursor_t2.capabilities(environ={})
        self.assertTrue(caps["t0"])
        self.assertFalse(caps["t2"])
        self.assertFalse(caps["has_cred"])

    def test_capabilities_with_cred(self) -> None:
        caps = cursor_t2.capabilities(environ={"CURSOR_ADMIN_API_KEY": "key_test"})
        self.assertTrue(caps["t2"])
        self.assertTrue(caps["has_cred"])

    def test_parse_fixture_event_id_and_cost(self) -> None:
        raw = _load("cursor_t2_events.json")["usageEvents"][0]
        parsed = cursor_t2.parse_event(raw)
        assert parsed is not None
        self.assertEqual(parsed["event_id"], "evt_t2_matched")
        self.assertEqual(parsed["message_id"], "evt_t2_matched")
        self.assertEqual(parsed["request_id"], "evt_t2_matched")
        self.assertEqual(parsed["conversation_id"], "conv_proj_1")
        self.assertEqual(parsed["input_tokens"], 126)
        self.assertEqual(parsed["output_tokens"], 450)
        self.assertEqual(parsed["cache_creation_tokens"], 6112)
        self.assertEqual(parsed["cache_read_tokens"], 11964)
        self.assertAlmostEqual(parsed["cost_usd"], 0.2136232, places=6)
        self.assertEqual(parsed["source"], "cursor_t2")

    def test_event_id_stable_without_explicit_id(self) -> None:
        raw = dict(_load("cursor_t2_events.json")["usageEvents"][0])
        raw.pop("id")
        first = cursor_t2.event_id(raw)
        second = cursor_t2.event_id(raw)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("cur_"))

    def test_t0_hook_keeps_conversation_id(self) -> None:
        event = usage_only_event(
            {
                "conversationId": "conv_proj_1",
                "model": "composer-2.5",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        self.assertEqual(event["session_id"], "conv_proj_1")

    def test_vendor_test_missing_cred(self) -> None:
        data = cursor_t2.test_vendor(environ={})
        self.assertTrue(data["ok"])
        self.assertTrue(data["skipped"])
        self.assertEqual(data["reason"], "missing_cred")
        self.assertIn("missing CURSOR_ADMIN_API_KEY", data["message"])
        self.assertIn("T0-only", cursor_t2.render_test(data))
        self.assertIn("advanced", data["message"].lower())
        self.assertIn("Team/Enterprise", data["message"])

    def test_vendor_test_fixture_roster_role_events(self) -> None:
        transport = FixtureTransport()
        data = cursor_t2.test_vendor(transport=transport, environ={})
        self.assertTrue(data["ok"])
        self.assertEqual(data["roster"], 2)
        self.assertEqual(data["role"], "member,owner")
        self.assertEqual(data["events_7d"], 3)
        text = cursor_t2.render_test(data)
        self.assertIn("roster=2", text)
        self.assertIn("role=member,owner", text)
        self.assertIn("events_7d=3", text)
        paths = {c[1] for c in transport.calls}
        self.assertEqual(
            paths,
            {"/teams/members", "/teams/spend", "/teams/filtered-usage-events"},
        )

    def test_vendor_test_401_uses_fail_open_wording(self) -> None:
        def boom(_method: str, _path: str, _body: dict[str, Any] | None = None) -> dict[str, Any]:
            raise RuntimeError(
                "cursor admin API GET /teams/members failed: HTTP 401 Invalid Team API Key"
            )

        data = cursor_t2.test_vendor(
            transport=boom,
            environ={"CURSOR_ADMIN_API_KEY": "key_test"},
        )
        text = cursor_t2.render_test(data)
        self.assertFalse(data["ok"])
        self.assertIn("Team Admin API key rejected (401)", text)
        self.assertIn("optional T2", text)
        self.assertIn("Personal/solo", text)
        self.assertNotIn("key_test", text)

    def test_pull_without_cred_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.db"
            result = cursor_t2.pull(db_path=ledger, environ={})
            self.assertTrue(result["skipped"])
            self.assertEqual(result["reason"], "missing_cred")
            self.assertFalse(ledger.exists())

    def test_pull_joins_conversation_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            transport = FixtureTransport()
            with db.session(ledger) as conn:
                db.upsert_entry(
                    conn,
                    {
                        "source": "cursor",
                        "message_id": "msg_hook_1",
                        "request_id": "req_hook_1",
                        "project": "clouvelai/ardoise",
                        "model": "composer-2.5",
                        "occurred_at": "2026-09-12T10:00:00Z",
                        "input_tokens": 10,
                        "output_tokens": 4,
                        "session_id": "conv_proj_1",
                        "cost_usd": 0.0,
                    },
                )
                first = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )
                second = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )

                self.assertEqual(first["inserted"], 3)
                self.assertEqual(first["attributed"], 1)
                self.assertEqual(first["unattributed"], 2)
                self.assertEqual(second["inserted"], 0)
                self.assertEqual(second["skipped_rows"], 3)

                matched = conn.execute(
                    "SELECT * FROM entries WHERE message_id = 'evt_t2_matched'"
                ).fetchone()
                self.assertIsNotNone(matched)
                self.assertEqual(matched["project"], "clouvelai/ardoise")
                self.assertEqual(matched["source"], "cursor_t2")
                self.assertEqual(matched["session_id"], "conv_proj_1")
                self.assertAlmostEqual(float(matched["cost_usd"]), 0.2136232, places=6)

                unmatched = conn.execute(
                    "SELECT project FROM entries WHERE message_id = 'evt_t2_unmatched'"
                ).fetchone()
                self.assertEqual(unmatched["project"], UNATTRIBUTED)

                no_conv = conn.execute(
                    "SELECT project FROM entries WHERE message_id = 'evt_t2_no_conv'"
                ).fetchone()
                self.assertEqual(no_conv["project"], UNATTRIBUTED)

                mark = db.get_sync_watermark(conn, "cursor", "usage_events")
                self.assertIsNotNone(mark)
                self.assertTrue(str(mark).isdigit())

            blob = ledger.read_bytes()
            for needle in (b"developer@example.com", b"admin@example.com", b"key_test"):
                self.assertNotIn(needle, blob)

            t2_count = 0
            with db.session(ledger) as conn:
                t2_count = conn.execute(
                    "SELECT COUNT(*) FROM entries WHERE source = 'cursor_t2'"
                ).fetchone()[0]
            self.assertEqual(t2_count, 3)

    def test_reattribute_on_later_t0_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            transport = FixtureTransport()
            with db.session(ledger) as conn:
                first = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )
                self.assertEqual(first["unattributed"], 3)
                db.upsert_entry(
                    conn,
                    {
                        "source": "hook",
                        "message_id": "msg_late",
                        "request_id": "req_late",
                        "project": "clouvelai/Arbusteia",
                        "model": "composer-2.5",
                        "occurred_at": "2026-09-12T11:00:00Z",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "session_id": "conv_proj_1",
                        "cost_usd": 0.0,
                    },
                )
                again = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )
                self.assertGreaterEqual(again["updated"], 1)
                matched = conn.execute(
                    "SELECT project FROM entries WHERE message_id = 'evt_t2_matched'"
                ).fetchone()
                self.assertEqual(matched["project"], "clouvelai/Arbusteia")

    def test_cli_vendor_test_missing_cred(self) -> None:
        env_home = tempfile.TemporaryDirectory()
        try:
            os.environ["ARDOISE_HOME"] = env_home.name
            os.environ.pop("CURSOR_ADMIN_API_KEY", None)
            os.environ.pop("CURSOR_API_KEY", None)
            from io import StringIO
            from contextlib import redirect_stdout

            buf = StringIO()
            with redirect_stdout(buf):
                code = cli_main(["vendor", "test", "cursor"])
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("missing CURSOR_ADMIN_API_KEY", out)
            self.assertIn("T0-only", out)
            self.assertIn("advanced", out.lower())
            self.assertIn("Team/Enterprise", out)
        finally:
            env_home.cleanup()

    def test_parse_event_keeps_cloud_agent_id(self) -> None:
        parsed = cursor_t2.parse_event(
            {
                "id": "evt_bc",
                "timestamp": "1757667900000",
                "cloudAgentId": "bc-00000000-0000-0000-0000-000000000042",
                "model": "claude-4.5-sonnet",
                "tokenUsage": {"inputTokens": 10, "outputTokens": 4},
                "chargedCents": 2,
            }
        )
        assert parsed is not None
        self.assertEqual(parsed["bc_id"], "bc-00000000-0000-0000-0000-000000000042")
        self.assertEqual(parsed["session_id"], "bc-00000000-0000-0000-0000-000000000042")
        self.assertIsNone(parsed["agent"])

    def test_t0_hook_named_agent_still_persists(self) -> None:
        raw = {
            "hook_event_name": "stop",
            "conversationId": "conv_named",
            "agentId": "Craie",
            "model": "composer-2.5",
            "usage": {"input_tokens": 8, "output_tokens": 3},
            "message": {"id": "msg_hook_named"},
            "requestId": "req_hook_named",
        }
        safe = usage_only_event(raw)
        self.assertEqual(safe["agent"], "Craie")
        self.assertEqual(safe["session_id"], "conv_named")
        entry = event_to_entry(raw, default_source="hook")
        assert entry is not None
        self.assertEqual(entry["agent"], "Craie")
        self.assertEqual(entry["session_id"], "conv_named")

    def test_join_conversation_sets_agent_from_t0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            transport = FixtureTransport()
            with db.session(ledger) as conn:
                db.upsert_entry(
                    conn,
                    {
                        "source": "hook",
                        "message_id": "msg_hook_named",
                        "request_id": "req_hook_named",
                        "project": "clouvelai/ardoise",
                        "model": "composer-2.5",
                        "occurred_at": "2026-09-12T10:00:00Z",
                        "input_tokens": 8,
                        "output_tokens": 3,
                        "session_id": "conv_proj_1",
                        "cost_usd": 0.0,
                        "agentId": "Craie",
                    },
                )
                result = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )
                self.assertEqual(result["agent_attributed"], 1)
                matched = conn.execute(
                    "SELECT agent, project FROM entries WHERE message_id = 'evt_t2_matched'"
                ).fetchone()
                self.assertEqual(matched["agent"], "Craie")
                self.assertEqual(matched["project"], "clouvelai/ardoise")
                unknown = conn.execute(
                    "SELECT agent FROM entries WHERE message_id = 'evt_t2_unmatched'"
                ).fetchone()
                self.assertIsNone(unknown["agent"])

    def test_join_bcid_sets_agent_unknown_stays_unset(self) -> None:
        rows = [
            {
                "id": "evt_t2_bc_hit",
                "timestamp": "1757667900000",
                "cloudAgentId": "bc-00000000-0000-0000-0000-000000000001",
                "model": "cursor-grok-4.6-high",
                "tokenUsage": {"inputTokens": 20, "outputTokens": 6},
                "chargedCents": 5,
            },
            {
                "id": "evt_t2_bc_miss",
                "timestamp": "1757668000000",
                "cloudAgentId": "bc-00000000-0000-0000-0000-00000000dead",
                "model": "cursor-grok-4.6-high",
                "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                "chargedCents": 1,
            },
        ]
        transport = FixtureTransport(events=_usage_events(rows))
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            with db.session(ledger) as conn:
                db.upsert_entry(
                    conn,
                    {
                        "source": "cursor",
                        "message_id": "msg_cloud_craie",
                        "request_id": "req_cloud_craie",
                        "model": "cursor-grok-4.6-high",
                        "occurred_at": "2026-09-13T09:05:00Z",
                        "input_tokens": 1500,
                        "output_tokens": 300,
                        "session_id": "bc-00000000-0000-0000-0000-000000000001",
                        "cost_usd": 0.01,
                        "agent": "Craie",
                    },
                )
                result = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )
                self.assertEqual(result["agent_attributed"], 1)
                self.assertEqual(result["agent_unattributed"], 1)
                hit = conn.execute(
                    "SELECT agent FROM entries WHERE message_id = 'evt_t2_bc_hit'"
                ).fetchone()
                miss = conn.execute(
                    "SELECT agent FROM entries WHERE message_id = 'evt_t2_bc_miss'"
                ).fetchone()
                self.assertEqual(hit["agent"], "Craie")
                self.assertIsNone(miss["agent"])

    def test_sidecar_map_joins_prompt_only_run(self) -> None:
        mapping = named_run_agents(CLOUD)
        rows = [
            {
                "id": "evt_t2_prompt_only",
                "timestamp": "1757668100000",
                "cloudAgentId": "bc-00000000-0000-0000-0000-000000000042",
                "model": "cursor-grok-4.6-high",
                "tokenUsage": {"inputTokens": 90, "outputTokens": 12},
                "chargedCents": 8,
            }
        ]
        transport = FixtureTransport(events=_usage_events(rows))
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            with db.session(ledger) as conn:
                result = cursor_t2.pull(
                    conn=conn,
                    transport=transport,
                    environ={},
                    run_agents=mapping,
                )
                self.assertEqual(result["inserted"], 1)
                self.assertEqual(result["agent_attributed"], 1)
                row = conn.execute(
                    "SELECT agent, input_tokens, cost_usd FROM entries "
                    "WHERE message_id = 'evt_t2_prompt_only'"
                ).fetchone()
                self.assertEqual(row["agent"], "Encre")
                self.assertEqual(int(row["input_tokens"]), 90)
                self.assertAlmostEqual(float(row["cost_usd"]), 0.08, places=6)

    def test_never_invents_agent_from_title_or_unknown_id(self) -> None:
        rows = [
            {
                "id": "evt_t2_title",
                "timestamp": "1757668200000",
                "cloudAgentId": "bc-00000000-0000-0000-0000-000000000099",
                "name": "Fix the billing success page",
                "agent": {
                    "id": "bc-00000000-0000-0000-0000-000000000099",
                    "name": "Fix the billing success page",
                    "status": "FINISHED",
                    "env": {"type": "cloud"},
                },
                "model": "cursor-grok-4.6-high",
                "tokenUsage": {"inputTokens": 11, "outputTokens": 2},
                "chargedCents": 3,
            }
        ]
        transport = FixtureTransport(events=_usage_events(rows))
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            with db.session(ledger) as conn:
                result = cursor_t2.pull(
                    conn=conn,
                    transport=transport,
                    environ={},
                    run_agents=named_run_agents(CLOUD),
                )
                self.assertEqual(result["agent_attributed"], 0)
                row = conn.execute(
                    "SELECT agent FROM entries WHERE message_id = 'evt_t2_title'"
                ).fetchone()
                self.assertIsNone(row["agent"])

    def test_reattribute_agent_on_later_named_hook(self) -> None:
        rows = [
            {
                "id": "evt_t2_late_agent",
                "timestamp": "1757668300000",
                "conversationId": "conv_late_agent",
                "model": "composer-2.5",
                "tokenUsage": {"inputTokens": 7, "outputTokens": 2},
                "chargedCents": 1,
            }
        ]
        transport = FixtureTransport(events=_usage_events(rows))
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ARDOISE_HOME"] = tmp
            ledger = Path(tmp) / "ledger.db"
            with db.session(ledger) as conn:
                first = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )
                self.assertEqual(first["agent_unattributed"], 1)
                db.upsert_entry(
                    conn,
                    {
                        "source": "hook",
                        "message_id": "msg_late_agent",
                        "request_id": "req_late_agent",
                        "model": "composer-2.5",
                        "occurred_at": "2026-09-12T12:00:00Z",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "session_id": "conv_late_agent",
                        "cost_usd": 0.0,
                        "agentId": "captain",
                    },
                )
                again = cursor_t2.pull(
                    conn=conn, transport=transport, environ={}, run_agents={}
                )
                self.assertGreaterEqual(again["updated"], 1)
                row = conn.execute(
                    "SELECT agent FROM entries WHERE message_id = 'evt_t2_late_agent'"
                ).fetchone()
                self.assertEqual(row["agent"], "captain")


if __name__ == "__main__":
    unittest.main()
