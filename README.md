# Ardoise

Ardoise is a **local AI spend ledger** for [Claude Code](https://code.claude.com)
and [Cursor](https://cursor.com).

It reads on-disk usage into SQLite at `~/.ardoise/ledger.db` and prints month
statements. Core is **Python 3 standard library only**. Nothing leaves the
machine. Prompts and credentials are never stored.

## Install

```bash
./install.sh --no-plugin-manager
```

That copies shared capture hooks into `~/.claude/settings.json` and
`~/.cursor/hooks.json` (no plugin marketplace). `bin/ardoise` is linked to
`~/.local/bin/ardoise` when possible.

## Commands

```bash
bin/ardoise status              # this UTC month
bin/ardoise status --json
bin/ardoise backfill            # Anthropic T0 JSONL + Cursor logs + hook queue
bin/ardoise capture             # drain ~/.ardoise/queue
bin/ardoise capture --stdin     # one hook event (used by plugins)
bin/ardoise statement 2026-09   # writes MD + HTML + CSV
bin/ardoise export              # JSONL of usage rows
bin/ardoise export --month 2026-09 --out /tmp/ardoise.jsonl
bin/ardoise vendor test anthropic
bin/ardoise invoice paste --file invoices.jsonl   # section A billed truth
```

Statements land in `~/.ardoise/statements/YYYY-MM.{md,html,csv}`.

**Section A** is billed truth: pasted invoices, else T1 snapshots, else T2 billed events — labeled by tier of truth. **T0** (local tokens × list price) only allocates those dollars across projects. T0 is never treated as an invoice-grade total.

## How spend is captured

| Source | Adapter | Location |
|---|---|---|
| Claude Code session logs | `vendors/anthropic` T0 | `~/.claude/projects/**/*.jsonl` |
| Cursor transcripts | `vendors/cursor` T0 | `~/.cursor/**/*.jsonl` (usage-shaped) |
| Pasted invoices | `invoice paste` | ledger `invoices` table (section A) |
| Live sessions | Shared hooks + queue | `~/.ardoise/queue/*.json` |

Streaming duplicates share `message.id` + `requestId`. Ardoise keeps the row
with the highest `output_tokens`.

**Project** is the git remote `owner/repo` for the event `cwd` (or the current
workspace).

Prices come from [`data/prices.fallback.json`](data/prices.fallback.json).
Override with `~/.ardoise/prices.json`.

## Privacy

The ledger stores model, tokens, timestamps, ids, and `owner/repo`. Capture
scrubs prompts, message bodies, tool I/O, and credentials before enqueue or
insert.

## Tests

```bash
tests/fresh-box.sh
```

Must print `FRESH-BOX-OK` with no network.

## Landing

Marketing site lives in [`apps/web`](apps/web) (Next.js App Router + Tailwind).

```bash
cd apps/web
npm install
npm run dev    # http://localhost:3000
npm run build
```

## Later (not Phase 1)

A hosted companion, if any, should follow
[`docs/saas-scaffold.md`](docs/saas-scaffold.md): **Supabase email OTP +
Postgres**, and **Stripe Checkout Sessions** — the same pattern Arbusteia
already uses. Phase 1 does not call those services.

Scaffold lives in [`apps/api`](apps/api) (FastAPI). Local mock:

```bash
apps/api/scripts/smoke.sh   # SMOKE-OK health+mock-checkout
```
