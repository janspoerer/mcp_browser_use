# Browser Configuration

All env vars are read by `src/mcp_browser_use/config/environment.py` at process
start. They MUST be defined in the agent host's `.mcp.json` `env` block — the
MCP subprocess only inherits explicitly passed env. `.env` files are NOT loaded
at server startup.

## Channel Priority

`environment.get_env_config()` picks Chrome in this order (later overrides earlier):

1. Generic Chrome — `CHROME_EXECUTABLE_PATH` + `CHROME_PROFILE_USER_DATA_DIR` + `CHROME_PROFILE_NAME`
2. Canary — `CANARY_EXECUTABLE_PATH` + `CANARY_PROFILE_USER_DATA_DIR` + `CANARY_PROFILE_NAME`
3. Beta — `BETA_EXECUTABLE_PATH` + `BETA_PROFILE_USER_DATA_DIR` + `BETA_PROFILE_NAME` **(preferred — overrides both above)**

At least one user-data-dir of the three MUST be set or every tool call fails with
`invalid_configuration`. The setter of an `EXECUTABLE_PATH` also requires the
matching `USER_DATA_DIR`.

## Env Var Reference

| Variable | Default | Notes |
|----------|---------|-------|
| `CHROME_PROFILE_USER_DATA_DIR` | — | Generic Chrome profile dir. Required if no Beta/Canary set. |
| `CHROME_PROFILE_NAME` | `Default` | Profile subdirectory name. |
| `CHROME_EXECUTABLE_PATH` | autodetect | Override Chrome binary path. |
| `BETA_EXECUTABLE_PATH` | — | Path to Chrome Beta. **If set, takes priority.** |
| `BETA_PROFILE_USER_DATA_DIR` | — | Required if `BETA_EXECUTABLE_PATH` set. |
| `BETA_PROFILE_NAME` | `Default` | — |
| `CANARY_EXECUTABLE_PATH` | — | Path to Chrome Canary. Higher prio than generic, lower than Beta. |
| `CANARY_PROFILE_USER_DATA_DIR` | — | Required if `CANARY_EXECUTABLE_PATH` set. |
| `CANARY_PROFILE_NAME` | `Default` | — |
| `CHROME_REMOTE_DEBUG_PORT` | dynamic | Fixed CDP port. Omit → MCP picks free port. |
| `CHROME_PROFILE_STRICT` | `0` | `1` = hard-fail if profile dir does not exist (no auto-create). |
| `MCP_HEADLESS` | `0` | `1` = pass `--headless=new`. Needed on display-less Linux. |
| `MCP_NO_SANDBOX` | `0` | `1` = pass `--no-sandbox`. **Required on WSL2 / Docker.** |
| `MCP_ENABLE_EXTENSIONS` | `0` | `1` = load every extension under `~/MCPExtensions/` (Linux/macOS) or `%USERPROFILE%\MCPExtensions\` (Windows). |
| `MCP_MAX_SNAPSHOT_CHARS` | `10000` | Cap for HTML snapshots. |
| `MCP_ATTACH_ANY_PROFILE` | `0` | `1` = attach to any Chrome regardless of configured profile (advanced). |
| `MCP_BROWSER_LOCK_DIR` | `<repo>/tmp/mcp_locks/` | Override lock directory. |

Lock-related env vars are listed in `locking.md`.

## Chrome Cmdline (always passed)

From `browser/chrome_launcher.py:build_chrome_command`:

```
--remote-debugging-port=<port>
--user-data-dir=<user_data_dir>
--profile-directory=<profile_name>
--no-first-run
--no-default-browser-check
--new-window
--disable-features=ProcessPerSite
--disable-gpu
--disable-dev-shm-usage
--disable-software-rasterizer
about:blank
```

Conditional flags:
- `--headless=new` if `MCP_HEADLESS=1`
- `--no-sandbox` if `MCP_NO_SANDBOX=1`
- `--load-extension=<dir1>,<dir2>,…` if `MCP_ENABLE_EXTENSIONS=1` and one or
  more valid extension dirs (must contain `manifest.json`) exist under
  `~/MCPExtensions/`

Extension debug log: `<tempdir>/mcp_browser_logs/extension_loading_debug.log`.
Chrome stderr/stdout log: `<tempdir>/mcp_browser_logs/chrome_debug_<port>.log`.

## Why Beta/Canary?

The DevTools debugger refuses to start on a Chrome instance that's already running
without remote-debugging. If you point at your everyday Chrome user-data-dir
while a normal Chrome is open on it, Chrome will spawn but the debug endpoint
will never bind. Beta/Canary live in separate user-data-dirs so the MCP and your
daily browser coexist.

Equivalent escape hatch: use a dedicated `user_data_dir` like `/tmp/mcp-chrome-profile`
on Linux or `C:\\Users\\<you>\\ChromeBetaMCP` on Windows.

## Profile Key

Locks are keyed by `SHA-256("<resolved user_data_dir>|<profile_name>")` —
computed by `config.environment.profile_key()`. Same key across processes → they
contend for the same locks. Different profile_dir or profile_name → independent
lock universes.

## Default-Profile Detection

`environment.is_default_user_data_dir(path)` recognises platform-default Chrome
profile paths (e.g. `~/Library/Application Support/Google/Chrome` on macOS).
The launcher uses this to be more conservative when killing Chrome — it will
NOT mass-kill processes if the profile is a default channel directory.

## Debugging

If Chrome is running with debugging, you can verify externally:

```
http://127.0.0.1:<CHROME_REMOTE_DEBUG_PORT>/json/version
```

Returns JSON with `Browser`, `Protocol-Version`, `webSocketDebuggerUrl`.
