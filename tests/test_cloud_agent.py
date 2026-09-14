#!/usr/bin/env python3
"""Grok Bot / cloud-agent transcripts land as T0 events with agent= when named."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise import attribution, db  # noqa: E402
from ardoise.adapters.cloud_agent import (  # noqa: E402
    discover_transcript_files,
    iter_transcript_objects,
    named_run_agents,
    parse_line,
    sidecar_meta,
    transcript_roots,
)
from ardoise.backfill import backfill  # noqa: E402
from ardoise.cli import main as cli_main  # noqa: E402
from ardoise.privacy import usage_only_event  # noqa: E402
from ardoise.statement import write_statement  # noqa: E402
from ardoise.status import render_text, summarize  # noqa: E402
from ardoise.vendors.cursor import discover_cursor_files  # noqa: E402

GROK = ROOT / "tests" / "fixtures" / "grok_bot.jsonl"
CLOUD = ROOT / "tests" / "fixtures" / "cloud_agent"


def _lines(path: Path = GROK) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line.replace("/WORKSPACE", str(ROOT))))
    return rows


class ParseTests(unittest.TestCase):
    def test_grok_bot_jsonl_sets_agent(self) -> None:
        parsed = [parse_line(obj) for obj in _lines()]
        self.assertTrue(all(parsed[:3]))
        self.assertEqual(parsed[0]["agent"], "Craie")
        self.assertEqual(parsed[0]["skill"], "session-retrospective")
        self.assertEqual(parsed[0]["effort"], "high")
        self.assertEqual(parsed[0]["vendor"], "cursor")
        self.assertEqual(parsed[0]["source"], "cursor")
        self.assertEqual(parsed[1]["agent"], "Encre")
        self.assertEqual(parsed[1]["skill"], "stripe-docs")
        self.assertEqual(parsed[2]["agent"], "captain")
        self.assertEqual(parsed[2]["input_tokens"], 200)
        self.assertEqual(parsed[2]["cache_read_tokens"], 10)

    def test_prompt_text_does_not_invent_agent(self) -> None:
        anon = parse_line(_lines()[3])
        assert anon is not None
        self.assertIsNone(anon["agent"])
        self.assertIsNone(anon["skill"])

    def test_stop_hook_top_level_tokens_and_model_params(self) -> None:
        raw = _lines()[4]
        safe = usage_only_event(raw)
        self.assertEqual(safe["usage"]["input_tokens"], 90)
        self.assertEqual(safe["agent"], "Craie")
        self.assertEqual(safe["effort"], "high")
        entry = parse_line(raw)
        assert entry is not None
        self.assertEqual(entry["agent"], "Craie")
        self.assertEqual(entry["effort"], "high")
        self.assertEqual(entry["input_tokens"], 90)
        self.assertEqual(entry["source"], "cursor")

    def test_cloud_run_title_is_not_agent(self) -> None:
        found = attribution.extract(
            {
                "id": "bc-00000000-0000-0000-0000-000000000099",
                "name": "Fix the billing success page",
                "status": "FINISHED",
                "agent": {
                    "id": "bc-00000000-0000-0000-0000-000000000099",
                    "name": "Fix the billing success page",
                    "status": "FINISHED",
                    "env": {"type": "cloud"},
                },
            }
        )
        self.assertIsNone(found["agent"])

    def test_bot_name_key(self) -> None:
        found = attribution.extract({"botName": "captain", "skill": "stripe-apps"})
        self.assertEqual(found["agent"], "captain")
        self.assertEqual(found["skill"], "stripe-apps")

    def test_sidecar_inherits_agent_without_inventing_title(self) -> None:
        path = CLOUD / "craie-run" / "transcript.json"
        inherited = sidecar_meta(path)
        self.assertEqual(inherited.get("agent"), "Craie")
        self.assertEqual(inherited.get("session_id"), "bc-00000000-0000-0000-0000-000000000001")
        self.assertNotIn("What did Craie spend", json.dumps(inherited))
        objs = list(iter_transcript_objects(path))
        self.assertEqual(len(objs), 1)
        entry = parse_line(objs[0], inherited=inherited)
        assert entry is not None
        self.assertEqual(entry["agent"], "Craie")
        self.assertEqual(entry["message_id"], "msg_cloud_craie")
        self.assertEqual(entry["session_id"], "bc-00000000-0000-0000-0000-000000000001")

    def test_named_run_agents_maps_bc_id_never_invents(self) -> None:
        mapping = named_run_agents(CLOUD)
        self.assertEqual(mapping.get("bc-00000000-0000-0000-0000-000000000001"), "Craie")
        self.assertEqual(mapping.get("bc-00000000-0000-0000-0000-000000000042"), "Encre")
        self.assertNotIn("bc-00000000-0000-0000-0000-000000000099", mapping)
        self.assertNotIn("What should Encre ship next", mapping.values())
        self.assertNotIn("Fix the billing success page", mapping.values())

    def test_prompt_only_transcript_does_not_invent_meters(self) -> None:
        path = CLOUD / "prompt-only-run" / "transcript.json"
        inherited = sidecar_meta(path)
        self.assertEqual(inherited.get("agent"), "Encre")
        objs = list(iter_transcript_objects(path))
        self.assertEqual(len(objs), 1)
        self.assertIsNone(parse_line(objs[0], inherited=inherited))

    def test_unnamed_sidecar_stays_unattributed(self) -> None:
        path = CLOUD / "unnamed-run" / "transcript.json"
        inherited = sidecar_meta(path)
        self.assertIsNone(inherited.get("agent"))
        entry = parse_line(list(iter_transcript_objects(path))[0], inherited=inherited)
        assert entry is not None
        self.assertIsNone(entry["agent"])

    def test_garbage_and_secrets_are_skipped(self) -> None:
        broken = CLOUD / "garbage" / "broken.jsonl"
        self.assertEqual(list(iter_transcript_objects(broken)), [])
        self.assertIsNone(parse_line(None))
        self.assertIsNone(parse_line({"not": "usage"}))
        found = discover_transcript_files(CLOUD)
        names = {p.name for p in found}
        self.assertNotIn("secrets.json", names)
        self.assertIn("broken.jsonl", names)


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in (
            "ARDOISE_LEDGER",
            "ARDOISE_QUEUE",
            "ARDOISE_STATEMENTS",
            "ARDOISE_CONFIG",
            "ARDOISE_CLOUD_AGENT_ROOT",
            "ARDOISE_AGENT_DATA",
            "ARDOISE_TRANSCRIPT_PATHS",
        ):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class IngestAndRosterTests(IsolatedHome):
    def test_backfill_fixture_persists_agent(self) -> None:
        empty_claude = Path(self.tmp.name) / "empty-claude"
        empty_cursor = Path(self.tmp.name) / "empty-cursor"
        empty_claude.mkdir()
        empty_cursor.mkdir()
        result = backfill(claude=empty_claude, cursor=empty_cursor, transcripts=CLOUD)
        self.assertGreaterEqual(result["inserted"], 3)
        with db.session() as conn:
            rows = {
                str(r["message_id"]): dict(r)
                for r in conn.execute("SELECT * FROM events").fetchall()
            }
            blob = Path(os.environ["ARDOISE_HOME"], "ledger.db").read_bytes()
        self.assertEqual(rows["msg_cloud_craie"]["agent"], "Craie")
        self.assertEqual(rows["msg_box_captain"]["agent"], "captain")
        self.assertIsNone(rows["msg_cloud_anon"]["agent"])
        for needle in (
            b"SECRET_CLOUD_PROMPT",
            b"SECRET_BOX_PROMPT",
            b"SECRET_SHOULD_NOT_BE_READ",
            b"SECRET_PROMPT_ONLY_PROMPT",
            b"SECRET_PROMPT_ONLY_BODY",
        ):
            self.assertNotIn(needle, blob)

    def test_configurable_root_env_and_config(self) -> None:
        dest = Path(self.tmp.name) / "exports" / "agent-data"
        dest.mkdir(parents=True)
        (dest / "craie.jsonl").write_text(
            json.dumps(
                {
                    "agent": "Craie",
                    "model": "cursor-grok-4.6-high",
                    "timestamp": "2026-09-13T15:00:00Z",
                    "requestId": "req_cfg",
                    "message": {
                        "id": "msg_cfg",
                        "usage": {"input_tokens": 11, "output_tokens": 2},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ARDOISE_CLOUD_AGENT_ROOT"] = str(dest)
        roots = transcript_roots()
        self.assertTrue(any(p.resolve() == dest.resolve() for p in roots))
        home = Path(os.environ["ARDOISE_HOME"])
        home.mkdir(parents=True)
        (home / "config.json").write_text(
            json.dumps({"transcripts": {"paths": [str(dest)]}}),
            encoding="utf-8",
        )
        os.environ.pop("ARDOISE_CLOUD_AGENT_ROOT", None)
        from ardoise import config as config_mod

        cfg = config_mod.load()
        self.assertEqual(cfg["transcripts"]["paths"], [str(dest)])

    def test_default_transcripts_dir_needs_no_flag(self) -> None:
        empty_claude = Path(self.tmp.name) / "empty-claude"
        empty_cursor = Path(self.tmp.name) / "empty-cursor"
        empty_claude.mkdir()
        empty_cursor.mkdir()
        from ardoise import paths as paths_mod

        dest = paths_mod.transcripts_dir() / "agent-data"
        dest.mkdir(parents=True)
        src = ROOT / "tests" / "fixtures" / "dogfood" / "agent-data"
        for name in ("Craie", "Encre", "captain"):
            folder = dest / name
            folder.mkdir()
            body = (src / name / "session.jsonl").read_text(encoding="utf-8")
            (folder / "session.jsonl").write_text(body.replace("/WORKSPACE", str(ROOT)), encoding="utf-8")
        result = backfill(claude=empty_claude, cursor=empty_cursor)
        self.assertGreaterEqual(result["inserted"], 3)
        data = summarize("2026-09")
        self.assertEqual({row["agent"] for row in data["agents"]}, {"Craie", "Encre", "captain"})
        text = render_text(data)
        for name in ("Craie", "Encre", "captain"):
            self.assertIn(f"{name} $", text)
        self.assertGreater(float(summarize("2026-09", person="Craie")["cost_usd"]), 0)

    def test_cursor_discover_still_skips_agent_transcripts(self) -> None:
        root = Path(self.tmp.name) / ".cursor"
        keep = root / "projects" / "app" / "chat.jsonl"
        skip = root / "projects" / "app" / "agent-transcripts" / "x.jsonl"
        keep.parent.mkdir(parents=True)
        skip.parent.mkdir(parents=True)
        keep.write_text("{}\n", encoding="utf-8")
        skip.write_text("{}\n", encoding="utf-8")
        found = {p.resolve() for p in discover_cursor_files(root)}
        self.assertIn(keep.resolve(), found)
        self.assertNotIn(skip.resolve(), found)

    def test_status_statement_chips_and_agent_filter(self) -> None:
        empty_claude = Path(self.tmp.name) / "empty-claude"
        empty_cursor = Path(self.tmp.name) / "empty-cursor"
        empty_claude.mkdir()
        empty_cursor.mkdir()
        drop = Path(self.tmp.name) / "transcripts"
        drop.mkdir()
        (drop / "grok_bot.jsonl").write_text(
            GROK.read_text(encoding="utf-8").replace("/WORKSPACE", str(ROOT)),
            encoding="utf-8",
        )
        backfill(claude=empty_claude, cursor=empty_cursor, transcripts=drop)

        data = summarize("2026-09")
        names = {row["agent"] for row in data["agents"]}
        self.assertEqual(names, {"Craie", "Encre", "captain"})
        text = render_text(data)
        for name in ("Craie", "Encre", "captain"):
            self.assertIn(f"{name} $", text)
        self.assertIn("agents   ", text)
        self.assertIn("attribution (when present)", text)

        craie = summarize("2026-09", person="Craie")
        self.assertEqual(craie["filter"]["kind"], "agent")
        self.assertTrue(craie["filter"]["view_only"])
        self.assertTrue(all(row.get("agent") == "Craie" for row in craie["lines"]))
        self.assertGreater(float(craie["cost_usd"]), 0)
        self.assertGreaterEqual(craie["month_entries"], 2)
        self.assertEqual(craie["entries"], data["entries"])
        filtered = render_text(craie)
        self.assertIn("filter   Craie", filtered)
        self.assertIn("$", filtered.split("filter   Craie", 1)[1][:24])
        self.assertNotIn("Encre", json.dumps(craie["lines"]))

        written = write_statement("2026-09")
        md = Path(written["md"]).read_text(encoding="utf-8")
        html = Path(written["html"]).read_text(encoding="utf-8")
        self.assertIn("Agents ·", md)
        self.assertIn("**Craie**", md)
        self.assertIn("$", md.split("Agents ·", 1)[1][:80])
        self.assertIn("badge agent", html)
        self.assertIn("$", html.split("badge agent", 1)[1][:80])
        self.assertNotIn("roster table", html.lower())

        agent_stmt = write_statement("2026-09", person="captain")
        self.assertIn("2026-09--captain.md", agent_stmt["md"])
        agent_md = Path(agent_stmt["md"]).read_text(encoding="utf-8")
        agent_html = Path(agent_stmt["html"]).read_text(encoding="utf-8")
        agent_csv = Path(agent_stmt["csv"]).read_text(encoding="utf-8")
        self.assertIn("Agent **captain**", agent_md)
        self.assertIn("$", agent_md.split("Agent **captain**", 1)[1][:40])
        self.assertIn("view only", agent_md)
        self.assertIn("badge agent", agent_html)
        self.assertIn("agent filter captain", agent_csv)
        self.assertNotIn("msg_grok_craie", agent_csv)
        self.assertNotIn("msg_grok_encre", agent_csv)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(["status", "--json", "--month", "2026-09", "--roster", "Encre"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["filter"]["kind"], "agent")
        self.assertEqual(payload["filter"]["canonical"], "Encre")
        named = {
            row["agent"]
            for row in payload.get("by_agent") or []
            if row.get("agent") and row["agent"] != attribution.UNATTRIBUTED
        }
        self.assertEqual(named, {"Encre"})


if __name__ == "__main__":
    unittest.main()
