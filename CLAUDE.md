# mcp_browser_use

MCP server that wraps Selenium + Chrome DevTools Protocol so multiple AI agents can
share one Chrome user-data-dir, each in their own window, with the same persistent
profile (logins/cookies/extensions). Coordinates with file-based locks.

## Rules & Instructions

Detailed instructions live in `.claude/rules/`:

| File | Content |
|------|---------|
| [architecture.md](.claude/rules/architecture.md) | Tech stack, package layout, key abstractions |
| [mcp-tools.md](.claude/rules/mcp-tools.md) | All `mcp_browser_use__*` tools, signatures, purpose |
| [browser-config.md](.claude/rules/browser-config.md) | Chrome/profile env vars, channel priority, DevTools port |
| [locking.md](.claude/rules/locking.md) | Action lock, window registry, startup mutex, orphan cleanup |
| [deployment.md](.claude/rules/deployment.md) | Git workflow, install, repo branch (`master`), gitignore'd files |

## Project Overview

- **Transport**: stdio MCP server (FastMCP) launched by an agent host (Claude Code,
  Codex CLI, fast-agent, etc.) via `.mcp.json`.
- **Backend**: Selenium 4 driving Chrome (preferably Beta/Canary) over the
  Chrome DevTools Protocol on a fixed or dynamic debug port.
- **Multi-agent model**: every agent spawns its own MCP process; processes
  cooperate via file locks in `tmp/mcp_locks/` keyed by SHA-256 of
  `user_data_dir|profile_name`. New agents attach to an already-running Chrome
  and open their own window (TargetId).
- **Output shape**: each tool returns a JSON `ContextPack` — configurable
  `return_mode` (`outline` / `text` / `html` / `dompaths` / `mixed`),
  `cleaning_level` (0-3), and `token_budget` so HTML snapshots stay below the
  model context window.

## Tech Stack

- **Language**: Python 3.x (`src/` layout, `pyproject.toml`)
- **MCP framework**: `mcp.server.fastmcp.FastMCP`
- **Browser**: `selenium >= 4.30` + Chrome / Chrome Beta / Chrome Canary
- **HTML cleaning**: `beautifulsoup4`, custom cleaners in
  `src/mcp_browser_use/cleaners.py`
- **Locks**: file mutexes + softlock JSON in `tmp/mcp_locks/` (no DB)
- **Tests**: pytest (no pytest-asyncio); fast-agent for e2e
- **Config**: env vars only — defined in the agent host's `.mcp.json`, NOT in
  `.env` (the MCP subprocess only inherits explicitly passed env)

## Key Conventions

1. **Env vars in `.mcp.json` only** — agent hosts launch the MCP as a
   subprocess; `.env` files are NOT loaded by the server.
2. **Dedicated profile dir** — never point at `~/Library/Application Support/Google/Chrome`
   or `~/.config/google-chrome` (the default profile may be locked by the user's normal browser).
3. **Channel priority**: Beta > Canary > generic Chrome — see `browser-config.md`.
4. **`close_browser` / `force_close_all_chrome` are destructive** — only call on
   explicit user request; they affect every other agent on the same profile.
5. **Iframe context resets per tool call** — pass `iframe_selector` on every
   `click_element` / `fill_text` / `debug_element` for multi-step iframe flows.

## Directory Structure

```
src/mcp_browser_use/
  __main__.py            # FastMCP entry: registers all @mcp.tool wrappers
  constants.py           # Lock TTLs, snapshot caps, feature flags (env-driven)
  cleaners.py            # HTML cleaning + token-budgeted truncation
  context.py             # ContextPack data class
  context_pack.py        # ContextPack assembly
  helpers_context.py     # to_context_pack — render snapshot in chosen mode
  helpers.py             # Misc shared helpers
  browser/               # Chrome launch + driver attach + DevTools / process mgmt
  config/                # environment.py (env parse), paths.py (lock dirs)
  decorators/            # tool_envelope, exclusive_browser_access, ensure_driver_ready
  locking/               # action_lock, file_mutex, window_registry
  actions/               # Selenium primitives (navigation, elements, keyboard, screenshots, extraction)
  tools/                 # Higher-level tool impls called by __main__
  utils/                 # diagnostics, html_utils, retry
tests/                   # pytest (cross-platform, decorators, e2e, other)
scripts/                 # test_coverage.sh
docs/                    # logo + assorted docs
.claude/rules/           # Modular instructions for Claude Code agents
```

## Additional Documentation

| File | Content |
|------|---------|
| [README.md](README.md) | Public-facing overview, env var reference, debugging URL, lock docs |
| [SETUP_GUIDE.md](SETUP_GUIDE.md) | Per-platform `.mcp.json` templates + troubleshooting |
