# Install (maintainers)

Customer install is `curl | sh` (or a verified copy of `install.sh`). That
fetches a tagged archive unless `ARDOISE_TARBALL` is set, stages the engine
at `~/.local/share/ardoise`, and links `~/.local/bin/ardoise`. Deleting a
git clone afterwards is fine.

From a clone, `./install.sh` is the same: it still copies into the prefix
so runtime does not depend on the checkout.

That path:

1. Stages `ardoise/`, `data/`, `bin/`, `plugins/shared/` under
   `~/.local/share/ardoise`
2. Links `~/.local/bin/ardoise` → that prefix
3. Copies **self-contained** capture/snapshot scripts (plus `hook_enqueue.py`)
   into `~/.ardoise/hooks/`
4. Merges those absolute paths into `~/.claude/settings.json` and
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

## Plugin manager (additive)

Canonical install remains `./install.sh`. Marketplace / plugin-manager
paths are additive and never required. They ship **zero credentials**.

### Claude Code marketplace

In-repo catalog: [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json)
(plugin source `./plugins/claude`).

```
/plugin marketplace add clouvelai/ardoise
/plugin install ardoise@ardoise
```

Bundled stubs still resolve the `install.sh` hooks or `ardoise` on PATH.

When the Claude Code CLI is available, validate the catalog and plugin:

```
claude plugin validate .
claude plugin validate ./plugins/claude
```

The first checks `marketplace.json` (and each local plugin source). The
second checks that plugin's `plugin.json` and `hooks/hooks.json`.

### Cursor local plugin (dogfood)

First-class layout lives under `plugins/cursor/`
(`.cursor-plugin/plugin.json` + `hooks/hooks.json`). Copy or symlink it
into `~/.cursor/plugins/local` and reload the window:

```
mkdir -p ~/.cursor/plugins/local
cp -R plugins/cursor ~/.cursor/plugins/local/ardoise
# or: ln -s "$(pwd)/plugins/cursor" ~/.cursor/plugins/local/ardoise
```

Whole-checkout dogfood also works: repo-root
[`.cursor-plugin/plugin.json`](../.cursor-plugin/plugin.json) points hooks
at `plugins/cursor/capture.sh`.

```
ln -s "$(pwd)" ~/.cursor/plugins/local/ardoise
```

This scaffold does **not** replace `install.sh`'s merge into
`~/.cursor/hooks.json`. Keep using `./install.sh` as the secure user path.

Env for the lone-script path: `ARDOISE_TAG` (default `v0.3.3`),
`ARDOISE_TARBALL` (offline tests), `ARDOISE_PREFIX`.
