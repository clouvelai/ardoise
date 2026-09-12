# Landing-hero proof (Phase 1 fixtures)

Captured from [clouvelai/ardoise](https://github.com/clouvelai/ardoise) at
`a5bc55df21508d1a803554e6b1c573f1623b8194` (`main`).

## Smoke

```
tests/fresh-box.sh
```

- Result: **FRESH-BOX-OK**
- Elapsed: **0.377s**
- Isolated `HOME` / `ARDOISE_HOME` (script default + a second ingest under `/tmp/ardoise-landing-proof.*`)

## Status numbers (2026-09)

| Field | Value |
|---|---|
| Projects | **1** (`clouvelai/Arbusteia`) |
| Month entries | **3** (3 total) |
| Spend | **$0.02105** (human status prints `$0.0210`) |
| Tokens | in=1700 out=550 cache_read=10000 cache_write=2000 |
| Sources | hook $0.0195 · anthropic_t0 $0.001 · cursor $0.00055 |

## Files

| Path | What |
|---|---|
| `status.txt` | Exact `bin/ardoise status --month 2026-09` |
| `status.json` | Exact `bin/ardoise status --json --month 2026-09` |
| `status.html` | Terminal-style marketing render of that status |
| `status.png` | Headless Chrome screenshot of `status.html` |
| `statement.md` / `.html` / `.csv` | `bin/ardoise statement 2026-09` |
| `statement.json` | CLI write-path metadata |
| `fresh-box.txt` | Smoke timing + totals |
