# Grok Bot

Install once → local ledger → when usage meters, `ardoise status`
shows captain / Craie / Encre chips.

**No keys required for Free.**

## When chips show

Usage meters from:

- Capture hooks (the editor already emitted tokens)
- Usage-shaped transcripts (token objects on disk)
- Optional Admin T2 (`CURSOR_ADMIN_API_KEY` + `ardoise vendor pull cursor`)

Until one of those lands, `status` stays quiet. That is expected.

## Meter gap

Box and cloud-agent chats are often prompt-shaped JSON — no `usage` /
`tokenUsage` object. Ardoise does not invent spend and does not
estimate-from-prompt. Empty ledger after install → backfill on those
trees is correct.

## Optional Admin T2

`vendor pull cursor` can join team usage to a named agent when
`cloudAgentId` / `bcId` or `conversationId` is already known.

This may need Cursor Enterprise. It is never required at install,
backfill, or Free. Missing key stays T0-only.

Join rules: [meter-shape.md](meter-shape.md).
