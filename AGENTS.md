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
tests/fresh-box.sh   # must print FRESH-BOX-OK offline
tests/dogfood-grok.sh  # install → backfill → status chips with Craie/Encre/captain spend
```

- Ledger: `~/.ardoise/ledger.db`
- Config: `~/.ardoise/config.json` — optional `budgets.monthly_usd` / `budgets.person` / `budgets.project` (soft caps, warn only), `anomalies.*` knobs, `roster` (name list or `{canonical: [aliases]}`), and `transcripts.paths` (extra Grok Bot / cloud-agent dirs)
- Roster filters on `status` / `statement` (`--person` / `--seat` / `--roster`) are view-only and never block. Named `events.agent` values are first-class on the same flags.
- Dedupe: `message.id` + `requestId` (keep highest `output_tokens`)
- Project: `git remote` `owner/repo`
- Attribution: persist `agent` / `skill` / `effort` when a T0 transcript or hook already names them; never invent; missing stays unattributed
- Meter-shape: prompt-only cloud/box transcripts do not meter (empty ledger is expected). Install/backfill/dogfood never require keys. Team / Enterprise only (not Free): `vendor test cursor` / `vendor pull cursor` and `vendor test anthropic` / `vendor pull anthropic` — see [docs/meter-shape.md](docs/meter-shape.md). Individual Cursor plans have no Team Admin API key. Anthropic Analytics is Enterprise-only.
- Never persist prompts or credentials
- Soft caps and `ardoise estimate` never block the editor
- Do not add third-party Python deps to `ardoise/`
- Hosted companion: `apps/api` (FastAPI + its own requirements). **Account first, card later** — OTP signup is free; Stripe Checkout (`mode=subscription`) only for Pro/Team. Keep Stripe/JWT secrets server-side. Never add third-party Python deps to `ardoise/`.
