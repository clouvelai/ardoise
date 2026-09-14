# Meter shape

Install and `backfill` never require API keys. They only persist rows that
already carry a usage object (token counts and/or charged cents). Hooks do
the same: they meter when the editor already emitted usage.

## Prompt-only cloud / box trees

Cursor cloud-agent and Grok Bot box exports are often chat/prompt JSON.
Those files have **no** `usage` / `tokenUsage` object. Fail-open is
correct: they are skipped. An empty ledger after `install` → `backfill` on
a prompt-only tree is expected.

Ardoise does **not** invent meters and does **not** estimate-from-prompt.

Until a platform export includes usage objects, **or** optional Cursor
Admin T2 can join a known run, those trees will not show spend.

## What actually meters

| Path | When it counts |
| --- | --- |
| In-editor Cursor T0 hooks | Hook payload already includes usage. `agent=` is copied only when the hook already named one. |
| T0 JSONL (Claude / Cursor / usage-shaped cloud-agent) | Transcript line already has tokens. Named `agent` / `skill` / `effort` are copied when present. |
| Optional Cursor Admin T2 | `CURSOR_ADMIN_API_KEY` (alias `CURSOR_API_KEY`) is set. `ardoise vendor pull cursor` fetches Admin usage events. |

T2 is never required at install, backfill, or `tests/fresh-box.sh` /
`tests/dogfood-grok.sh`. Missing key → T0-only skip, exit 0.

## How T2 join sets `agent=`

Admin usage events do not name a launching agent. They expose join keys:

- `conversationId` — in-editor / hook session id (T0 `session_id`)
- `cloudAgentId` — cloud-agent run id (`bc-…`, also accepted as `bcId`)

When one of those ids matches a **known** named run, T2 copies `agent=`
via `ardoise.attribution` (never invented):

1. T0 hook or usage-shaped transcript row already stored with that
   `session_id` and a named `agent`
2. Local cloud-agent sidecar (`index.json` / `run.json`) that already
   names `agentName` / `botName` for that `bcId`

Unknown ids stay unattributed. Job titles, folder names, and prompt text
are never treated as agent names. Project join is unchanged: conversation
→ T0 `owner/repo`, else project `unattributed`.

Admin dogfood needs a real team Admin API key. CI and offline tests use
fixtures/mocks only — no live key.
