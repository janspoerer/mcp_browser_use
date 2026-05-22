# MCP Tools

All tools live in `src/mcp_browser_use/__main__.py`, prefixed `mcp_browser_use__`.
Every tool returns a JSON `ContextPack` (see `architecture.md`).

Common kwargs on most tools:
- `return_mode` (`outline` | `text` | `html` | `dompaths` | `mixed`)
- `cleaning_level` (0-3)
- `token_budget` (int, default 5000)
- `text_offset` / `html_offset` (pagination through cleaned content)

## Tool Catalogue

| Tool | Decorators | Purpose |
|------|-----------|---------|
| `start_browser` | envelope + exclusive | Start Chrome if not running, else open a new window for this agent. Idempotent per agent process. |
| `navigate_to_url` | envelope + exclusive + ensure | Go to `url`, wait for `load`/`complete`, return snapshot. Supports inline extraction (see below). |
| `fill_text` | envelope + exclusive + ensure | Type into a field. Iframe + shadow-root selectors supported (must be repeated per call). |
| `click_element` | envelope + exclusive + ensure | Click. `force_js=True` falls back to JS click. Iframe/shadow-root aware. |
| `take_screenshot` | envelope + exclusive + ensure | PNG to disk + optional base64 thumbnail + optional snapshot. `thumbnail_width` default 200px to stay under the 25K-token MCP image cap. |
| `get_debug_diagnostics_info` | envelope only | Driver session, user-agent, window size, profile path, browser/driver/Selenium versions. Does NOT need driver. |
| `debug_element` | envelope + exclusive + ensure | Diagnose why an element is not clickable/visible (visibility, overlay, iframe scope). |
| `unlock_browser` | envelope + exclusive | Release the action lock owned by this process. Recovery if a previous call wedged the lock. |
| `close_browser` | envelope + exclusive | Quit this agent's Selenium driver + window. **Destructive — explicit user request only.** |
| `force_close_all_chrome` | envelope only | Kill every Chrome process under the configured profile, wipe locks, reset state. **Affects all other agents on this profile. Use only when truly stuck.** |
| `scroll` | envelope + exclusive + ensure | Scroll viewport by `x`,`y` pixels. Supports inline extraction (infinite-scroll pattern). |
| `send_keys` | envelope + exclusive + ensure | Send special keys (`ENTER`, `TAB`, `ESCAPE`, …) optionally to a focused selector. |
| `wait_for_element` | envelope + exclusive + ensure | Block until selector is `present` / `visible` / `clickable` (default 10s). |
| `extract_elements` | envelope + exclusive + ensure | Two modes — simple (`selectors=[…]`) for ad-hoc fields, or structured (`container_selector` + `fields=[…]`) for list/table scraping. Iframe + shadow DOM supported. With no args, acts as "get current page state". |

## Inline Extraction on Navigation Tools

`navigate_to_url`, `scroll` (and some other navigation tools) accept the same
extraction params as `extract_elements` with an `extract_` prefix:

```
extract_selectors:      list  - MODE 1 simple extraction
extract_container:      str   - MODE 2 container selector
extract_fields:         list  - MODE 2 field extractors
extract_selector_type:  str   - "css" | "xpath" (auto-detected if omitted)
extract_wait_visible:   bool
extract_timeout:        int
extract_max_items:      int
extract_discover:       bool
```

When set, the wrapper performs the extraction immediately after the action and
merges the result into the returned ContextPack under `extraction`. Saves a round-trip
versus calling `extract_elements` separately.

## Output Envelope

`tool_envelope` ensures every tool returns valid JSON even on failure:

```json
{ "ok": false, "error": "<class>", "message": "...", "details": { ... } }
```

`exclusive_browser_access` validates env early. If `CHROME_PROFILE_USER_DATA_DIR`
(or Beta/Canary equivalent) is missing, every call short-circuits with:

```json
{ "ok": false, "error": "invalid_configuration",
  "message": "...",
  "details": { "required": [...], "optional": [...] } }
```

When another agent holds the action lock past the wait timeout
(`MCP_ACTION_LOCK_WAIT`, default 60s):

```json
{ "ok": false, "error": "locked", "owner": "<other_owner>",
  "expires_at": <ts>, "lock_ttl_seconds": <ttl> }
```

## Iframe / Shadow DOM Gotcha

Browser context is reset between tool calls for reliability. For any multi-step
flow inside an iframe or shadow root, repeat the `iframe_selector` /
`shadow_root_selector` on EVERY call (`click_element`, `fill_text`,
`debug_element`, etc.). The MCP will NOT remember where you were.
