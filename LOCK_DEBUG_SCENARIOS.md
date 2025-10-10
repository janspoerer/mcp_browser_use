# Rubber Duck Debug Scenarios for Lock Testing

This document contains test scenarios to verify the locking mechanism, window registry, and orphan cleanup functionality in `mcp_browser_use`.

## Lock File Locations

All lock files should be in: `/Users/janspoerer/code/agents/mcp_browser_use/tmp/mcp_locks/`

Expected files:
- `<hash>.softlock.json` - Action lock state (owner, expires_at)
- `<hash>.softlock.mutex` - File mutex for action lock
- `<hash>.startup.mutex` - Startup coordination mutex
- `<hash>.window_registry.json` - Window ownership registry

## Scenario 1: Single Agent Basic Flow

**Purpose:** Verify basic lock acquisition, window registration, and cleanup.

**Steps:**
1. Start browser using `start_browser`
2. Check lock files - should see:
   - Action lock acquired (softlock.json has owner and expires_at)
   - Window registry has one entry with this agent's PID
3. Navigate to a URL (e.g., example.com)
4. Check lock files - should see:
   - Action lock renewed (expires_at updated)
   - Window registry heartbeat updated
5. Close browser using `close_browser`
6. Check lock files - should see:
   - Action lock released (softlock.json should be empty or removed)
   - Window registry entry removed

**Expected Lock File States:**

After `start_browser`:
```json
# softlock.json
{
  "owner": "agent:<pid>:<timestamp>:<random>",
  "expires_at": <timestamp + 30 seconds>
}

# window_registry.json
{
  "agent:<pid>:<timestamp>:<random>": {
    "target_id": "...",
    "window_id": ...,
    "pid": <current_pid>,
    "last_heartbeat": <timestamp>,
    "created_at": <timestamp>
  }
}
```

After `close_browser`:
```json
# softlock.json
{}

# window_registry.json
{}
```

---

## Scenario 2: Lock Renewal During Long Operation

**Purpose:** Verify that action lock is renewed and window heartbeat is updated during operations.

**Steps:**
1. Start browser
2. Navigate to example.com
3. Note the initial `expires_at` timestamp from softlock.json
4. Wait 5 seconds
5. Perform another action (e.g., take_screenshot)
6. Check softlock.json - `expires_at` should be updated (30 seconds from now)
7. Check window_registry.json - `last_heartbeat` should be updated

**What to verify:**
- Action lock doesn't expire during continuous use
- Window heartbeat is piggybacked on lock renewal
- Lock TTL is consistently ~30 seconds in the future

---

## Scenario 3: Window Registry Persistence

**Purpose:** Verify window registry survives across multiple operations.

**Steps:**
1. Start browser
2. Record the agent ID from window_registry.json
3. Navigate to example.com
4. Take screenshot
5. Scroll the page
6. Fill text in a field
7. After each operation, verify:
   - Same agent ID still in registry
   - `last_heartbeat` is updated
   - `target_id` and `window_id` remain the same

**What to verify:**
- Window registry entry persists throughout session
- Heartbeat updates with each action
- No duplicate entries created

---

## Scenario 4: Orphan Window Cleanup (Simulated)

**Purpose:** Verify that orphaned windows from dead processes are detected and cleaned up.

**Steps:**
1. Start browser (Agent 1)
2. Note the window_registry.json entry
3. Manually edit window_registry.json to add a fake stale entry:
   ```json
   {
     "agent:<real_agent_id>": { ... actual entry ... },
     "agent:99999:1234567890:fake": {
       "target_id": "fake_target",
       "window_id": 123,
       "pid": 99999,
       "last_heartbeat": 1000000000,
       "created_at": 1000000000
     }
   }
   ```
4. Close browser (to release lock)
5. Start browser again (Agent 2 or same agent restarted)
6. Check window_registry.json immediately after start
7. The fake entry should be removed (PID 99999 doesn't exist)

**What to verify:**
- Cleanup function detects non-existent PID
- Fake entry is removed from registry
- Real agent's window is not affected
- No errors logged about failed cleanup

---

## Scenario 5: Stale Heartbeat Cleanup

**Purpose:** Verify that entries with stale heartbeats (>5 minutes) are cleaned up.

**Steps:**
1. Start browser
2. Manually edit window_registry.json to make `last_heartbeat` very old:
   ```json
   {
     "agent:<real_agent>": {
       "target_id": "...",
       "window_id": ...,
       "pid": <current_pid>,
       "last_heartbeat": 1000000000,  // Very old timestamp
       "created_at": 1000000000
     }
   }
   ```
3. Close browser
4. Start browser again
5. The old entry should be detected as stale and cleaned up

**What to verify:**
- Stale threshold (5 minutes) is enforced
- Old entries are cleaned even if PID still exists
- New window is created successfully

---

## Scenario 6: Lock File Path Verification

**Purpose:** Verify lock files are in the correct location (project root tmp/).

**Steps:**
1. Start browser
2. Check that lock files exist in:
   `/Users/janspoerer/code/agents/mcp_browser_use/tmp/mcp_locks/`
3. Verify NO lock files exist in:
   - `/tmp/`
   - System temporary directory
   - User home directory
4. Verify `tmp/` is in `.gitignore`

**What to verify:**
- All lock files use project-local tmp/ directory
- Hash-based filenames are consistent across files
- Directory is created automatically if it doesn't exist

---

## Scenario 7: Atomic File Operations

**Purpose:** Verify that file writes are atomic and don't corrupt during concurrent access.

**Steps:**
1. Start browser
2. While browser is running, manually inspect lock files
3. Files should always contain valid JSON
4. No partial writes or corruption
5. Check for `.tmp` files in lock directory (should be cleaned up immediately)

**What to verify:**
- No corrupted JSON files
- No leftover temporary files
- Files are always in consistent state

---

## Scenario 8: Multiple Sequential Browser Sessions

**Purpose:** Verify clean state transitions between sessions.

**Steps:**
1. Start browser (Session 1)
2. Navigate to example.com
3. Close browser
4. Verify locks are released and registry is clean
5. Start browser again (Session 2)
6. Verify new locks are acquired
7. Verify new window registry entry with different agent ID
8. Close browser
9. Verify clean state again

**What to verify:**
- Each session gets a unique agent ID
- Previous session's locks don't interfere
- Window registry is properly cleaned between sessions
- No lock contention or deadlocks

---

## Scenario 9: Lock Expiry and Staleness

**Purpose:** Verify that stale locks can be reclaimed.

**Steps:**
1. Start browser
2. Note the `expires_at` timestamp in softlock.json
3. Manually edit softlock.json to set `expires_at` to a past timestamp
4. Close browser (simulate crash without cleanup)
5. Start browser again
6. Should acquire lock successfully (old lock was stale)

**What to verify:**
- Stale locks (expired) can be reclaimed
- No errors when reclaiming stale lock
- New expiry is set correctly

---

## Scenario 10: Environment Variable Configuration

**Purpose:** Verify that environment variables control lock behavior.

**Steps:**
1. Check current lock behavior (defaults)
2. Set custom environment variables:
   ```bash
   MCP_ACTION_LOCK_TTL=60
   MCP_WINDOW_REGISTRY_STALE_SECS=120
   ```
3. Start browser
4. Verify softlock.json has `expires_at` = now + 60 seconds
5. Verify stale threshold is honored

**What to verify:**
- Environment variables are respected
- Lock TTL uses custom value
- Stale thresholds use custom values
- Defaults work when env vars not set

---

## Debug Commands

### View all lock files:
```bash
ls -lah /Users/janspoerer/code/agents/mcp_browser_use/tmp/mcp_locks/
```

### Read action lock state:
```bash
cat /Users/janspoerer/code/agents/mcp_browser_use/tmp/mcp_locks/*.softlock.json | jq .
```

### Read window registry:
```bash
cat /Users/janspoerer/code/agents/mcp_browser_use/tmp/mcp_locks/*.window_registry.json | jq .
```

### Monitor lock files in real-time:
```bash
watch -n 1 'ls -lh /Users/janspoerer/code/agents/mcp_browser_use/tmp/mcp_locks/ && echo "---" && cat /Users/janspoerer/code/agents/mcp_browser_use/tmp/mcp_locks/*.json 2>/dev/null | jq .'
```

### Get current PID:
```bash
echo $$
```

### Check if PID exists:
```bash
ps -p <PID>
```

### View timestamps in human-readable format:
```bash
date -r <timestamp>
```

---

## Expected Outcomes Summary

| Scenario | Key Verification Points |
|----------|------------------------|
| 1. Basic Flow | Lock acquired → renewed → released; Registry created → updated → removed |
| 2. Lock Renewal | Lock TTL stays ~30s ahead; heartbeat updates |
| 3. Registry Persistence | Same entry throughout session; heartbeat updates |
| 4. Orphan Cleanup | Non-existent PIDs removed from registry |
| 5. Stale Heartbeat | Old heartbeats (>5min) trigger cleanup |
| 6. Path Verification | All files in project tmp/, not system tmp/ |
| 7. Atomic Operations | No corrupted JSON; no leftover .tmp files |
| 8. Sequential Sessions | Clean transitions; unique agent IDs |
| 9. Lock Expiry | Stale locks can be reclaimed |
| 10. Environment Config | Custom values respected |

---

## Notes for Testing

- **Timestamps:** All timestamps in lock files are Unix epoch seconds (float)
- **Agent ID Format:** `agent:<pid>:<timestamp>:<random_hex>`
- **Hash Format:** SHA-256 hash of profile path + profile name
- **TTL Default:** 30 seconds for action lock
- **Stale Default:** 300 seconds (5 minutes) for window registry
- **Watch for:** Race conditions, deadlocks, orphaned resources, corrupted files
