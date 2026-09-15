# Ardoise

Ardoise is a **local AI spend ledger** for [Claude Code](https://code.claude.com)
and [Cursor](https://cursor.com).

It reads on-disk usage into SQLite at `~/.ardoise/ledger.db` and prints month
statements. Core is **Python 3 standard library only**. Nothing leaves the
machine. Prompts and credentials are never stored.

## Install

Requires **Python 3** (standard library only). Pin
[v0.3.3](https://github.com/clouvelai/ardoise/releases/tag/v0.3.3):

```bash
curl -fsSL https://raw.githubusercontent.com/clouvelai/ardoise/v0.3.3/install.sh | sh
```

Or verify the SHA-256 first:

```bash
curl -fsSL https://raw.githubusercontent.com/clouvelai/ardoise/v0.3.3/install.sh -o install.sh
echo "417344fac213bd1bf330227b754d96971920db4a47d5589f3fac7997d7ddeaa8  install.sh" | shasum -a 256 -c -
chmod +x install.sh && ./install.sh
```

**SHA-256** of `install.sh` at that tag: `417344fac213bd1bf330227b754d96971920db4a47d5589f3fac7997d7ddeaa8`

That stages the engine at `~/.local/share/ardoise` (so a git clone is not
required at runtime) and links `~/.local/bin/ardoise`. Then:

1. `ardoise backfill`
2. `ardoise status`
3. Open Claude Code or Cursor once
4. Optional: sign up, `ardoise login`, `ardoise sync` for the hosted ledger

Claude marketplace add / Cursor local hooks plugin are additive — see
[docs/install.md](docs/install.md). They are not the primary path.

Cursor **Marketplace → Plugins** listing is the Agent Plugin pack under
[`plugins/marketplace/`](plugins/marketplace/) (`plugin.json` + MCP
`status` / `statement` over the hosted API). That is a different scaffold
from the hooks CLI capture under `plugins/cursor/`.

Bare `ardoise` prints status. An empty ledger tells you to run `backfill`.

## Grok Bot

Install once → local ledger → hooks / usage-shaped capture → `status`
with captain / Craie / Encre chips. **No keys required for Free.**

Box / cloud-agent chats can be prompt-shaped with no token objects.
Until a usage-shaped export or hook lands, `status` stays quiet. That
is expected.

[docs/grok-bot.md](docs/grok-bot.md) · [docs/meter-shape.md](docs/meter-shape.md)

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
ardoise invoice add --vendor anthropic --cycle 2026-09 --usd-cents 1950
ardoise invoice paste --file invoices.jsonl   # same upsert, bulk
ardoise estimate --model claude-sonnet-4-6 --input-tokens 1000 --output-tokens 400
ardoise reprice                 # rewrite T0 cost_usd from the current price book
ardoise reprice --month 2026-09 --json
ardoise login --token ard_…    # token from /app/settings
ardoise sync
ardoise logout
```

Statements land in `~/.ardoise/statements/YYYY-MM.{md,html,csv}`.

**Team / Enterprise only (not Free):** `vendor test cursor` /
`vendor pull cursor` and `vendor test anthropic` /
`vendor pull anthropic` → [docs/meter-shape.md](docs/meter-shape.md).
Individual Cursor plans have no Team Admin API key. Anthropic Analytics
is Enterprise-only. Free stays T0.

**Section A** is one vendor line per scope: pasted invoice, else T2, else T1 snapshot — each line prints its tier. **Section B** uses T0 token weights only to allocate that billed total across projects.

## How spend is captured

| Source | Adapter | Location |
|---|---|---|
| Claude Code session logs | `vendors/anthropic` T0 | `~/.claude/projects/**/*.jsonl` |
| Cursor transcripts | `vendors/cursor` T0 | `~/.cursor/**/*.jsonl` (usage-shaped; skips `agent-transcripts`) |
| Grok Bot / cloud-agent | `adapters/cloud_agent` T0 | configurable roots — see below |

Streaming duplicates share `message.id` + `requestId`. Ardoise keeps the row
with the highest `output_tokens`.

**Project** is the git remote `owner/repo` for the event `cwd` (or the current
workspace). T2 events join T0 hook rows on `conversation_id`; unmatched events
are stored as project `unattributed`. Cursor capture stays T0-only on the
Free path.

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

Usage-shaped fixtures (like `tests/fixtures/dogfood/agent-data`) produce
agent chips. Live cloud/box trees that are prompt-only will **not** meter
until a usage-shaped export or hook lands. Empty chips are a Free
meter-gap, not a reason to mint an Admin key. Empty ledger after
install → backfill on those trees is expected. No keys required. Do not
estimate-from-prompt.

**Anthropic T2a** lights up when the org primary owner mints an Analytics API
key at [claude.ai → Organization settings → API](https://claude.ai) (`read:analytics`)
and exports it as `ANTHROPIC_ANALYTICS_API_KEY` (alias: `ANTHROPIC_ANALYTICS_KEY`).
That key is not an Admin API key and not `ANTHROPIC_API_KEY`. Without it,
`vendor test anthropic` / `vendor pull anthropic` print a skip line and exit 0 —
T0 JSONL and T1 OAuth snapshots keep working. Analytics rows join T0 on
`session_id` / `conversation_id` (or an `owner/repo` `project` field) when the
payload exposes them; otherwise the project is `unattributed`.

Prices come from [`data/prices.fallback.json`](data/prices.fallback.json)
(T0 list-price estimate only). Override with `~/.ardoise/prices.json`.
Cursor / `cursor-grok-*` SKUs use published Cursor list prices — see
[docs/t0-prices.md](docs/t0-prices.md). Missing or Auto/`default` models
store as `unknown` and do **not** inherit Claude Sonnet $3/$15.

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

Hosted MCP stub (marketplace plugin, no network in unit tests):

```bash
python3 -m unittest tests/test_marketplace_plugin.py
# local stdio server (needs a real ard_ token to call production):
# ARDOISE_API_TOKEN=ard_… python3 plugins/marketplace/mcp/server.py --check
```

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
