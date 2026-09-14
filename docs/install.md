# Install (maintainers)

Canonical Phase 1 install is still clone-then-`./install.sh`. That path:

1. Links `bin/ardoise` → `~/.local/bin/ardoise`
2. Copies **self-contained** capture/snapshot scripts (plus `hook_enqueue.py`)
   into `~/.ardoise/hooks/`
3. Merges those absolute paths into `~/.claude/settings.json` and
   `~/.cursor/hooks.json`

`--no-plugin-manager` is accepted and is the default. Hooks never store
credentials or prompts. Every hook is **fail-open** (`trap 'exit 0' EXIT`
plus `|| true` around the CLI) so a missing or crashing `ardoise` never
blocks the editor. Soft caps and `ardoise estimate` also never block.

## Runtime contract

Installed hooks and plugin entrypoints must invoke:

- `ARDOISE_BIN` if set and executable, else
- `ardoise` on `PATH`, else
- `~/.local/bin/ardoise`

They must **not** `exec ../shared/...` (or any other path that assumes the
monorepo layout). `install.sh` copies `plugins/shared/*.sh` into
`~/.ardoise/hooks/`; those copies are the source of truth for the
`--no-plugin-manager` merge.

`plugins/claude/hooks/*.sh` and `plugins/cursor/capture.sh` are
marketplace-safe stubs: they prefer `$ARDOISE_HOME/hooks` (default
`~/.ardoise/hooks`) and otherwise call the CLI. Copying only
`plugins/claude` out of the repo is enough for Claude Code's plugin
manager — no sibling `plugins/shared` directory is required.

`hook_enqueue.py` is copy-safe (import `ardoise` or exit 0). It does not
walk up to a repo root.

## Plugin manager

Phase 1 does not invoke a marketplace. If a user later installs the Claude
plugin via a plugin manager, the bundled stubs still resolve the
`install.sh` hooks or `ardoise` on PATH. Keep shipping the CLI via
`install.sh` (or a later tagged `curl | sh`).

## Follow-ups (not this change)

- Claude `.claude-plugin/marketplace.json` catalog
- Cursor `.cursor-plugin/plugin.json` scaffold
- Tagged release + checksummed `curl | sh` one-liner
- Marketing Install surface (Encre)
