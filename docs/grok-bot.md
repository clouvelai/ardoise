# Grok Bot

Install once → local ledger → hooks / usage-shaped capture →
`ardoise status` shows captain / Craie / Encre chips.

**No keys required for Free.** Do not mint Admin T2. Do not
estimate-from-prompt.

## 1. Soft notes when roots scanned but $0

Box and cloud-agent chats are often prompt-shaped JSON — no `usage` /
`tokenUsage` object. After `backfill` scans those trees and writes
nothing, that is expected.

`ardoise status` prints a **soft note** (never blocks):

```
roots scanned, no usage objects — prompt-only trees stay empty
until a usage-shaped export or hook lands
```

`ardoise backfill` prints the same tip when files were scanned and
`inserted=0`. Drop usage-shaped JSON/JSONL in `~/.ardoise/transcripts`
when you have it. No Admin key.

A live cloud-agent export on 2026-09-15 had `messages[]` with text and
tool calls only. Empty chips after that scan are correct.

## 2. `meter_gap` on `status --json`

```bash
ardoise status --json
```

includes `meter_gap`:

| Field | Meaning |
| --- | --- |
| `kind` | `prompt_only` when roots were scanned and no usage landed; `no_logs` when a capture pass found nothing; `null` when usage rows or spend already exist |
| `scanned` | A backfill/capture pass ran, or usage.json was found |
| `files` / `usage_rows` | Last backfill scan |
| `usage_json` / `usage_shaped` | Live count of `usage.json` / `usage.jsonl` files vs how many already carry tokens |
| `hook_queue` | Pending hook-queue files (not yet drained) |
| `hint` | Same soft sentence as the text note |

`kind` is never a reason to invent tokens or open Admin T2.

## 3. Hook / `usage.json` — capture only when usage-shaped

Free meters from:

- Capture hooks whose payload already includes token counts
- `usage.json` / `usage.jsonl` (and other transcripts) that already
  carry a `usage` / `tokenUsage` / `prompt_tokens` object
- `store.db` JSON blobs or `transcript_entries` that already carry tokens

Prompt-only files are scanned and skipped. `agent=` is copied from a
named profile / bot when present. Job titles are not agents.

Team / Enterprise Admin T2 (not Free): [meter-shape.md](meter-shape.md).
