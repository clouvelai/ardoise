# Ardoise

Ardoise is a **local AI spend ledger** for [Claude Code](https://code.claude.com) and [Cursor](https://cursor.com).

It reads on-disk usage (Anthropic session JSONL, Cursor/Claude hooks) into a SQLite ledger at `~/.ardoise/ledger.db`, then prints month statements. Core is Python 3 standard library only. Nothing leaves the machine. Prompts and credentials are never stored.

Phase 1 lives in this repository. See `docs/` after the first implementation lands.

```bash
./install.sh --no-plugin-manager
bin/ardoise status --json
bin/ardoise backfill
bin/ardoise statement 2026-09
```
