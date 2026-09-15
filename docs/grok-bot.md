# Grok Bot

Install once → local ledger → hooks / usage-shaped capture →
`ardoise status` shows captain / Craie / Encre chips.

**No keys required for Free.**

## When chips show

Usage meters from:

- Capture hooks (the editor already emitted tokens)
- Usage-shaped transcripts (token objects on disk)

Until one of those lands, `status` stays quiet. That is expected.

## Meter gap

Box and cloud-agent chats are often prompt-shaped JSON — no `usage` /
`tokenUsage` object. A live cloud-agent export on 2026-09-15 had
`messages[]` with text and tool calls only. Ardoise does not invent
spend and does not estimate-from-prompt. Empty ledger after install →
backfill on those trees is correct.

When usage appears, these Free paths persist it (no Admin key):

- Hooks that already include token counts
- Usage-shaped JSON/JSONL under `~/.ardoise/transcripts`,
  `~/.cursor/agent-data`, `~/.cursor/projects/**/agent-transcripts`,
  or cloud-agent drop folders
- `store.db` / `index.db` rows or JSON blobs that already carry tokens

`agent=` is copied from a named profile / bot when present. Job titles
are not agents.

Free fills the remaining gap with usage-shaped exports or hooks — not
Admin.

Team / Enterprise Admin T2 (not Free): [meter-shape.md](meter-shape.md).
