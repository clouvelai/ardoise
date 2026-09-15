---
name: ardoise-usage
description: >
  Read hosted Ardoise AI spend status and month statements. Use when the
  user asks for usage, spend, a statement, or how much a seat cost this
  month. Calls the ardoise MCP tools (status, statement). Never invent
  meters, invoices, or tax language.
---

# Ardoise hosted usage

Use the **ardoise** MCP server. It wraps the hosted companion
(`GET /v1/usage/status` and `GET /v1/usage/statement`).

## Tools

- `status` — month summary. Optional `month` as `YYYY-MM` (UTC).
- `statement` — spend document plus markdown and CSV. Optional `month`.

## Auth

The server reads `ARDOISE_API_TOKEN` (an `ard_…` CLI token from
`/app/settings`). If the token is missing, the tool returns a structured
error and does not crash. Ask the user to export the token or set it in
Cursor **Plugins → Configure**. Do not invent a token. Do not write
tokens to the repo or ledger.

## Language

This is a **spend statement**, not a tax invoice. Do not say "Amount
due". Free accounts see estimates; Pro+ may show billed Section A.

## Out of scope

Do not call local `bin/ardoise` from this skill. Do not mint Admin T2
keys. Do not persist prompts.
