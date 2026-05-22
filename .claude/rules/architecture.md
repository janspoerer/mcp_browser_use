# Architecture

## Tech Stack

- **Python 3.x** (src layout). Package: `mcp_browser_use`, installed via
  `pip install -e .` (see `pyproject.toml`).
- **MCP framework**: `mcp.server.fastmcp.FastMCP`. Stdio transport. One
  FastMCP instance per agent process — agents do NOT share state inside the
  Python process; coordination is via files on disk.
- **Browser driver**: `selenium >= 4.30`, driving Chrome over the Chrome
  DevTools Protocol on a remote-debugging port.
- **HTML processing**: `beautifulsoup4` + custom `cleaners.py` with
  cleaning levels 0-3 and token-budget aware truncation.
- **No database, no network services beyond Chrome+CDP.**
- **No async I/O outside the asyncio event loop FastMCP creates** —
  `pytest-asyncio` is intentionally NOT used (see `pyproject.toml` test extras).

## Process Model

```
agent host (Claude Code / Codex / fast-agent)
  -> spawns one Python subprocess per MCP entry  (.mcp.json `command`)
       -> subprocess runs `python -m mcp_browser_use`
            -> FastMCP instance handles stdio
                 -> each tool call goes through:
                    @tool_envelope            (error -> JSON envelope)
                    @exclusive_browser_access (cross-proc action lock + heartbeat)
                    @ensure_driver_ready      (lazy attach to Chrome + open window)
                    -> action impl from src/mcp_browser_use/tools/*.py
                    -> _to_context_pack(...) renders ContextPack JSON snapshot
```

Multiple agents each spawn their own subprocess. They share:
- one Chrome user-data-dir (so cookies/logins persist across agents)
- one Chrome process tree (after the first agent launches it)
- file locks in `tmp/mcp_locks/` keyed by SHA-256(`user_data_dir|profile_name`)

They do NOT share:
- Python process, Selenium driver, in-memory state
- browser windows — every agent owns a distinct TargetId tracked in the
  window registry

## Package Layout

| Path | Role |
|------|------|
| `src/mcp_browser_use/__main__.py` | FastMCP entry. Registers every `@mcp.tool` wrapper. ~1200 lines. |
| `src/mcp_browser_use/constants.py` | Env-driven globals: lock TTLs, snapshot caps, feature flags. No deps — safe to import anywhere. |
| `src/mcp_browser_use/config/environment.py` | Parses Chrome env vars; chooses channel (Beta > Canary > Chrome); computes `profile_key` SHA-256 used by all locks. |
| `src/mcp_browser_use/config/paths.py` | Resolves lock directory (`MCP_BROWSER_LOCK_DIR` or `<repo>/tmp/mcp_locks/`). |
| `src/mcp_browser_use/browser/chrome_executable.py` | Cross-platform Chrome binary discovery. |
| `src/mcp_browser_use/browser/chrome_launcher.py` | Builds Chrome cmdline, launches/attaches, waits for DevTools, fixed vs dynamic port. |
| `src/mcp_browser_use/browser/chrome_process.py` | Locate running Chrome by port / user-data-dir. |
| `src/mcp_browser_use/browser/chrome.py` | Higher-level start/attach orchestration. |
| `src/mcp_browser_use/browser/devtools.py` | DevToolsActivePort file parsing, port readiness checks. |
| `src/mcp_browser_use/browser/driver.py` | Selenium WebDriver attach + window/TargetId handling. |
| `src/mcp_browser_use/browser/process.py` | Process-tag rendezvous file, free-port helper. |
| `src/mcp_browser_use/decorators/envelope.py` | `tool_envelope` — catches all exceptions, returns JSON `{ok: false, ...}`. |
| `src/mcp_browser_use/decorators/locking.py` | `exclusive_browser_access` — intra-process asyncio lock + cross-process softlock + heartbeat task. Validates env early. |
| `src/mcp_browser_use/decorators/ensure.py` | `ensure_driver_ready` — attach to Chrome (or start it) before action runs. |
| `src/mcp_browser_use/locking/action_lock.py` | Softlock JSON + file mutex; renewed by heartbeat. |
| `src/mcp_browser_use/locking/file_mutex.py` | Atomic file-based mutex with stale detection. |
| `src/mcp_browser_use/locking/window_registry.py` | Per-profile registry of (targetId, windowId, PID, heartbeat); used for orphan cleanup. |
| `src/mcp_browser_use/actions/*.py` | Selenium primitives: navigation, elements, keyboard, screenshots, extraction. |
| `src/mcp_browser_use/tools/*.py` | Tool implementations called from `__main__.py`. |
| `src/mcp_browser_use/cleaners.py` | HTML cleaning levels 0-3, token-budget truncation, outline/text/dompaths render. |
| `src/mcp_browser_use/context.py` + `context_pack.py` | ContextPack data model. |
| `src/mcp_browser_use/helpers_context.py` | `to_context_pack` — turns a tool result + return_mode/cleaning/budget into the JSON envelope returned to the agent. |
| `src/mcp_browser_use/utils/*.py` | Diagnostics, retry, html_utils. |

## Decorator Stack on Every Mutating Tool

```python
@mcp.tool()
@tool_envelope
@exclusive_browser_access   # cross-proc action lock + heartbeat
@ensure_driver_ready        # attach Selenium, open window if needed
async def mcp_browser_use__<name>(...):
    result = await tools.<impl>(...)
    return await _to_context_pack(result_json=result, return_mode=..., cleaning_level=..., token_budget=...)
```

Non-mutating tools (`get_debug_diagnostics_info`, `unlock_browser`,
`force_close_all_chrome`) skip `ensure_driver_ready` and sometimes
`exclusive_browser_access`.

## ContextPack Return Modes

Every tool returns a JSON `ContextPack`. The agent picks the representation:

| `return_mode` | Use case |
|---------------|----------|
| `outline` | Just headings / landmark structure (default; cheapest). |
| `text` | Extracted readable text. Pair with `text_offset` for pagination. |
| `html` | Cleaned HTML. Pair with `html_offset` for pagination. |
| `dompaths` | Path-style element locators. |
| `mixed` | Combination — also carries auxiliary fields like `diagnostics`, `extraction`. |

`cleaning_level` 0 = none, 3 = aggressive (drops scripts/styles/ads).
`token_budget` truncates the final string; check `hard_capped` to detect
truncation and paginate with the `*_offset` knobs.
