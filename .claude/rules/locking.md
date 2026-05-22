# Locking & Coordination

Multiple agent processes share one Chrome user-data-dir. They cooperate via
files in `tmp/mcp_locks/` (or `MCP_BROWSER_LOCK_DIR` if set). All filenames are
prefixed with the profile hash (see `browser-config.md` → "Profile Key") so
distinct profiles get distinct lock universes.

## Lock Types

| Type | File pattern | Purpose |
|------|--------------|---------|
| Action lock | `<hash>.softlock.json` + `<hash>.softlock.mutex` | Serialize browser actions across processes. Owner heartbeats every ~1s while `exclusive_browser_access` is active. |
| Window registry | `<hash>.window_registry.json` | Map of `targetId -> {windowId, pid, last_heartbeat}`. Used for orphan cleanup of windows from dead/stale agents. |
| Startup mutex | `<hash>.startup.mutex` | Held briefly during initial Chrome launch so two agents don't both try to spawn Chrome. |

The softlock + window registry are updated together: every action-lock renewal
also bumps the owning agent's window heartbeat (piggyback optimization in
`action_lock._renew_action_lock`).

## Action Lock Lifecycle

In `decorators/locking.py:exclusive_browser_access`:

1. Validate env (`_validate_config_or_error`). Bad env → return JSON error, no lock taken.
2. Resolve owner from `browser/process.ensure_process_tag()` (per-process tag).
3. Acquire intra-process `asyncio.Lock()` (serializes concurrent tool calls
   within ONE Python process — rare but possible).
4. Acquire cross-process softlock via `_acquire_action_lock_or_error(owner)`:
   waits up to `ACTION_LOCK_WAIT_SECS`. On timeout returns the `locked` envelope.
5. Spawn an asyncio heartbeat task: every 1s it calls `_renew_action_lock(owner, ttl)`.
6. Run the wrapped tool body.
7. On exit: stop the heartbeat, then `_renew_action_lock` one last time (so a
   pending follow-up call from the same owner doesn't time out).

The softlock is "soft" — TTL-based, no kernel mutex. If a holder dies, the next
acquirer sees `expires_at <= now()` and steals the lock.

## Lock-Related Env Vars

| Variable | Default | Effect |
|----------|---------|--------|
| `MCP_ACTION_LOCK_TTL` | `30` (s) | Renewed each heartbeat. If a holder dies, others can grab the lock after at most this many seconds. |
| `MCP_ACTION_LOCK_WAIT` | `60` (s) | Max time a tool call waits to acquire the lock before returning `locked` error. |
| `MCP_FILE_MUTEX_STALE_SECS` | `60` (s) | Stale-threshold for the file mutex protecting softlock JSON writes. |
| `MCP_WINDOW_REGISTRY_STALE_SECS` | `300` (s) | A window registry entry not heartbeated within this many seconds is considered orphaned. |
| `MCP_BROWSER_LOCK_DIR` | `<repo>/tmp/mcp_locks/` | Override the lock directory (e.g. point at a tmpfs). |

Defined in `constants.py`.

## Orphan Window Cleanup

When `ensure_driver_ready` attaches/starts a session it scans
`<hash>.window_registry.json` and:

1. Drops entries whose `pid` no longer exists (`psutil`-based check).
2. Drops entries with no heartbeat in `WINDOW_REGISTRY_STALE_THRESHOLD` seconds.
3. Closes the matching browser windows via CDP `Target.closeTarget`.
4. Persists the trimmed registry.

This keeps zombie windows from crashed agents from piling up.

## Recovery Tools

| Symptom | Tool / Action |
|---------|---------------|
| One agent stuck holding the action lock | `mcp_browser_use__unlock_browser` releases this process's owner record. |
| Lock files corrupted / Chrome unresponsive | `mcp_browser_use__force_close_all_chrome` — kills every Chrome under the profile, wipes lock files. **Affects every other agent on the same profile.** |
| `locked` returned but no owner alive | TTL will expire on its own; manual fix: delete `<hash>.softlock.json` in the lock dir. |
| Want to inspect state | The lock dir is human-readable JSON; `cat tmp/mcp_locks/<hash>.softlock.json`. |

## Rendezvous File

`browser/process.write_rendezvous(config, port, pid)` records the current
Chrome's port + PID so subsequent MCP processes for the same profile can attach
without rediscovering. Stored under the lock directory. TTL =
`RENDEZVOUS_TTL_SEC` (24h).
