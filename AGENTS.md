# Ardoise agents

Local AI spend ledger. Core is **Python 3 stdlib only**.

```bash
./install.sh
bin/ardoise status --json
bin/ardoise backfill
bin/ardoise status --month 2026-09 --roster Craie
bin/ardoise statement YYYY-MM
bin/ardoise statement YYYY-MM --person alice
bin/ardoise status --json --seat alice
bin/ardoise status --json --person Craie
bin/ardoise snapshot anthropic   # T1 seat snapshot when OAuth cred resolves
bin/ardoise invoice add --vendor anthropic --cycle YYYY-MM --usd-cents N
bin/ardoise invoice paste --file invoices.jsonl
bin/ardoise estimate --model MODEL --input-tokens N --output-tokens N
bin/ardoise reprice                # rewrite T0 cost_usd from the current price book
bin/ardoise login --token TOKEN   # from hosted /app/settings
bin/ardoise sync
tests/fresh-box.sh   # must print FRESH-BOX-OK offline
tests/dogfood-grok.sh  # install → backfill → status chips with Craie/Encre/captain spend
python3 plugins/marketplace/mcp/server.py --check  # hosted MCP stub; ARDOISE_API_TOKEN for live calls
```

- Ledger: `~/.ardoise/ledger.db`
- Config: `~/.ardoise/config.json` — optional `budgets.monthly_usd` / `budgets.person` / `budgets.project` (soft caps, warn only), `anomalies.*` knobs, `roster` (name list or `{canonical: [aliases]}`), `transcripts.paths` (extra Grok Bot / cloud-agent dirs), and `statement.from` / `statement.prepared_for` (letterhead for Orb-floor spend statements)
- Roster filters on `status` / `statement` (`--person` / `--seat` / `--roster`) are view-only and never block. Named `events.agent` values are first-class on the same flags.
- Dedupe: `message.id` + `requestId` (keep highest `output_tokens`)
- Project: `git remote` `owner/repo`
- Attribution: persist `agent` / `skill` / `effort` when a T0 transcript or hook already names them; never invent; missing stays unattributed
- Meter-shape: prompt-only cloud/box transcripts do not meter (empty ledger is expected). Usage-shaped JSONL, hooks, `agent-transcripts`, and `store.db` rows meter when they already carry tokens. Install/backfill/dogfood never require keys. Team / Enterprise only (not Free): `vendor test cursor` / `vendor pull cursor` and `vendor test anthropic` / `vendor pull anthropic` — see [docs/meter-shape.md](docs/meter-shape.md). Individual Cursor plans have no Team Admin API key. Anthropic Analytics is Enterprise-only.
- Never persist prompts or credentials
- Soft caps and `ardoise estimate` never block the editor
- T0 prices: bundled `data/prices.fallback.json` (no network). Cursor `default`/`auto` persist as `unknown` ($0), never Sonnet. `ardoise reprice` rewrites existing T0 `cost_usd` from the current book (no re-ingest). See [docs/t0-prices.md](docs/t0-prices.md).
- Do not add third-party Python deps to `ardoise/`
- Hosted companion: `apps/api` (FastAPI + its own requirements). **Account first, card later** — OTP signup is free; Stripe Checkout (`mode=subscription`) only for Pro/Team. `ardoise login` / `ardoise sync` upload already-priced export rows. Keep Stripe/JWT secrets server-side. Never add third-party Python deps to `ardoise/`.
- Cursor marketplace Agent Plugin: `plugins/marketplace/` (`plugin.json` + MCP `status`/`statement` over `https://api-production-ea055.up.railway.app`). Auth env `ARDOISE_API_TOKEN` (`ard_…`). Not the hooks CLI scaffold. No secrets in the pack.
