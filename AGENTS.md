# Ardoise agents

Local AI spend ledger. Core is **Python 3 stdlib only**.

```bash
./install.sh --no-plugin-manager
bin/ardoise status --json
bin/ardoise backfill
bin/ardoise statement YYYY-MM
tests/fresh-box.sh   # must print FRESH-BOX-OK offline
```

- Ledger: `~/.ardoise/ledger.db`
- Dedupe: `message.id` + `requestId` (keep highest `output_tokens`)
- Project: `git remote` `owner/repo`
- Never persist prompts or credentials
- Do not add third-party Python deps to `ardoise/`
- Hosted companion scaffold: `apps/api` (FastAPI + its own requirements). Keep Stripe/JWT secrets server-side.
