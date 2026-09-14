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

## Optional Admin T2 (advanced)

`vendor pull cursor` can join team usage to a named agent when
`cloudAgentId` / `bcId` or `conversationId` is already known.
This is not a post-install next step.

That join path is fine. The key often is not. Solo / personal keys
commonly get Cursor `401 Invalid Team API Key`. Admin T2 needs a real
Team / Enterprise Admin key on a plan that exposes the Team Admin API.

Do not treat Admin smoke as working today. Missing or ineligible key
stays T0-only. Free stays zero-key — never required at install or
backfill.

Join rules: [meter-shape.md](meter-shape.md).
