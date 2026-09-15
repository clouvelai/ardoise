# Ardoise Cursor marketplace plugin

Agent Plugin pack (`plugin.json` + `mcp.json` + `skills/`) for the
Cursor **Marketplace → Plugins** tab. This is **not** the hooks CLI
scaffold under `plugins/cursor/`.

The MCP server is a thin hosted-API stub:

| Tool | Hosted route |
|---|---|
| `status` | `GET /v1/usage/status` |
| `statement` | `GET /v1/usage/statement` |

Default origin:
`https://api-production-ea055.up.railway.app`

MIT. No secrets in this tree. Tokens stay in the environment.

## Auth

Export a CLI token minted at hosted `/app/settings`:

```bash
export ARDOISE_API_TOKEN=ard_…   # never commit
# optional override (local API / preview)
# export ARDOISE_API_URL=http://127.0.0.1:8787
```

Cursor Marketplace / team install: set the same names under
**Plugins → Configure**. They are declared in
`.cursor-plugin/plugin.json` → `variables` (the marketplace env schema).
The plugin never stores the values.

`ARDOISE_API_URL` defaults to production. Unexpanded `${ARDOISE_API_URL}`
placeholders are ignored.

## Run the MCP server locally

Stdlib Python 3. From this directory:

```bash
export ARDOISE_API_TOKEN=ard_…    # from /app/settings
python3 mcp/server.py --check     # prints tools + whether a token is set
# Cursor / Claude spawn the stdio server:
python3 mcp/server.py
```

`--check` never prints the token and exits 0 even when it is missing
(fail-open). A missing token on `status` / `statement` returns
`{"ok": false, "error": "missing_token", ...}` instead of crashing.

Point Cursor at this folder as a local plugin, or add a stdio MCP entry:

```json
{
  "mcpServers": {
    "ardoise": {
      "command": "python3",
      "args": ["./plugins/marketplace/mcp/server.py"],
      "env": {
        "ARDOISE_API_TOKEN": "ard_…"
      }
    }
  }
}
```

Do not paste a live token into a committed file. Use your user MCP
config or the shell.

Dogfood once a fresh `ard_` is available:

1. Sign in on the hosted app → **Settings** → mint a CLI token.
2. `export ARDOISE_API_TOKEN=ard_…`
3. `python3 plugins/marketplace/mcp/server.py --check` → `token_set: true`
4. In Cursor, ask for this month's usage / statement and confirm the
   `status` and `statement` tools hit production.

## Pack shape

```
plugins/marketplace/
  plugin.json                 Agent Plugins 1.0.0 manifest
  mcp.json                    stdio MCP (python3 ./mcp/server.py)
  .cursor-plugin/plugin.json  Cursor manifest + variables schema
  mcp/server.py               hosted-API stub (stdlib)
  skills/ardoise-usage/       short skill
  README.md
```

Repo catalog: [`.cursor-plugin/marketplace.json`](../../.cursor-plugin/marketplace.json)
(`source`: `./plugins/marketplace`). Existing capture hooks stay under
`plugins/cursor/` and are not this listing.

## Create Plugin / marketplace submit (later)

Out of scope for this PR — mapping only:

1. **Create Plugin** in Cursor: pick this directory (or the repo, which
   already has `.cursor-plugin/marketplace.json`). Confirm the Agent
   Plugin `plugin.json` and the Cursor `variables` schema for
   `ARDOISE_API_TOKEN`.
2. Host the repo publicly (`clouvelai/ardoise`).
3. Submit at [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish)
   with the repository URL. Review is manual.
4. After listing, install from the **Plugins** tab and set
   `ARDOISE_API_TOKEN` in Configure. Do not embed tokens in the
   submission.

Local-ledger MCP (talking to `~/.ardoise/ledger.db`) is a later stretch.
This pack talks to the hosted API only.
