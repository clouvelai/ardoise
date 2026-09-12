# Ardoise agents

Local AI spend ledger. Core is **Python 3 stdlib only**.

```bash
./install.sh --no-plugin-manager
bin/ardoise status --json
bin/ardoise backfill
bin/ardoise statement YYYY-MM
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
- Config: `~/.ardoise/config.json` — optional `budgets.monthly_usd` / `budgets.person` / `budgets.project` (soft caps, warn only) and `anomalies.*` knobs
- Dedupe: `message.id` + `requestId` (keep highest `output_tokens`)
- Project: `git remote` `owner/repo`
- Never persist prompts or credentials
- Soft caps and `ardoise estimate` never block the editor
- Do not add third-party Python deps to `ardoise/`
- Hosted companion scaffold: `apps/api` (FastAPI + its own requirements). Keep Stripe/JWT secrets server-side.
