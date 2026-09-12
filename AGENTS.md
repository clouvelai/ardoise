# Ardoise agents

Local AI spend ledger. Core is **Python 3 stdlib only**.

```bash
./install.sh --no-plugin-manager
bin/ardoise status --json
bin/ardoise backfill
bin/ardoise statement YYYY-MM
bin/ardoise statement YYYY-MM --person alice
bin/ardoise status --json --seat alice
bin/ardoise vendor test anthropic  # T2a probe; missing Analytics key skips T2a
bin/ardoise vendor pull anthropic  # T2a Analytics when ANTHROPIC_ANALYTICS_API_KEY is set
bin/ardoise vendor test cursor  # T2 probe; missing cred stays T0-only
bin/ardoise snapshot anthropic   # T1 seat snapshot when OAuth cred resolves
bin/ardoise invoice add --vendor anthropic --cycle YYYY-MM --usd-cents N
bin/ardoise invoice paste --file invoices.jsonl
bin/ardoise estimate --model MODEL --input-tokens N --output-tokens N
tests/fresh-box.sh   # must print FRESH-BOX-OK offline
```

- Ledger: `~/.ardoise/ledger.db`
- Config: `~/.ardoise/config.json` — optional `budgets.monthly_usd` / `budgets.person` / `budgets.project` (soft caps, warn only), `anomalies.*` knobs, and `roster` (name list or `{canonical: [aliases]}`)
- Roster filters on `status` / `statement` (`--person` / `--seat` / `--roster`) are view-only and never block
- Dedupe: `message.id` + `requestId` (keep highest `output_tokens`)
- Project: `git remote` `owner/repo`
- Attribution: persist `agent` / `skill` / `effort` when a T0 transcript or hook already names them; never invent; missing stays unattributed
- Never persist prompts or credentials
- Soft caps and `ardoise estimate` never block the editor
- Do not add third-party Python deps to `ardoise/`
- Hosted companion: `apps/api` (FastAPI + its own requirements). **Account first, card later** — OTP signup is free; Stripe Checkout (`mode=subscription`) only for Team/Business. Keep Stripe/JWT secrets server-side. Never add third-party Python deps to `ardoise/`.
