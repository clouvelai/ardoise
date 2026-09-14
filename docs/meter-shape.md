# Meter shape

**Team / Enterprise Admin only — not Free.**

Product story (Free): [grok-bot.md](grok-bot.md).

Install and `backfill` never require API keys. They only persist rows that
already carry a usage object (token counts and/or charged cents). Hooks do
the same: they meter when the editor already emitted usage.

## Prompt-only cloud / box trees

Cursor cloud-agent and Grok Bot box exports are often chat/prompt JSON.
Those files have **no** `usage` / `tokenUsage` object. Fail-open is
correct: they are skipped. An empty ledger after `install` → `backfill` on
a prompt-only tree is expected.

Ardoise does **not** invent meters and does **not** estimate-from-prompt.

Until a usage-shaped export or hook includes usage objects, those trees
will not show spend. Admin T2 is not the Free fix for empty chips.

## What actually meters (Free)

| Path | When it counts |
| --- | --- |
| In-editor Cursor T0 hooks | Hook payload already includes usage. `agent=` is copied only when the hook already named one. |
| T0 JSONL (Claude / Cursor / usage-shaped cloud-agent) | Transcript line already has tokens. Named `agent` / `skill` / `effort` are copied when present. |

`tests/fresh-box.sh` and `tests/dogfood-grok.sh` stay on this path.
No keys.

T0 dollars are list-price estimates from the bundled price book
([docs/t0-prices.md](t0-prices.md)). Cursor hooks often send
`model=default`; capture prefers `model_id` / a nested real slug and
persists `unknown` (priced $0) when none exists. Grok and Composer SKUs
do not fall through to Claude Sonnet rates.

## Team / Enterprise Admin only — not Free

Cursor Admin T2 is **not** a next step after install. It needs a real
Team / Enterprise Admin key on a plan that exposes the Team Admin API
(cursor.com/dashboard → API Keys, `admin:*` when available). Solo /
personal keys — including `CURSOR_API_KEY` — often get `401 Invalid
Team API Key` and are not used for live probe. Do not treat Admin
smoke as working today.

`CURSOR_ADMIN_API_KEY` plus `ardoise vendor pull cursor` can fetch
Admin usage events. Live probe ignores `CURSOR_API_KEY`. Missing or
ineligible key → T0-only skip, exit 0. CI and offline tests use
fixtures/mocks only — no live key.

### How T2 join sets `agent=`

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
