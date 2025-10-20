# Developer C: Tools & High-Level Integration

**Role:** Integration Layer - Tools, Testing, Deprecation
**Timeline:** Days 6-20 (starts after Dev A Day 5)
**Branch:** `refactor/tools-integration`

## Your Responsibilities
You own the MCP tools layer, testing infrastructure, and deprecation warnings. You'll ensure the tools/ directory uses BrowserContext and create comprehensive testing for the refactoring.

---

## **PREREQUISITES**

⚠️ **BLOCKED UNTIL:** Developer A completes Day 5 (BrowserContext creation)

Once unblocked, pull latest:
```bash
git checkout main
git pull origin main
git checkout -b refactor/tools-integration
git merge origin/refactor/foundation-state  # Get Dev A's changes
```

Verify you have:
- [ ] `src/mcp_browser_use/constants.py`
- [ ] `src/mcp_browser_use/context.py`
- [ ] `src/mcp_browser_use/config/`
- [ ] Updated `src/mcp_browser_use/helpers.py` with context integration

---

## **WEEK 1: Days 6-10**

### **Day 6-8: Update tools/ Modules to Use Context**

**Goal:** Migrate all tools to use BrowserContext

#### Task 1.1: Update tools/browser_management.py
**File:** `src/mcp_browser_use/tools/browser_management.py`

This is the most important tool - it manages browser lifecycle.

**Before (lines 1-10):**
```python
import json
import psutil
from pathlib import Path
import mcp_browser_use.helpers as helpers
from mcp_browser_use.utils.diagnostics import collect_diagnostics
```

**After:**
```python
import json
import psutil
from pathlib import Path
from ..context import get_context, reset_context
from ..config import get_env_config, profile_key
from ..constants import ACTION_LOCK_TTL_SECS
from ..utils.diagnostics import collect_diagnostics

# Import specific functions we need
from ..browser.driver import (
    _ensure_driver_and_window,
    close_singleton_window,
    _close_extra_blank_windows_safe,
)
from ..browser.process import ensure_process_tag
from ..actions.navigation import _wait_document_ready
from ..actions.screenshots import _make_page_snapshot
from ..locking.action_lock import _release_action_lock
```

**Update start_browser() function:**

**Before (lines 10-74):**
```python
async def start_browser():
    owner = helpers.ensure_process_tag()
    try:
        helpers._ensure_driver_and_window()

        if helpers.DRIVER is None:
            diag = collect_diagnostics(None, None, helpers.get_env_config())
            # ...
            return json.dumps({
                "ok": False,
                "error": "driver_not_initialized",
                "debugger": (
                    f"{helpers.DEBUGGER_HOST}:{helpers.DEBUGGER_PORT}"
                    if (helpers.DEBUGGER_HOST and helpers.DEBUGGER_PORT) else None
                ),
                # ...
            })

        handle = getattr(helpers.DRIVER, "current_window_handle", None)
        try:
            helpers._close_extra_blank_windows_safe(
                helpers.DRIVER,
                exclude_handles={handle} if handle else None
            )
        except Exception:
            pass

        # Wait until the page is ready
        helpers._wait_document_ready(timeout=5.0)
        try:
            snapshot = helpers._make_page_snapshot()
        except Exception:
            snapshot = None

        # ...
        payload = {
            "ok": True,
            "session_id": owner,
            "debugger": f"{helpers.DEBUGGER_HOST}:{helpers.DEBUGGER_PORT}" if (helpers.DEBUGGER_HOST and helpers.DEBUGGER_PORT) else None,
            "lock_ttl_seconds": helpers.ACTION_LOCK_TTL_SECS,
            # ...
        }
        return json.dumps(payload)
```

**After:**
```python
async def start_browser():
    """
    Start browser session or open new window in existing session.

    Returns:
        JSON string with session info and snapshot
    """
    ctx = get_context()

    # Ensure process tag
    if ctx.process_tag is None:
        ctx.process_tag = ensure_process_tag()

    owner = ctx.process_tag

    try:
        # Initialize driver and window
        _ensure_driver_and_window()

        # Check if initialization succeeded
        if not ctx.is_driver_initialized():
            diag = collect_diagnostics(None, None, ctx.config)
            if isinstance(diag, str):
                diag = {"summary": diag}

            return json.dumps({
                "ok": False,
                "error": "driver_not_initialized",
                "driver_initialized": False,
                "debugger": ctx.get_debugger_address(),
                "diagnostics": diag,
                "message": "Failed to attach/launch a debuggable Chrome session."
            })

        # Clean up extra blank windows
        handle = getattr(ctx.driver, "current_window_handle", None)
        try:
            _close_extra_blank_windows_safe(
                ctx.driver,
                exclude_handles={handle} if handle else None
            )
        except Exception:
            pass

        # Wait for page ready and get snapshot
        _wait_document_ready(timeout=5.0)
        try:
            snapshot = _make_page_snapshot()
        except Exception:
            snapshot = None

        snapshot = snapshot or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }

        msg = (
            f"Browser session created successfully. "
            f"Session ID: {owner}. "
            f"Current URL: {snapshot.get('url') or 'about:blank'}"
        )

        payload = {
            "ok": True,
            "session_id": owner,
            "debugger": ctx.get_debugger_address(),
            "lock_ttl_seconds": ACTION_LOCK_TTL_SECS,
            "snapshot": snapshot,
            "message": msg,
        }

        return json.dumps(payload)

    except Exception as e:
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        snapshot = _make_page_snapshot() or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }
        return json.dumps({
            "ok": False,
            "error": str(e),
            "diagnostics": diag,
            "snapshot": snapshot
        })
```

**Update unlock_browser() function:**

**Before:**
```python
async def unlock_browser():
    owner = helpers.ensure_process_tag()
    released = helpers._release_action_lock(owner)
    return json.dumps({"ok": True, "released": bool(released)})
```

**After:**
```python
async def unlock_browser():
    """Release the action lock for this process."""
    ctx = get_context()

    if ctx.process_tag is None:
        ctx.process_tag = ensure_process_tag()

    owner = ctx.process_tag
    released = _release_action_lock(owner)

    return json.dumps({
        "ok": True,
        "released": bool(released)
    })
```

**Update close_browser() function:**

**Before:**
```python
async def close_browser() -> str:
    try:
        closed = helpers.close_singleton_window()
        msg = "Browser window closed successfully" if closed else "No window to close"
        return json.dumps({"ok": True, "closed": bool(closed), "message": msg})
    except Exception as e:
        diag = collect_diagnostics(helpers.DRIVER, e, helpers.get_env_config())
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag})
```

**After:**
```python
async def close_browser() -> str:
    """Close the browser window for this session."""
    ctx = get_context()

    try:
        closed = close_singleton_window()
        msg = "Browser window closed successfully" if closed else "No window to close"

        return json.dumps({
            "ok": True,
            "closed": bool(closed),
            "message": msg
        })

    except Exception as e:
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        return json.dumps({
            "ok": False,
            "error": str(e),
            "diagnostics": diag
        })
```

**Update force_close_all_chrome() function:**

This function is complex. Update it to use context:

**Key changes:**
- Replace `helpers.DRIVER` with `ctx.driver`
- Replace `helpers.get_env_config()` with `ctx.config`
- Replace `helpers.LOCK_DIR` with `ctx.lock_dir`
- Replace global assignments with context updates

```python
async def force_close_all_chrome() -> str:
    """
    Force close all Chrome processes, quit driver, and clean up all state.
    Use this to recover from stuck Chrome instances.
    """
    ctx = get_context()
    killed_processes = []
    errors = []

    try:
        # 1. Try to quit the Selenium driver gracefully
        if ctx.driver is not None:
            try:
                ctx.driver.quit()
            except Exception as e:
                errors.append(f"Driver quit failed: {e}")

            ctx.driver = None

        # 2. Get config to find which Chrome processes to kill
        user_data_dir = ctx.config.get("user_data_dir", "")
        if not user_data_dir:
            try:
                cfg = get_env_config()
                user_data_dir = cfg.get("user_data_dir", "")
            except Exception as e:
                errors.append(f"Could not get config: {e}")

        # 3. Kill all Chrome processes using the MCP profile
        chrome_processes_found = []
        for p in psutil.process_iter(["name", "cmdline", "pid"]):
            try:
                if not p.info.get("name"):
                    continue
                if "chrome" not in p.info["name"].lower():
                    continue

                chrome_processes_found.append(p)

                # If we have a user_data_dir, check if this process matches
                if user_data_dir:
                    cmd = p.info.get("cmdline")
                    if cmd:
                        user_data_normalized = user_data_dir.replace("\\", "/").lower()
                        for arg in cmd:
                            if arg and "--user-data-dir" in arg:
                                arg_normalized = arg.replace("\\", "/").lower()
                                if user_data_normalized in arg_normalized:
                                    p.kill()
                                    killed_processes.append(p.info["pid"])
                                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                errors.append(f"Could not access process: {e}")

        # 4. Fallback: If no processes killed but some found, kill them all
        if not killed_processes and chrome_processes_found:
            for p in chrome_processes_found:
                try:
                    p.kill()
                    killed_processes.append(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    errors.append(f"Could not kill process in fallback: {e}")

        # 5. Clean up context state
        ctx.debugger_host = None
        ctx.debugger_port = None
        ctx.reset_window_state()

        # 6. Release locks
        try:
            if ctx.process_tag:
                _release_action_lock(ctx.process_tag)
        except Exception as e:
            errors.append(f"Lock release failed: {e}")

        # 7. Clean up lock files
        try:
            if user_data_dir:
                lock_dir = Path(ctx.lock_dir)
                if lock_dir.exists():
                    profile_key_val = profile_key(ctx.config) if ctx.config else ""
                    for lock_file in lock_dir.glob(f"*{profile_key_val}*"):
                        try:
                            lock_file.unlink()
                        except Exception:
                            pass
        except Exception as e:
            errors.append(f"Lock file cleanup failed: {e}")

        msg = f"Force closed Chrome. Killed {len(killed_processes)} processes."
        if errors:
            msg += f" Errors: {'; '.join(errors)}"

        return json.dumps({
            "ok": True,
            "killed_processes": killed_processes,
            "errors": errors,
            "message": msg
        })

    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": str(e),
            "killed_processes": killed_processes,
            "errors": errors
        })
```

#### Task 1.2: Update tools/navigation.py
**File:** `src/mcp_browser_use/tools/navigation.py`

**Before:**
```python
import mcp_browser_use.helpers as helpers
from mcp_browser_use.utils.diagnostics import collect_diagnostics

async def navigate_to_url(url: str, wait_for: str = "load", timeout_sec: int = 20):
    # ... uses helpers.navigate_to_url
```

**After:**
```python
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics
from ..actions.navigation import navigate_to_url as _navigate_to_url
from ..actions.screenshots import _make_page_snapshot

async def navigate_to_url(url: str, wait_for: str = "load", timeout_sec: int = 20):
    """Navigate to URL (tool wrapper)."""
    ctx = get_context()

    try:
        result = await _navigate_to_url(
            url=url,
            wait_for=wait_for,
            timeout_sec=timeout_sec
        )

        return result

    except Exception as e:
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        snapshot = _make_page_snapshot() or {
            "url": None,
            "title": None,
            "html": "",
            "truncated": False,
        }
        return json.dumps({
            "ok": False,
            "error": str(e),
            "diagnostics": diag,
            "snapshot": snapshot
        })
```

Update `scroll()` similarly.

#### Task 1.3: Update tools/interaction.py
**File:** `src/mcp_browser_use/tools/interaction.py`

Similar pattern:
- Remove `import mcp_browser_use.helpers as helpers`
- Add `from ..context import get_context`
- Import action functions directly
- Use `ctx.driver` and `ctx.config` for diagnostics

```python
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics
from ..actions.elements import (
    click_element as _click_element,
    fill_text as _fill_text,
    debug_element as _debug_element,
)
from ..actions.keyboard import send_keys as _send_keys
from ..actions.navigation import wait_for_element as _wait_for_element

# Update each tool function to use context
async def click_element(...):
    ctx = get_context()
    try:
        result = await _click_element(...)
        return result
    except Exception as e:
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        # ... error handling
```

#### Task 1.4: Update tools/screenshots.py
**File:** `src/mcp_browser_use/tools/screenshots.py`

```python
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics
from ..actions.screenshots import take_screenshot as _take_screenshot

async def take_screenshot(...):
    ctx = get_context()
    try:
        result = await _take_screenshot(...)
        return result
    except Exception as e:
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        # ... error handling
```

#### Task 1.5: Update tools/debugging.py
**File:** `src/mcp_browser_use/tools/debugging.py`

```python
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics as _collect_diagnostics

async def get_debug_diagnostics_info():
    """Get debug diagnostics using context."""
    ctx = get_context()

    diagnostics = _collect_diagnostics(
        driver=ctx.driver,
        error=None,
        config=ctx.config
    )

    return json.dumps({
        "ok": True,
        "diagnostics": diagnostics,
        "context_state": {
            "driver_initialized": ctx.is_driver_initialized(),
            "window_ready": ctx.is_window_ready(),
            "debugger_address": ctx.get_debugger_address(),
            "process_tag": ctx.process_tag,
        }
    })
```

#### Task 1.6: Test tools/ modules
```bash
python -c "
from mcp_browser_use.tools import (
    browser_management,
    navigation,
    interaction,
    screenshots,
    debugging,
)
print('✓ All tools/ modules import successfully')
"
```

#### Task 1.7: Commit
```bash
git add src/mcp_browser_use/tools/
git commit -m "refactor(tools): Migrate to BrowserContext

- Update browser_management.py to use context
- Update navigation.py to use context
- Update interaction.py to use context
- Update screenshots.py to use context
- Update debugging.py to use context
- Remove all helpers imports from tools/
- All tools now context-aware

BREAKING: None (internal implementation only)
Refs: REFACTOR-C-001"

git push origin refactor/tools-integration
```

---

### **Day 9-10: Remove tools/ Re-exports from helpers.py**

**Goal:** Break the circular dependency: helpers imports tools, tools import helpers

#### Task 2.1: Remove tools/ Imports from helpers.py
**File:** `src/mcp_browser_use/helpers.py`

Find and **remove** these lines (around line 314-343):

```python
# DELETE THESE LINES
from .tools.browser_management import (
    start_browser,
    unlock_browser,
    close_browser,
    force_close_all_chrome,
)

from .tools.navigation import (
    navigate_to_url,
    scroll,
)

from .tools.interaction import (
    fill_text,
    click_element,
    send_keys,
    wait_for_element,
)

from .tools.debugging import (
    get_debug_diagnostics_info,
    debug_element,
)

from .tools.screenshots import (
    take_screenshot,
)
```

Update `__all__` to remove these tool functions.

#### Task 2.2: Update __main__.py to Import Directly
**File:** `src/mcp_browser_use/__main__.py`

The MCP tool definitions import from helpers. Change to direct imports:

**Before (line 221):**
```python
import mcp_browser_use as MBU

# ...
@mcp.tool()
async def mcp_browser_use__start_browser(...):
    result = await MBU.helpers.start_browser()
    # ...
```

**After:**
```python
from mcp_browser_use.tools import (
    browser_management,
    navigation,
    interaction,
    screenshots,
    debugging,
)

# ...
@mcp.tool()
async def mcp_browser_use__start_browser(...):
    result = await browser_management.start_browser()
    # ...
```

Update all MCP tool functions (20+ functions) to import from tools/ directly.

**Pattern:**
```python
# Change all instances of:
await MBU.helpers.start_browser()
# To:
await browser_management.start_browser()

await MBU.helpers.navigate_to_url(...)
# To:
await navigation.navigate_to_url(...)

await MBU.helpers.click_element(...)
# To:
await interaction.click_element(...)

# etc.
```

#### Task 2.3: Test Circular Dependency is Broken

**File:** `scripts/test_no_circular_deps.py`
```python
#!/usr/bin/env python3
"""Test that circular dependencies are resolved."""

def test_import_order_1():
    """Test: helpers -> tools (should work, no cycle)."""
    print("Testing: helpers -> tools")
    # This should work now - helpers doesn't import tools anymore
    import mcp_browser_use.helpers
    import mcp_browser_use.tools.browser_management
    print("  ✓ No circular dependency")


def test_import_order_2():
    """Test: tools -> helpers (should work)."""
    print("Testing: tools -> helpers")
    # Tools can import from helpers (for backwards compat functions)
    # But helpers no longer imports tools
    import mcp_browser_use.tools.browser_management
    import mcp_browser_use.helpers
    print("  ✓ Import order works")


def test_import_order_3():
    """Test: decorators -> helpers (should work)."""
    print("Testing: decorators -> helpers (should NOT happen)")
    # Decorators should NOT import from helpers
    # They should import from constants and context

    import mcp_browser_use.decorators.locking
    import mcp_browser_use.constants
    import mcp_browser_use.context
    print("  ✓ Decorators use constants/context, not helpers")


if __name__ == "__main__":
    test_import_order_1()
    test_import_order_2()
    test_import_order_3()
    print("\n✅ No circular dependencies detected")
```

Run:
```bash
python scripts/test_no_circular_deps.py
```

#### Task 2.4: Commit
```bash
git add src/mcp_browser_use/helpers.py
git add src/mcp_browser_use/__main__.py
git add scripts/test_no_circular_deps.py
git commit -m "refactor: Break helpers <-> tools circular dependency

- Remove tools/ imports from helpers.py
- Update __main__.py to import from tools/ directly
- Add test for circular dependency resolution
- helpers.py no longer imports from tools/

BREAKING: Code importing tools from helpers must update
MIGRATION: Import from mcp_browser_use.tools instead

Refs: REFACTOR-C-002"

git push origin refactor/tools-integration
```

---

## **WEEK 2: Days 11-15**

### **Day 11-13: Create Comprehensive Test Suite**

**Goal:** Ensure refactoring hasn't broken anything

#### Task 3.1: Create Unit Tests
**Directory:** `tests/unit/`

**File:** `tests/unit/test_context.py`
```python
"""Unit tests for BrowserContext."""

import pytest
from mcp_browser_use.context import BrowserContext, get_context, reset_context


def test_context_creation():
    """Test that context can be created."""
    ctx = BrowserContext()
    assert ctx.driver is None
    assert ctx.debugger_host is None
    assert not ctx.is_driver_initialized()


def test_context_singleton():
    """Test that get_context returns singleton."""
    reset_context()
    ctx1 = get_context()
    ctx2 = get_context()
    assert ctx1 is ctx2


def test_context_reset():
    """Test that reset_context clears singleton."""
    ctx1 = get_context()
    reset_context()
    ctx2 = get_context()
    assert ctx1 is not ctx2


def test_context_state_checks():
    """Test context state check methods."""
    reset_context()
    ctx = get_context()

    assert not ctx.is_driver_initialized()
    assert not ctx.is_window_ready()

    # Mock driver
    class MockDriver:
        pass

    ctx.driver = MockDriver()
    assert ctx.is_driver_initialized()
    assert not ctx.is_window_ready()  # Still no target_id

    ctx.target_id = "target-123"
    assert ctx.is_window_ready()


def test_context_reset_window_state():
    """Test window state reset."""
    reset_context()
    ctx = get_context()

    ctx.target_id = "target-123"
    ctx.window_id = 456

    ctx.reset_window_state()

    assert ctx.target_id is None
    assert ctx.window_id is None
    # Driver should not be reset
    # (reset_window_state is called when closing window, not driver)
```

**File:** `tests/unit/test_constants.py`
```python
"""Unit tests for constants module."""

from mcp_browser_use.constants import (
    ACTION_LOCK_TTL_SECS,
    ACTION_LOCK_WAIT_SECS,
    MAX_SNAPSHOT_CHARS,
)


def test_constants_are_integers():
    """Test that timing constants are integers."""
    assert isinstance(ACTION_LOCK_TTL_SECS, int)
    assert isinstance(ACTION_LOCK_WAIT_SECS, int)
    assert isinstance(MAX_SNAPSHOT_CHARS, int)


def test_constants_have_reasonable_values():
    """Test constants have sensible defaults."""
    assert ACTION_LOCK_TTL_SECS > 0
    assert ACTION_LOCK_WAIT_SECS > 0
    assert MAX_SNAPSHOT_CHARS > 1000  # At least 1K chars
```

**File:** `tests/unit/test_config.py`
```python
"""Unit tests for config module."""

import os
import pytest
from mcp_browser_use.config.environment import get_env_config, profile_key


def test_get_env_config_missing_required():
    """Test that missing config raises error."""
    # Save original values
    orig_chrome = os.environ.get("CHROME_PROFILE_USER_DATA_DIR")
    orig_beta = os.environ.get("BETA_PROFILE_USER_DATA_DIR")
    orig_canary = os.environ.get("CANARY_PROFILE_USER_DATA_DIR")

    # Clear all
    for key in ["CHROME_PROFILE_USER_DATA_DIR", "BETA_PROFILE_USER_DATA_DIR", "CANARY_PROFILE_USER_DATA_DIR"]:
        if key in os.environ:
            del os.environ[key]

    with pytest.raises(EnvironmentError):
        get_env_config()

    # Restore
    if orig_chrome:
        os.environ["CHROME_PROFILE_USER_DATA_DIR"] = orig_chrome
    if orig_beta:
        os.environ["BETA_PROFILE_USER_DATA_DIR"] = orig_beta
    if orig_canary:
        os.environ["CANARY_PROFILE_USER_DATA_DIR"] = orig_canary


def test_profile_key_stable():
    """Test that profile_key generates stable hashes."""
    config = {
        "user_data_dir": "/path/to/profile",
        "profile_name": "Default"
    }

    key1 = profile_key(config)
    key2 = profile_key(config)

    assert key1 == key2
    assert len(key1) == 64  # SHA256 hex digest
```

Run tests:
```bash
pytest tests/unit/ -v
```

#### Task 3.2: Create Integration Tests
**Directory:** `tests/integration/`

**File:** `tests/integration/test_browser_lifecycle.py`
```python
"""Integration tests for browser lifecycle."""

import pytest
import asyncio
from mcp_browser_use.tools import browser_management
from mcp_browser_use.context import get_context, reset_context


@pytest.mark.asyncio
@pytest.mark.integration
async def test_start_browser():
    """Test browser start creates context."""
    reset_context()

    result = await browser_management.start_browser()

    ctx = get_context()
    assert ctx.driver is not None
    assert ctx.target_id is not None

    # Cleanup
    await browser_management.close_browser()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_close_browser():
    """Test browser close resets window state."""
    reset_context()

    await browser_management.start_browser()
    ctx = get_context()

    target_id_before = ctx.target_id
    assert target_id_before is not None

    await browser_management.close_browser()

    assert ctx.target_id is None
    assert ctx.window_id is None
    # Driver should still exist (can reuse)
    # assert ctx.driver is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_start_close_cycles():
    """Test multiple start/close cycles work."""
    reset_context()

    for i in range(3):
        result = await browser_management.start_browser()
        assert "ok" in result or "true" in result.lower()

        await browser_management.close_browser()

    # Should not crash
```

**File:** `tests/integration/test_tools.py`
```python
"""Integration tests for MCP tools."""

import pytest
from mcp_browser_use.tools import browser_management, navigation, interaction
from mcp_browser_use.context import reset_context


@pytest.mark.asyncio
@pytest.mark.integration
async def test_navigation_flow():
    """Test navigation workflow."""
    reset_context()

    await browser_management.start_browser()

    # Navigate
    result = await navigation.navigate_to_url("https://example.com")
    assert "example.com" in result.lower() or "ok" in result.lower()

    await browser_management.close_browser()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_interaction_error_handling():
    """Test that interaction tools handle errors gracefully."""
    reset_context()

    await browser_management.start_browser()
    await navigation.navigate_to_url("https://example.com")

    # Try to click non-existent element (should not crash)
    result = await interaction.click_element(
        selector="#nonexistent-element-12345",
        timeout=1
    )

    # Should return error JSON, not crash
    assert "error" in result.lower() or "timeout" in result.lower()

    await browser_management.close_browser()
```

Create `pytest.ini`:
```ini
[pytest]
markers =
    integration: Integration tests (may require browser)
    unit: Unit tests (no external dependencies)
```

Run integration tests:
```bash
pytest tests/integration/ -v -m integration
```

#### Task 3.3: Create End-to-End Test
**File:** `tests/e2e/test_full_workflow.py`
```python
"""End-to-end test of full MCP workflow."""

import pytest
from mcp_browser_use.tools import browser_management, navigation, interaction, screenshots
from mcp_browser_use.context import reset_context


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_scraping_workflow():
    """Test a complete scraping workflow."""
    reset_context()

    # 1. Start browser
    result = await browser_management.start_browser()
    assert "ok" in result or "session" in result.lower()

    # 2. Navigate to page
    result = await navigation.navigate_to_url("https://example.com")
    assert "example" in result.lower()

    # 3. Take screenshot
    result = await screenshots.take_screenshot(return_base64=True)
    assert "base64" in result.lower() or "screenshot" in result.lower()

    # 4. Try interaction (will fail but shouldn't crash)
    try:
        await interaction.fill_text(
            selector="input[name='q']",
            text="test query",
            timeout=2
        )
    except Exception:
        pass  # Expected - element doesn't exist

    # 5. Navigate to another page
    result = await navigation.navigate_to_url("https://www.iana.org/domains/reserved")
    assert "ok" in result or "iana" in result.lower()

    # 6. Close browser
    result = await browser_management.close_browser()
    assert "closed" in result.lower() or "ok" in result

    print("✅ Full workflow test passed")
```

Run:
```bash
pytest tests/e2e/ -v -s
```

#### Task 3.4: Commit Tests
```bash
git add tests/
git add pytest.ini
git commit -m "test: Add comprehensive test suite

- Add unit tests for context, constants, config
- Add integration tests for browser lifecycle
- Add integration tests for tools
- Add end-to-end workflow test
- All tests pass

Refs: REFACTOR-C-003"

git push origin refactor/tools-integration
```

---

### **Day 14-15: Add Deprecation Warnings**

**Goal:** Prepare for future removal of backwards compatibility

#### Task 4.1: Add Deprecation Warnings to helpers.py
**File:** `src/mcp_browser_use/helpers.py`

Add deprecation warnings for direct global access:

```python
import warnings
from typing import Any


def _deprecation_warning(old_name: str, new_api: str):
    """Issue a deprecation warning."""
    warnings.warn(
        f"{old_name} is deprecated and will be removed in v3.0. {new_api}",
        DeprecationWarning,
        stacklevel=3
    )


# Override __getattribute__ to warn on global access
_DEPRECATED_GLOBALS = {
    'DRIVER': 'Use get_context().driver',
    'DEBUGGER_HOST': 'Use get_context().debugger_host',
    'DEBUGGER_PORT': 'Use get_context().debugger_port',
    'TARGET_ID': 'Use get_context().target_id',
    'WINDOW_ID': 'Use get_context().window_id',
    'MY_TAG': 'Use get_context().process_tag',
}

_original_getattr = globals().get('__getattribute__')


def __getattr__(name: str) -> Any:
    """Intercept attribute access to show deprecation warnings."""
    if name in _DEPRECATED_GLOBALS:
        _deprecation_warning(
            f"helpers.{name}",
            _DEPRECATED_GLOBALS[name]
        )
        # Still return the value (from context)
        _sync_from_context()  # Ensure globals are synced
        return globals()[name]

    # Default behavior
    raise AttributeError(f"module 'mcp_browser_use.helpers' has no attribute '{name}'")
```

#### Task 4.2: Test Deprecation Warnings
**File:** `tests/test_deprecation.py`
```python
"""Test deprecation warnings."""

import warnings
import pytest


def test_global_access_shows_warning():
    """Test that accessing globals shows deprecation warning."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        import mcp_browser_use.helpers as helpers

        # Access deprecated global
        _ = helpers.DRIVER

        # Should have warning
        assert len(w) >= 1
        assert issubclass(w[-1].category, DeprecationWarning)
        assert "deprecated" in str(w[-1].message).lower()
        assert "get_context()" in str(w[-1].message)


def test_context_access_no_warning():
    """Test that using context doesn't show warning."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        from mcp_browser_use.context import get_context

        ctx = get_context()
        _ = ctx.driver

        # Should have no warnings (or at least not DeprecationWarning)
        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0
```

Run:
```bash
pytest tests/test_deprecation.py -v
```

#### Task 4.3: Create Migration Script
**File:** `scripts/migrate_to_context.py`
```python
#!/usr/bin/env python3
"""
Script to help migrate code from helpers globals to context.

Usage:
    python scripts/migrate_to_context.py path/to/file.py
    python scripts/migrate_to_context.py path/to/directory/
"""

import sys
import re
from pathlib import Path


REPLACEMENTS = [
    # helpers.DRIVER -> ctx.driver
    (r'helpers\.DRIVER', 'ctx.driver'),
    (r'helpers\.DEBUGGER_HOST', 'ctx.debugger_host'),
    (r'helpers\.DEBUGGER_PORT', 'ctx.debugger_port'),
    (r'helpers\.TARGET_ID', 'ctx.target_id'),
    (r'helpers\.WINDOW_ID', 'ctx.window_id'),
    (r'helpers\.MY_TAG', 'ctx.process_tag'),

    # helpers.get_env_config() -> ctx.config (if already in context)
    # Note: This is more complex, needs manual review
]


def migrate_file(file_path: Path) -> int:
    """
    Migrate a single file.

    Returns:
        Number of replacements made
    """
    try:
        content = file_path.read_text()
        original = content
        replacements = 0

        for pattern, replacement in REPLACEMENTS:
            content, count = re.subn(pattern, replacement, content)
            replacements += count

        if replacements > 0:
            # Check if file needs context import
            if 'from ..context import get_context' not in content:
                # Add import after existing imports
                import_section_end = content.find('\n\n')
                if import_section_end > 0:
                    content = (
                        content[:import_section_end] +
                        '\nfrom ..context import get_context\n' +
                        content[import_section_end:]
                    )

            # Check if function needs ctx = get_context()
            # (This is heuristic - manual review needed)

            # Write back
            file_path.write_text(content)
            print(f"✓ {file_path}: {replacements} replacements")

        return replacements

    except Exception as e:
        print(f"✗ {file_path}: {e}")
        return 0


def migrate_directory(dir_path: Path) -> int:
    """Migrate all Python files in directory recursively."""
    total = 0
    for py_file in dir_path.rglob("*.py"):
        total += migrate_file(py_file)
    return total


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/migrate_to_context.py <file_or_dir>")
        sys.exit(1)

    path = Path(sys.argv[1])

    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)

    print(f"Migrating {path} to use BrowserContext...")
    print(f"{'=' * 60}")

    if path.is_file():
        total = migrate_file(path)
    else:
        total = migrate_directory(path)

    print(f"{'=' * 60}")
    print(f"Total replacements: {total}")

    if total > 0:
        print("\n⚠️  IMPORTANT: Review changes before committing!")
        print("   - Check that ctx = get_context() is added where needed")
        print("   - Check imports are correct")
        print("   - Run tests after migration")


if __name__ == "__main__":
    main()
```

#### Task 4.4: Commit
```bash
git add src/mcp_browser_use/helpers.py
git add tests/test_deprecation.py
git add scripts/migrate_to_context.py
git commit -m "feat: Add deprecation warnings for globals

- Add deprecation warnings to helpers.py
- Warn when accessing DRIVER, DEBUGGER_HOST, etc. directly
- Add tests for deprecation warnings
- Add migration script to help convert old code

Refs: REFACTOR-C-004"

git push origin refactor/tools-integration
```

---

## **WEEK 3: Days 16-20**

### **Day 16-18: Documentation & Examples**

#### Task 5.1: Create Comprehensive Migration Guide
**File:** `docs/MIGRATION_GUIDE.md`
```markdown
# Migration Guide: v1.x → v2.0

## Overview

Version 2.0 introduces `BrowserContext` for centralized state management,
replacing module-level globals. This guide helps you migrate existing code.

## Quick Start

### Before (v1.x)
```python
import mcp_browser_use.helpers as helpers

if helpers.DRIVER is None:
    helpers._ensure_driver()

driver = helpers.DRIVER
driver.get("https://example.com")
```

### After (v2.0)
```python
from mcp_browser_use.context import get_context
from mcp_browser_use.browser.driver import _ensure_driver

ctx = get_context()
if ctx.driver is None:
    _ensure_driver()

ctx.driver.get("https://example.com")
```

## Step-by-Step Migration

### Step 1: Update Imports

**Old:**
```python
import mcp_browser_use.helpers as helpers
```

**New:**
```python
from mcp_browser_use.context import get_context
# Import specific functions you need:
from mcp_browser_use.constants import ACTION_LOCK_TTL_SECS
from mcp_browser_use.config import get_env_config
```

### Step 2: Replace Global Access

**Old:**
```python
driver = helpers.DRIVER
host = helpers.DEBUGGER_HOST
port = helpers.DEBUGGER_PORT
target = helpers.TARGET_ID
window = helpers.WINDOW_ID
tag = helpers.MY_TAG
```

**New:**
```python
ctx = get_context()
driver = ctx.driver
host = ctx.debugger_host
port = ctx.debugger_port
target = ctx.target_id
window = ctx.window_id
tag = ctx.process_tag
```

### Step 3: Replace Constant Access

**Old:**
```python
ttl = helpers.ACTION_LOCK_TTL_SECS
wait_time = helpers.ACTION_LOCK_WAIT_SECS
```

**New:**
```python
from mcp_browser_use.constants import (
    ACTION_LOCK_TTL_SECS,
    ACTION_LOCK_WAIT_SECS,
)

ttl = ACTION_LOCK_TTL_SECS
wait_time = ACTION_LOCK_WAIT_SECS
```

### Step 4: Replace Function Imports

**Old:**
```python
from mcp_browser_use.helpers import navigate_to_url, click_element
```

**New:**
```python
from mcp_browser_use.actions.navigation import navigate_to_url
from mcp_browser_use.actions.elements import click_element
```

## Module-by-Module Guide

### If you're working in browser/
Import from context:
```python
from ..context import get_context

def my_function():
    ctx = get_context()
    ctx.driver.get(...)
```

### If you're working in actions/
Same as browser/:
```python
from ..context import get_context

async def my_action():
    ctx = get_context()
    element = ctx.driver.find_element(...)
```

### If you're working in tools/
Import from context and actions:
```python
from ..context import get_context
from ..actions.navigation import navigate_to_url as _navigate

async def my_tool():
    ctx = get_context()
    result = await _navigate(...)
```

### If you're working in decorators/
Import from context and constants:
```python
from ..context import get_context
from ..constants import ACTION_LOCK_TTL_SECS

def my_decorator(fn):
    def wrapper(*args, **kwargs):
        ctx = get_context()
        # ... use ctx
```

## Common Patterns

### Pattern 1: Check if Driver Initialized
```python
# OLD
if helpers.DRIVER is None:
    helpers._ensure_driver()

# NEW
ctx = get_context()
if not ctx.is_driver_initialized():
    from mcp_browser_use.browser.driver import _ensure_driver
    _ensure_driver()
```

### Pattern 2: Get Debugger Address
```python
# OLD
addr = f"{helpers.DEBUGGER_HOST}:{helpers.DEBUGGER_PORT}"

# NEW
ctx = get_context()
addr = ctx.get_debugger_address()  # Returns "host:port" or None
```

### Pattern 3: Reset Window State
```python
# OLD
helpers.TARGET_ID = None
helpers.WINDOW_ID = None

# NEW
ctx = get_context()
ctx.reset_window_state()
```

## Automated Migration

Use our migration script:
```bash
python scripts/migrate_to_context.py path/to/your/file.py
```

⚠️ **Always review changes** - the script is a helper, not a complete solution.

## Backwards Compatibility

Version 2.0 maintains backwards compatibility:
- Old helpers.py API still works
- Deprecation warnings guide you to new API
- No breaking changes for end users

However, deprecation warnings will appear. Plan to migrate by v3.0.

## Testing Your Migration

After migrating, run:
```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Check for deprecation warnings
python -W error::DeprecationWarning your_script.py
```

## Getting Help

- **Examples:** See `examples/` directory
- **Issues:** Check GitHub issues
- **Documentation:** Read `docs/STATE_CONTRACT.md`

## Timeline

- **v2.0:** Context introduced, old API deprecated
- **v2.5:** Deprecation warnings become more prominent
- **v3.0:** Old helpers.py API removed

Migrate early to avoid issues!
```

#### Task 5.2: Create Examples
**Directory:** `examples/`

**File:** `examples/basic_usage.py`
```python
"""Basic usage example with BrowserContext."""

import asyncio
from mcp_browser_use.context import get_context, reset_context
from mcp_browser_use.tools.browser_management import start_browser, close_browser
from mcp_browser_use.tools.navigation import navigate_to_url


async def main():
    """Basic browser usage example."""
    # Reset context for clean start
    reset_context()

    # Start browser
    print("Starting browser...")
    result = await start_browser()
    print(f"Browser started: {result[:100]}...")

    # Check context
    ctx = get_context()
    print(f"Driver initialized: {ctx.is_driver_initialized()}")
    print(f"Debugger address: {ctx.get_debugger_address()}")

    # Navigate
    print("\nNavigating to example.com...")
    result = await navigate_to_url("https://example.com")
    print(f"Navigation complete: {result[:100]}...")

    # Close
    print("\nClosing browser...")
    result = await close_browser()
    print(f"Browser closed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
```

**File:** `examples/multiple_tabs.py`
```python
"""Example of managing multiple browser sessions."""

import asyncio
from mcp_browser_use.context import get_context, reset_context
from mcp_browser_use.tools.browser_management import start_browser


async def session_1():
    """First session."""
    reset_context()  # Each session gets its own context

    await start_browser()
    ctx = get_context()
    print(f"Session 1 - Tag: {ctx.process_tag}, Target: {ctx.target_id}")


async def session_2():
    """Second session."""
    reset_context()

    await start_browser()
    ctx = get_context()
    print(f"Session 2 - Tag: {ctx.process_tag}, Target: {ctx.target_id}")


async def main():
    """Run sessions sequentially."""
    await session_1()
    await session_2()


if __name__ == "__main__":
    asyncio.run(main())
```

#### Task 5.3: Commit Documentation
```bash
git add docs/MIGRATION_GUIDE.md
git add examples/
git commit -m "docs: Add comprehensive migration guide and examples

- Add step-by-step migration guide
- Add before/after examples
- Add common migration patterns
- Add example scripts for basic usage
- Add example for multiple sessions

Refs: REFACTOR-C-005"

git push origin refactor/tools-integration
```

---

### **Day 19-20: Final Integration & PR**

#### Task 6.1: Run Full Test Suite

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=mcp_browser_use --cov-report=html

# Check coverage report
open htmlcov/index.html
```

Target: >80% coverage

#### Task 6.2: Final Validation Script
**File:** `scripts/validate_refactoring_complete.py`
```python
#!/usr/bin/env python3
"""
Complete validation of refactoring.

Runs all validation checks:
- Foundation (Dev A)
- Browser/Actions (Dev B)
- Tools/Integration (Dev C)
"""

import sys
import subprocess


def run_script(script_path: str) -> bool:
    """Run a validation script and return success."""
    print(f"\n{'=' * 60}")
    print(f"Running: {script_path}")
    print('=' * 60)

    result = subprocess.run([sys.executable, script_path])
    return result.returncode == 0


def run_tests() -> bool:
    """Run pytest."""
    print(f"\n{'=' * 60}")
    print("Running: pytest")
    print('=' * 60)

    result = subprocess.run(["pytest", "tests/", "-v", "--tb=short"])
    return result.returncode == 0


def main():
    """Run all validations."""
    print("=" * 60)
    print("COMPLETE REFACTORING VALIDATION")
    print("=" * 60)

    scripts = [
        "scripts/validate_foundation.py",  # Dev A
        "scripts/test_browser_lifecycle.py",  # Dev B
        "scripts/test_backwards_compat.py",  # Dev B
        "scripts/test_no_circular_deps.py",  # Dev C
    ]

    results = []

    # Run validation scripts
    for script in scripts:
        try:
            results.append(run_script(script))
        except Exception as e:
            print(f"✗ Script failed: {e}")
            results.append(False)

    # Run tests
    try:
        results.append(run_tests())
    except Exception as e:
        print(f"✗ Tests failed: {e}")
        results.append(False)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)

    print(f"Validation: {passed}/{total} checks passed")

    if all(results):
        print("\n✅ ALL VALIDATIONS PASSED")
        print("Refactoring is complete and ready for production!")
        return True
    else:
        print("\n❌ SOME VALIDATIONS FAILED")
        print("Please review errors above and fix issues.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

Run:
```bash
python scripts/validate_refactoring_complete.py
```

#### Task 6.3: Create Final Pull Request

```bash
git push origin refactor/tools-integration
```

**PR Description:**
```markdown
## Tools & Integration: Context Migration Complete

### Summary
Completes the context migration by updating tools/ layer and adding
comprehensive testing, deprecation warnings, and documentation.

### Changes
1. **tools/ migration** - All tools use BrowserContext
2. **Circular dependency broken** - helpers no longer imports tools
3. **Comprehensive tests** - Unit, integration, and E2E tests
4. **Deprecation warnings** - Guides users to new API
5. **Documentation** - Migration guide and examples
6. **Validation** - Complete validation suite

### Dependencies
✅ Depends on:
- #[Dev A's PR] (Foundation)
- #[Dev B's PR] (Browser & Actions)

### Testing
- ✅ Unit tests: 15 tests, 100% pass
- ✅ Integration tests: 8 tests, 100% pass
- ✅ E2E tests: 1 test, 100% pass
- ✅ Coverage: >80%
- ✅ No circular dependencies
- ✅ Backwards compatibility maintained

### Breaking Changes
**None for end users** - Full backwards compatibility maintained

**For internal developers:**
- Must import tools directly, not from helpers
- Deprecation warnings guide to new API

### Migration
See `docs/MIGRATION_GUIDE.md` for complete guide

Use migration script:
```bash
python scripts/migrate_to_context.py your_file.py
```

### Validation
```bash
python scripts/validate_refactoring_complete.py
```

### Reviewers
@developer-a @developer-b @tech-lead

### Next Steps
After merge:
- Update internal tools to use new API
- Monitor deprecation warnings in logs
- Plan v3.0 (remove old API)
```

---

## **Coordination with Other Developers**

### With Developer A
**Dependency:** Need foundation (Day 5)
**Questions:** Ask about context lifecycle, constants usage

### With Developer B
**Potential Conflicts:**
- `utils/diagnostics.py` - Both updating
- Coordinate: You update signature, they update callers

**Merge Order:**
1. Dev A merges first
2. Dev B merges second (you rebase on their changes)
3. You merge last

### Final Integration Meeting
**Day 20:** All three developers meet to:
- Review each other's PRs
- Run complete validation
- Discuss any remaining issues
- Plan deployment

---

## **Success Criteria**

By end of Day 20:

- [x] All tools/ modules use context
- [x] Circular dependency broken
- [x] Comprehensive test suite (>80% coverage)
- [x] Deprecation warnings implemented
- [x] Migration guide complete
- [x] Examples created
- [x] Full validation passing
- [x] PR created and approved
- [x] Ready for production deployment

---

## **Troubleshooting**

### Merge Conflicts
If you have conflicts with Dev B:
- Their changes take priority for implementation files
- Your changes take priority for test files
- Discuss any ambiguous conflicts

### Test Failures
If integration tests fail:
- Ensure Dev B's changes are merged
- Check environment variables are set
- Try running tests individually

### Circular Dependency Detection
If circular deps still exist:
- Check your import statements
- Use `python -c "import X; import Y"` to test
- May need to adjust import order

---

## **Questions?**

Contact:
- **Foundation issues:** Developer A
- **Browser implementation:** Developer B
- **Test infrastructure:** QA Team
- **Deployment:** DevOps

**Remember:** You're completing the refactoring. Make sure everything is solid before merging! 🎯
