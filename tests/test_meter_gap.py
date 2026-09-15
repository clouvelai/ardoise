#!/usr/bin/env python3
"""Soft notes + status --json meter_gap when roots are prompt-only."""

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

from ardoise import meter_gap  # noqa: E402
from ardoise.backfill import backfill, empty_ledger_tip  # noqa: E402
from ardoise.status import render_text, summarize  # noqa: E402

CLOUD = ROOT / "tests" / "fixtures" / "cloud_agent"


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old_home = os.environ.get("HOME")
        self._old_ardoise = os.environ.get("ARDOISE_HOME")
        os.environ["HOME"] = self.tmp.name
        os.environ["ARDOISE_HOME"] = str(Path(self.tmp.name) / ".ardoise")
        for key in (
            "ARDOISE_LEDGER",
            "ARDOISE_QUEUE",
            "ARDOISE_CONFIG",
            "ARDOISE_CLOUD_AGENT_ROOT",
            "ARDOISE_AGENT_DATA",
            "ARDOISE_TRANSCRIPT_PATHS",
            "ARDOISE_SCAN_BOX_ROOTS",
        ):
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


class MeterGapTests(IsolatedHome):
    def test_prompt_only_scan_sets_meter_gap_and_soft_note(self) -> None:
        empty_claude = Path(self.tmp.name) / "empty-claude"
        empty_cursor = Path(self.tmp.name) / "empty-cursor"
        empty_claude.mkdir()
        empty_cursor.mkdir()
        prompt = CLOUD / "prompt-only-run"
        result = backfill(claude=empty_claude, cursor=empty_cursor, transcripts=prompt)
        self.assertEqual(result["inserted"], 0)
        self.assertGreaterEqual(result["files"], 1)
        self.assertEqual(empty_ledger_tip(result), meter_gap.PROMPT_ONLY_HINT)
        data = summarize("2026-09")
        gap = data.get("meter_gap") or {}
        self.assertEqual(gap.get("kind"), meter_gap.KIND_PROMPT_ONLY)
        self.assertTrue(gap.get("scanned"))
        self.assertEqual(gap.get("usage_rows"), 0)
        self.assertIn(meter_gap.PROMPT_ONLY_HINT, data.get("notes") or [])
        text = render_text(data)
        self.assertIn("notes (soft)", text)
        self.assertIn("roots scanned, no usage objects", text)

    def test_usage_json_probe_counts_shaped_only(self) -> None:
        drop = Path(os.environ["ARDOISE_HOME"]) / "transcripts" / "probe"
        drop.mkdir(parents=True)
        (drop / "usage.json").write_text(
            json.dumps({"messages": [{"role": "assistant", "text": "SECRET_NO_USAGE"}]}),
            encoding="utf-8",
        )
        (drop / "usage.jsonl").write_text(
            json.dumps(
                {
                    "model": "cursor-grok-4.6-high",
                    "requestId": "req_usage_json",
                    "message": {
                        "id": "msg_usage_json",
                        "usage": {"input_tokens": 10, "output_tokens": 2},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        probe = meter_gap.probe_usage_paths()
        self.assertEqual(probe["usage_json"], 2)
        self.assertEqual(probe["usage_shaped"], 1)

    def test_usage_shaped_backfill_clears_gap(self) -> None:
        empty_claude = Path(self.tmp.name) / "empty-claude"
        empty_cursor = Path(self.tmp.name) / "empty-cursor"
        empty_claude.mkdir()
        empty_cursor.mkdir()
        dest = Path(os.environ["ARDOISE_HOME"]) / "transcripts"
        dest.mkdir(parents=True)
        (dest / "usage.jsonl").write_text(
            json.dumps(
                {
                    "agent": "Craie",
                    "model": "cursor-grok-4.6-high",
                    "timestamp": "2026-09-13T10:00:00Z",
                    "requestId": "req_gap_clear",
                    "message": {
                        "id": "msg_gap_clear",
                        "usage": {"input_tokens": 20, "output_tokens": 4},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        result = backfill(claude=empty_claude, cursor=empty_cursor)
        self.assertGreaterEqual(result["inserted"], 1)
        self.assertIsNone(empty_ledger_tip(result))
        data = summarize("2026-09")
        self.assertIsNone((data.get("meter_gap") or {}).get("kind"))
        self.assertGreater(float(data.get("cost_usd") or 0), 0)
        self.assertNotIn(meter_gap.PROMPT_ONLY_HINT, data.get("notes") or [])

    def test_describe_no_logs_after_empty_capture(self) -> None:
        gap = meter_gap.describe(
            scan={"files": 0, "usage_rows": 0},
            backfilled=True,
            month_cost=0,
            probe={"usage_json": 0, "usage_shaped": 0, "hook_queue": 0},
        )
        self.assertEqual(gap["kind"], meter_gap.KIND_NO_LOGS)
        self.assertIsNone(meter_gap.note_for(gap))


if __name__ == "__main__":
    unittest.main()
