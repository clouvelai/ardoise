# Ardoise

Ardoise is a **local AI spend ledger** for [Claude Code](https://code.claude.com)
and [Cursor](https://cursor.com).

It reads on-disk usage into SQLite at `~/.ardoise/ledger.db` and prints month
statements. Core is **Python 3 standard library only**. Nothing leaves the
machine. Prompts and credentials are never stored.

## Install

Requires **Python 3** (standard library only). Pin
[v0.3.1](https://github.com/clouvelai/ardoise/releases/tag/v0.3.1):

```bash
curl -fsSL https://raw.githubusercontent.com/clouvelai/ardoise/v0.3.1/install.sh | sh
```

Or verify the SHA-256 first:

```bash
curl -fsSL https://raw.githubusercontent.com/clouvelai/ardoise/v0.3.1/install.sh -o install.sh
echo "36a4d5f90da173a6ba7285f0bfb49bf9d80964bb91222745bd82ef2ceef878a8  install.sh" | shasum -a 256 -c -
chmod +x install.sh && ./install.sh
```

**SHA-256** of `install.sh` at that tag: `36a4d5f90da173a6ba7285f0bfb49bf9d80964bb91222745bd82ef2ceef878a8`

Then verify:

1. `ardoise backfill`
2. `ardoise status`
3. Open Claude Code or Cursor once

No API keys required for capture. Signup is optional later for Pro/Team.

That copies self-contained hooks into `~/.ardoise/hooks/` and links
`bin/ardoise` to `~/.local/bin/ardoise`. If `~/.local/bin` is not on `PATH`,
add it. From a clone, `./install.sh` is the same default.

Claude marketplace add / Cursor local plugin are additive — see
[docs/install.md](docs/install.md). They are not the primary path.

Bare `ardoise` prints status. An empty ledger tells you to run `backfill`.

## Commands

```bash
ardoise                         # status for this UTC month
ardoise status --json
ardoise backfill                # Anthropic T0 + Cursor + ~/.ardoise/transcripts
ardoise status --month 2026-09 --roster Craie
ardoise capture                 # drain ~/.ardoise/queue
ardoise capture --stdin         # one hook event (used by plugins)
ardoise statement 2026-09       # writes MD + HTML + CSV
ardoise status --person alice
ardoise statement 2026-09 --seat alice   # YYYY-MM--alice.{md,html,csv}
ardoise export                  # JSONL of usage rows
ardoise export --month 2026-09 --out /tmp/ardoise.jsonl
ardoise vendor test anthropic   # T2a probe; skip if no Analytics API key
ardoise vendor pull anthropic   # ingest Analytics usage/cost when key is set
ardoise vendor test cursor      # T2 probe; T0-only if no Admin API key
ardoise vendor pull cursor      # ingest team usage events when key is set
ardoise invoice add --vendor anthropic --cycle 2026-09 --usd-cents 1950
ardoise invoice paste --file invoices.jsonl   # same upsert, bulk
ardoise estimate --model claude-sonnet-4-6 --input-tokens 1000 --output-tokens 400
ardoise estimate --stdin --json # hook-friendly ask on stdin
```

Statements land in `~/.ardoise/statements/YYYY-MM.{md,html,csv}`.

**Section A** is one vendor line per scope: pasted invoice, else T2, else T1 snapshot — each line prints its tier. **Section B** uses T0 token weights only to allocate that billed total across projects.

## How spend is captured

| Source | Adapter | Location |
|---|---|---|
| Claude Code session logs | `vendors/anthropic` T0 | `~/.claude/projects/**/*.jsonl` |
| Cursor transcripts | `vendors/cursor` T0 | `~/.cursor/**/*.jsonl` (usage-shaped; skips `agent-transcripts`) |
| Grok Bot / cloud-agent | `adapters/cloud_agent` T0 | configurable roots — see below |
| Claude Enterprise Analytics (optional T2a) | `vendors/anthropic` pull | `GET /v1/organizations/analytics/usage_report` when `ANTHROPIC_ANALYTICS_API_KEY` is set |
| Cursor Admin API (optional T2) | `vendors/cursor` pull | `POST /teams/filtered-usage-events` when `CURSOR_ADMIN_API_KEY` is set |
| Pasted invoices | `invoice paste` | ledger `invoices` table (section A) |
| Live sessions | Shared hooks + queue | `~/.ardoise/queue/*.json` |

Streaming duplicates share `message.id` + `requestId`. Ardoise keeps the row
with the highest `output_tokens`.

**Project** is the git remote `owner/repo` for the event `cwd` (or the current
workspace). T2 events join T0 hook rows on `conversation_id`; unmatched events
are stored as project `unattributed`. Without an Admin API key, Cursor capture
stays T0-only. The key is never written to the ledger.

**Attribution** (agent / skill / effort) is copied from T0 transcript and hook
JSON when those identifiers are already present (`agentId`, `attributionSkill`,
`effort`, `botName`, and a few stable aliases). Missing fields stay unattributed — Ardoise
never invents them from prompts, run titles, or defaults. `status` and the statement show a
quiet breakdown only when at least one row is named. Named agents also appear as
roster chips; `--person` / `--seat` / `--roster` match a seat *or* a named agent.
Section A vendor lines stay sparse.

In-editor Cursor chat is already T0. Named Grok Bot / cloud-agent exports
(`agent-data`, `transcript.json` + `index.json`) are not under `~/.cursor/projects`.
`install.sh` creates `~/.ardoise/transcripts`. Drop a fixture tree there and
plain `backfill` is enough — no flags, no keys:

```bash
./install.sh
mkdir -p ~/.ardoise/transcripts
cp -R tests/fixtures/dogfood/agent-data ~/.ardoise/transcripts/
ardoise backfill
ardoise status --month 2026-09
ardoise status --month 2026-09 --roster Craie
# or: tests/dogfood-grok.sh   # must print DOGFOOD-OK
```

If they already exist, backfill also reads `~/.cursor/cloud-agent-transcripts`,
`~/.cursor/agent-data`, and `~/agent-data`. Extra roots:
`ARDOISE_CLOUD_AGENT_ROOT`, `ARDOISE_AGENT_DATA`, `ARDOISE_TRANSCRIPT_PATHS`,
`--cloud-agent-root`, or `config.json` `transcripts.paths`. Hooks and the
adapter fail-open. Prompts are scrubbed. No marketplace or credentials.

**Anthropic T2a** lights up when the org primary owner mints an Analytics API
key at [claude.ai → Organization settings → API](https://claude.ai) (`read:analytics`)
and exports it as `ANTHROPIC_ANALYTICS_API_KEY` (alias: `ANTHROPIC_ANALYTICS_KEY`).
That key is not an Admin API key and not `ANTHROPIC_API_KEY`. Without it,
`vendor test anthropic` / `vendor pull anthropic` print a skip line and exit 0 —
T0 JSONL and T1 OAuth snapshots keep working. Analytics rows join T0 on
`session_id` / `conversation_id` (or an `owner/repo` `project` field) when the
payload exposes them; otherwise the project is `unattributed`.

Prices come from [`data/prices.fallback.json`](data/prices.fallback.json).
Override with `~/.ardoise/prices.json`.

## Soft caps, anomalies, estimate (Phase 3)

Optional `~/.ardoise/config.json` (override path with `ARDOISE_CONFIG`):

```json
{
  "budgets": {
    "monthly_usd": 100,
    "person": { "default": 80, "alice": 40 },
    "project": { "clouvelai/ardoise": 25 }
  },
  "anomalies": {
    "day_multiple": 3,
    "trailing_days": 14,
    "min_days": 3,
    "min_day_usd": 1,
    "project_share": 0.75,
    "min_month_usd": 1
  },
  "roster": {
    "alice": ["alice@acme.com"],
    "bob": []
  }
}
```

`ardoise status` and `--json` show vs-cap % for each configured scope and flag
when spend is over the soft cap. Overages are **warn only** — capture hooks and
the editor are never blocked.

Anomaly notes are local heuristics (a day well above the trailing median, or
one project taking most of the month). They appear on status/statement as soft
notes, not an alerts pipeline.

`ardoise estimate` prices a hypothetical token/model ask from the price table.
Hooks may call it later; it writes nothing, needs no network, and always exits 0.

## Roster filters (multi-seat)

`status` and `statement` accept `--person` / `--seat` / `--roster` to view one
seat **or named agent**. The filter is **read-only**: it does not write the
ledger and unknown names exit 0 with an empty view plus a soft note.

Roster members come from existing `person` columns on events, snapshots, and
invoices (the same dimension T1/T2 and `invoice --person` already store).
Named `events.agent` values (Craie, Encre, captain, …) are first-class on the
same flags and show as quiet chips when present. Optional `config.json`
`roster` is a name list or `{canonical: [aliases]}` map so `alice` and
`alice@acme.com` resolve to one seat.

Unfiltered statements stay `YYYY-MM.{md,html,csv}`. Filtered files use
`YYYY-MM--alice.{md,html,csv}` so a seat or agent view does not clobber the org
statement. HTML adds a quiet seat/agent chip — no roster tables.

## Privacy

The ledger stores model, tokens, timestamps, ids, `owner/repo`, and optional
agent / skill / effort identifiers when the source named them. Capture
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

A hosted companion follows [`docs/saas-scaffold.md`](docs/saas-scaffold.md):
**account first, card later**. Supabase email OTP creates a free account
(no card). Stripe Checkout Sessions (`mode=subscription`) run only when
someone pays for Pro ($20/mo) or Team ($49/mo). Invoice-grade claims
stay Pro+. Phase 1 CLI does not call those services.

Scaffold lives in [`apps/api`](apps/api) (FastAPI). Local mock:

```bash
apps/api/scripts/smoke.sh   # SMOKE-OK health+mock-checkout+otp+billing
```

## License

[MIT](LICENSE) © 2026 clouvelai. Vulnerability reports: [SECURITY.md](SECURITY.md).
