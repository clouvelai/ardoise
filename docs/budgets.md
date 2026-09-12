# Soft budgets and anomaly flags

Phase 3 PR1. Caps and flags **warn only**. Capture, backfill, status, and
statement always complete; nothing is hard-blocked.

## Where caps live

`~/.ardoise/budgets.json` (override with `ARDOISE_BUDGETS`). This is user
config, not ledger rows — it is not stored in `ledger.db`.

```json
{
  "version": 1,
  "budgets": [
    {"id": "month:usd", "period": "month", "metric": "usd", "limit": 50.0},
    {"id": "day:tokens", "period": "day", "metric": "tokens", "limit": 1000000}
  ]
}
```

Identity is `(period, metric)`. `ardoise budget set` upserts.

| Field | Values | Notes |
|---|---|---|
| `period` | `day` / `month` (`daily` / `monthly` accepted) | UTC |
| `metric` | `usd` or `tokens` | tokens = input + output (cache ignored) |
| `limit` | number `> 0` | tokens must be a whole number |

A corrupt file is ignored by `status` (treated as no caps).

## How used is computed

- **Month USD** — invoice-grade `billed_usd` when section A has an invoice / T1 / T2 total, otherwise the T0 `estimated_usd`.
- **Day USD** — event `billed_cents` when present, else T0 `cost_usd`, summed for the reference UTC day (`as_of` if it falls in the month, else the last day of that month).
- **Tokens** — `input_tokens + output_tokens` for the same day/month window.

Headroom states: `ok` under 80% of the cap, `warn` at 80–100%, `over` at or above 100%. The 80% line is `WARN_RATIO` in `ardoise/budget.py`.

## Anomaly rules

Deterministic. Implemented in `ardoise/alerts.py`. Fixtures in `tests/fixtures/alerts.json`.

1. **`day_spike`** — a UTC day in the month is at least **3×** the mean of prior days that have spend in the previous **7** days, with at least **3** such prior days, and the day itself is at least **$0.05**.
2. **`session_outlier`** — a session in the month is at least **3×** the median of the other sessions, with at least **4** sessions in the month, and the session itself is at least **$0.05**.

Sessions use `session_id` when present, otherwise `msg:{message_id}`. Days without enough baseline stay quiet (no false spike on a first-week ledger).

## CLI

```bash
bin/ardoise budget set --period month --usd 50
bin/ardoise budget set --period day --tokens 1000000
bin/ardoise budget list
bin/ardoise budget list --json
```

Edit the JSON file directly if you prefer. Re-runs are idempotent.

## Surfacing

- `ardoise status` prints one `budget` line per cap and an `alerts` line when flags exist. `--json` includes `budgets`, `flags`, and `daily_ready`.
- Statement **Alerts** is a short strip above section A (Markdown + HTML). Section A vendor lines are unchanged. CSV is unchanged.

## `daily_ready` JSON (hook for a later HTTP route)

Do not add the HTTP endpoint here. `ardoise.alerts.daily_ready()` is the payload
`status` already embeds as `daily_ready`:

```json
{
  "schema": "ardoise.daily_ready.v1",
  "month": "2026-09",
  "as_of": "2026-09-12T18:00:00Z",
  "day": "2026-09-12",
  "budgets": [{"id": "month:usd", "period": "month", "metric": "usd", "limit": 50, "used": 21.05, "remaining": 28.95, "ratio": 0.421, "state": "ok", "basis": "billed"}],
  "flags": [{"kind": "day_spike", "severity": "warn", "message": "...", "detail": {}}]
}
```

Flag `kind` values: `budget_warn`, `budget_over`, `day_spike`, `session_outlier`.
