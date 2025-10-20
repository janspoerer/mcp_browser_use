# Developer B: Browser & Actions Modules

**Role:** Implementation Layer - Browser & Action Logic
**Timeline:** Days 6-17 (starts after Dev A Day 5)
**Branch:** `refactor/browser-actions`

## Your Responsibilities
You own the browser lifecycle and action implementations. You'll migrate browser/ and actions/ modules to use the new BrowserContext and break dependencies on helpers.py.

---

## **PREREQUISITES**

⚠️ **BLOCKED UNTIL:** Developer A completes Day 5 (BrowserContext creation)

Once unblocked, pull latest:
```bash
git checkout main
git pull origin main
git checkout -b refactor/browser-actions
git merge origin/refactor/foundation-state  # Get Dev A's changes
```

Verify you have:
- [ ] `src/mcp_browser_use/constants.py`
- [ ] `src/mcp_browser_use/context.py`
- [ ] `src/mcp_browser_use/config/`
- [ ] Updated `src/mcp_browser_use/helpers.py` with context integration

---

## **WEEK 1: Days 6-10**

### **Day 6-7: Update browser/driver.py to Use Context**

**Goal:** Replace global variable accessors with context

#### Task 1.1: Remove Temporary Global Accessors
**File:** `src/mcp_browser_use/browser/driver.py`

Developer A added temporary global accessors. Replace them with direct context usage.

**Remove these** (Dev A's temporary code):
```python
# DELETE THIS SECTION
def _get_helpers_module():
    """Lazy import to avoid circular dependencies."""
    import mcp_browser_use.helpers as helpers
    return helpers

def _get_global(name):
    """Get global from helpers module with caching."""
    # ... DELETE

def _set_global(name, value):
    """Set global in helpers module."""
    # ... DELETE
```

**Add at top of file:**
```python
from ..context import get_context
```

#### Task 1.2: Update _ensure_driver()

**Before (Dev A's temporary fix):**
```python
def _ensure_driver() -> None:
    DRIVER = _get_global('DRIVER')
    if DRIVER is not None:
        return
    # ...
```

**After:**
```python
def _ensure_driver() -> None:
    """Attach Selenium to Chrome instance."""
    ctx = get_context()

    if ctx.driver is not None:
        return

    _ensure_debugger_ready(ctx.config)

    if not (ctx.debugger_host and ctx.debugger_port):
        return

    ctx.driver = create_webdriver(
        ctx.debugger_host,
        ctx.debugger_port,
        ctx.config
    )
```

#### Task 1.3: Update ensure_process_tag()

**Before:**
```python
def ensure_process_tag() -> str:
    MY_TAG = _get_global('MY_TAG')
    if MY_TAG is None:
        MY_TAG = make_process_tag()
        _set_global('MY_TAG', MY_TAG)
    return MY_TAG
```

**After:**
```python
def ensure_process_tag() -> str:
    """Get or create process tag in context."""
    ctx = get_context()

    if ctx.process_tag is None:
        ctx.process_tag = make_process_tag()

    return ctx.process_tag
```

#### Task 1.4: Update _ensure_singleton_window()

This is a big function. Update systematically:

**Before (line 72):**
```python
def _ensure_singleton_window(driver: webdriver.Chrome):
    global TARGET_ID, WINDOW_ID

    if TARGET_ID:
        if _validate_window_context(driver, TARGET_ID):
            return
        # ...
```

**After:**
```python
def _ensure_singleton_window(driver: webdriver.Chrome):
    """Ensure we have a singleton window for this process."""
    ctx = get_context()

    # 0) If we already have a target, validate context
    if ctx.target_id:
        if _validate_window_context(driver, ctx.target_id):
            return

        # Context validation failed - attempt recovery
        h = _handle_for_target(driver, ctx.target_id)
        if h:
            try:
                driver.switch_to.window(h)
                if _validate_window_context(driver, ctx.target_id):
                    return
            except Exception:
                pass

        # Recovery failed - clear target and recreate
        ctx.reset_window_state()

    # 1) Create new window if we don't have a target
    if not ctx.target_id:
        # Cleanup orphaned windows
        try:
            cleanup_orphaned_windows(driver)
        except Exception as e:
            logger.debug(f"Window cleanup failed (non-critical): {e}")

        try:
            win = driver.execute_cdp_cmd("Browser.createWindow", {"state": "normal"})
            if not isinstance(win, dict):
                raise RuntimeError(f"Browser.createWindow returned {win!r}")

            ctx.window_id = win.get("windowId")
            ctx.target_id = win.get("targetId")

            if not ctx.target_id:
                # Fallback
                t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
                if not isinstance(t, dict) or "targetId" not in t:
                    raise RuntimeError(f"Target.createTarget returned {t!r}")

                ctx.target_id = t["targetId"]

                if not ctx.window_id:
                    try:
                        w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": ctx.target_id}) or {}
                        ctx.window_id = w.get("windowId")
                    except Exception:
                        ctx.window_id = None
        except Exception:
            # Last resort
            t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
            if not isinstance(t, dict) or "targetId" not in t:
                raise RuntimeError(f"Target.createTarget returned {t!r}")

            ctx.target_id = t["targetId"]
            try:
                w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": ctx.target_id}) or {}
                ctx.window_id = w.get("windowId")
            except Exception:
                ctx.window_id = None

    # 2) Map targetId -> Selenium handle
    h = _handle_for_target(driver, ctx.target_id)
    if not h:
        for _ in range(20):
            time.sleep(0.05)
            h = _handle_for_target(driver, ctx.target_id)
            if h:
                break

    if h:
        driver.switch_to.window(h)

        if not _validate_window_context(driver, ctx.target_id):
            raise RuntimeError(f"Failed to establish correct window context for target {ctx.target_id}")

        # Register window
        try:
            owner = ensure_process_tag()
            _register_window(owner, ctx.target_id, ctx.window_id)
        except Exception as e:
            logger.debug(f"Window registration failed (non-critical): {e}")
    else:
        raise RuntimeError(f"Failed to find window handle for target {ctx.target_id}")
```

#### Task 1.5: Update _ensure_driver_and_window()

**Before:**
```python
def _ensure_driver_and_window() -> None:
    global DRIVER, TARGET_ID
    _ensure_driver()
    if DRIVER is None:
        return
    _ensure_singleton_window(DRIVER)
```

**After:**
```python
def _ensure_driver_and_window() -> None:
    """Ensure both driver and window are ready."""
    _ensure_driver()

    ctx = get_context()
    if ctx.driver is None:
        return

    _ensure_singleton_window(ctx.driver)
```

#### Task 1.6: Update _close_extra_blank_windows_safe()

**Before (line 167):**
```python
def _close_extra_blank_windows_safe(driver, exclude_handles=None) -> int:
    exclude = set(exclude_handles or ())
    own_window_id = WINDOW_ID  # Global
    if own_window_id is None:
        return 0
```

**After:**
```python
def _close_extra_blank_windows_safe(driver, exclude_handles=None) -> int:
    """Close extra blank windows, only within our own OS window."""
    exclude = set(exclude_handles or ())

    ctx = get_context()
    own_window_id = ctx.window_id
    if own_window_id is None:
        return 0
    # ... rest unchanged
```

#### Task 1.7: Update close_singleton_window()

**Before:**
```python
def close_singleton_window() -> bool:
    global DRIVER, TARGET_ID, WINDOW_ID
    if DRIVER is None or not TARGET_ID:
        return False

    closed = False
    try:
        DRIVER.execute_cdp_cmd("Target.closeTarget", {"targetId": TARGET_ID})
        closed = True
    # ...
    TARGET_ID = None
    WINDOW_ID = None
    return closed
```

**After:**
```python
def close_singleton_window() -> bool:
    """Close the singleton window without quitting Chrome."""
    ctx = get_context()

    if ctx.driver is None or not ctx.target_id:
        return False

    closed = False
    try:
        ctx.driver.execute_cdp_cmd("Target.closeTarget", {"targetId": ctx.target_id})
        closed = True
    except Exception:
        # Fallback
        try:
            h = _handle_for_target(ctx.driver, ctx.target_id)
            if h:
                ctx.driver.switch_to.window(h)
                ctx.driver.close()
                closed = True
        except Exception:
            pass

    # Unregister window
    if closed:
        try:
            owner = ensure_process_tag()
            _unregister_window(owner)
        except Exception as e:
            logger.debug(f"Window unregistration failed (non-critical): {e}")

    ctx.reset_window_state()
    return closed
```

#### Task 1.8: Remove Unused Global Variables

At top of file, **remove these lines**:
```python
# DELETE THESE
_global_driver: Optional[webdriver.Chrome] = None
_global_target_id: Optional[str] = None
_global_window_id: Optional[int] = None
```

They were defined but never used.

#### Task 1.9: Test driver.py
```bash
python -c "
from mcp_browser_use.browser.driver import (
    _ensure_driver,
    _ensure_driver_and_window,
    close_singleton_window,
)
from mcp_browser_use.context import get_context

ctx = get_context()
print('✓ driver.py uses context correctly')
"
```

#### Task 1.10: Commit
```bash
git add src/mcp_browser_use/browser/driver.py
git commit -m "refactor(driver): Migrate to BrowserContext

- Remove temporary global accessors (from Dev A)
- Use get_context() throughout
- Update _ensure_driver to use ctx.driver
- Update _ensure_singleton_window to use ctx.target_id, ctx.window_id
- Update close_singleton_window to use ctx
- Remove unused _global_* variables

BREAKING: None (internal implementation only)
Refs: REFACTOR-B-001"

git push origin refactor/browser-actions
```

---

### **Day 8-9: Update browser/ Supporting Modules**

#### Task 2.1: Update browser/devtools.py
**File:** `src/mcp_browser_use/browser/devtools.py`

Search for imports from `helpers`. Update to use `context`:

```python
# Add at top
from ..context import get_context
```

Find functions that use globals and update:

**Example - _ensure_debugger_ready():**
```python
# If it sets DEBUGGER_HOST, DEBUGGER_PORT:
def _ensure_debugger_ready(config: dict):
    """Ensure debugger is ready and update context."""
    ctx = get_context()

    # ... existing logic to find port/host ...

    # Update context instead of globals
    ctx.debugger_host = host
    ctx.debugger_port = port
```

#### Task 2.2: Update browser/chrome.py
**File:** `src/mcp_browser_use/browser/chrome.py`

This file orchestrates Chrome startup. It may set debugger_host/port.

Search for any code that:
- Imports from helpers
- Uses global variables

Update to use context:
```python
from ..context import get_context

# In start_or_attach_chrome_from_env():
def start_or_attach_chrome_from_env(config: dict) -> Tuple[str, int, Optional[psutil.Process]]:
    # ... existing logic ...

    # After determining host/port:
    ctx = get_context()
    ctx.debugger_host = host
    ctx.debugger_port = port

    return host, port, proc
```

#### Task 2.3: Update browser/process.py
**File:** `src/mcp_browser_use/browser/process.py`

Check if it accesses any globals. Update imports to use `context` or `config`:

```python
from ..context import get_context
from ..config.paths import get_lock_dir
```

If `rendezvous_path()` uses `profile_key()`:
```python
from ..config.environment import profile_key
```

#### Task 2.4: Test browser/ modules
```bash
python -c "
from mcp_browser_use.browser import (
    driver,
    chrome,
    devtools,
    process,
)
print('✓ All browser/ modules import successfully')
"
```

#### Task 2.5: Commit
```bash
git add src/mcp_browser_use/browser/
git commit -m "refactor(browser): Update supporting modules to use context

- Update devtools.py to use context for debugger state
- Update chrome.py to set context attributes
- Update process.py imports
- All browser/ modules now use BrowserContext

BREAKING: None (internal implementation only)
Refs: REFACTOR-B-002"

git push origin refactor/browser-actions
```

---

### **Day 10: Update actions/ Modules**

#### Task 3.1: Update actions/navigation.py
**File:** `src/mcp_browser_use/actions/navigation.py`

This file likely uses `DRIVER` from helpers. Update:

```python
# At top
from ..context import get_context

# Example function:
async def navigate_to_url(url: str, wait_for: str = "load", timeout_sec: int = 20):
    """Navigate to URL."""
    ctx = get_context()

    if not ctx.driver:
        raise RuntimeError("Driver not initialized")

    ctx.driver.get(url)

    # Wait for page ready
    _wait_document_ready(timeout=timeout_sec)

    # ... rest of function
```

Update all functions that use driver:
- `navigate_to_url()`
- `wait_for_element()`
- `get_current_page_meta()`
- `_wait_document_ready()`

#### Task 3.2: Update actions/elements.py
**File:** `src/mcp_browser_use/actions/elements.py`

Similar updates:

```python
from ..context import get_context

async def click_element(
    selector: str,
    selector_type: str = "css",
    # ... args
):
    """Click an element."""
    ctx = get_context()

    element = find_element(
        ctx.driver,
        selector,
        selector_type,
        timeout,
        iframe_selector,
        # ...
    )

    element.click()
    # ...
```

Update:
- `click_element()`
- `fill_text()`
- `debug_element()`
- `find_element()` - may need driver passed as param

#### Task 3.3: Update actions/keyboard.py
**File:** `src/mcp_browser_use/actions/keyboard.py`

```python
from ..context import get_context

async def send_keys(key: str, selector: Optional[str] = None, ...):
    """Send keyboard keys."""
    ctx = get_context()

    if selector:
        element = find_element(ctx.driver, selector, ...)
        element.send_keys(key)
    else:
        # Send to active element
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(ctx.driver).send_keys(key).perform()
```

Update:
- `send_keys()`
- `scroll()`

#### Task 3.4: Update actions/screenshots.py
**File:** `src/mcp_browser_use/actions/screenshots.py`

```python
from ..context import get_context

async def take_screenshot(
    screenshot_path: Optional[str] = None,
    return_base64: bool = False,
    # ...
):
    """Take screenshot."""
    ctx = get_context()

    screenshot_data = ctx.driver.get_screenshot_as_png()
    # ... process screenshot
```

Update:
- `take_screenshot()`
- `_make_page_snapshot()` - important! This is used everywhere

#### Task 3.5: Test actions/ modules
```bash
python -c "
from mcp_browser_use.actions import (
    navigation,
    elements,
    keyboard,
    screenshots,
)
print('✓ All actions/ modules import successfully')
"
```

#### Task 3.6: Commit
```bash
git add src/mcp_browser_use/actions/
git commit -m "refactor(actions): Migrate to BrowserContext

- Update navigation.py to use ctx.driver
- Update elements.py to use ctx.driver
- Update keyboard.py to use ctx.driver
- Update screenshots.py to use ctx.driver
- All action functions now get driver from context

BREAKING: None (internal implementation only)
Refs: REFACTOR-B-003"

git push origin refactor/browser-actions
```

---

## **WEEK 2: Days 11-14**

### **Day 11-12: Update utils/ Modules**

#### Task 4.1: Update utils/diagnostics.py
**File:** `src/mcp_browser_use/utils/diagnostics.py`

This file currently imports `helpers`. Update:

```python
# Remove
import mcp_browser_use.helpers as helpers

# Add
from ..context import get_context
from ..constants import *
from ..config import get_env_config
```

Update `collect_diagnostics()` function to accept context as parameter:

**Before:**
```python
def collect_diagnostics(driver, error, config):
    # Uses helpers.DRIVER, helpers.DEBUGGER_HOST, etc.
```

**After:**
```python
def collect_diagnostics(driver, error, config=None):
    """
    Collect diagnostics.

    Args:
        driver: WebDriver instance (if None, will try to get from context)
        error: Exception that occurred
        config: Configuration dict (if None, will get from context)
    """
    ctx = get_context()

    if driver is None:
        driver = ctx.driver

    if config is None:
        config = ctx.config

    diagnostics = {
        "driver_initialized": driver is not None,
        "debugger_address": ctx.get_debugger_address(),
        "window_ready": ctx.is_window_ready(),
        "error": str(error) if error else None,
        # ... rest of diagnostics
    }

    return diagnostics
```

#### Task 4.2: Update utils/html_utils.py
**File:** `src/mcp_browser_use/utils/html_utils.py`

Check if it imports any constants from helpers. If so:
```python
from ..constants import MAX_SNAPSHOT_CHARS
```

#### Task 4.3: Test utils/
```bash
python -c "
from mcp_browser_use.utils.diagnostics import collect_diagnostics
from mcp_browser_use.utils.html_utils import get_cleaned_html
print('✓ utils/ modules import successfully')
"
```

#### Task 4.4: Commit
```bash
git add src/mcp_browser_use/utils/
git commit -m "refactor(utils): Update to use context and constants

- Update diagnostics.py to accept context
- Update html_utils.py to import from constants
- All utils now context-aware

BREAKING: None (backwards compatible)
Refs: REFACTOR-B-004"

git push origin refactor/browser-actions
```

---

### **Day 13-14: Update helpers.py - Remove Internal Re-exports**

**Goal:** helpers.py should only re-export for backwards compatibility, not import from submodules

#### Task 5.1: Analyze Current Re-exports
```bash
grep -n "^from \." src/mcp_browser_use/helpers.py | head -50
```

You'll see imports like:
```python
from .locking.file_mutex import (...)
from .browser.driver import (...)
from .actions.navigation import (...)
# etc.
```

#### Task 5.2: Update helpers.py Structure

**Current structure (lines 195-343):**
```python
#region Re-exports from refactored modules
from .locking.file_mutex import (...)
from .browser.driver import (...)
# ... tons of imports
#endregion
```

**New structure:**

```python
#region Backwards Compatibility Re-exports
"""
DEPRECATED: These re-exports are for backwards compatibility only.
New code should import directly from the respective modules.

Example:
    # OLD (deprecated):
    from mcp_browser_use.helpers import navigate_to_url

    # NEW:
    from mcp_browser_use.actions.navigation import navigate_to_url
"""

# Only import what's actually used by external code
# Mark each with deprecation comment

# Core functions still needed by decorators/tools
from .locking.action_lock import (
    get_intra_process_lock,  # Used by decorators
    _acquire_action_lock_or_error,  # Used by decorators
    _renew_action_lock,  # Used by decorators
    _release_action_lock,  # Used by tools
)

from .browser.process import (
    ensure_process_tag,  # Used by decorators/tools
    make_process_tag,  # Used internally
)

from .browser.driver import (
    _ensure_driver,  # DEPRECATED - use directly
    _ensure_driver_and_window,  # Used by tools
    _ensure_singleton_window,  # Used by decorators
    close_singleton_window,  # Used by tools
    _cleanup_own_blank_tabs,  # Used by tools
    _close_extra_blank_windows_safe,  # Used by tools
)

from .actions.navigation import (
    _wait_document_ready,  # Used by tools
)

from .actions.screenshots import (
    _make_page_snapshot,  # Used by tools
)

# DO NOT re-export everything else - force migration
# If someone needs it, they import directly from the module
#endregion
```

#### Task 5.3: Update __all__ Export List

Reduce the massive `__all__` list (currently 90+ items) to only what's truly public API:

```python
__all__ = [
    # Context (NEW - primary API)
    'get_context',
    'reset_context',
    'BrowserContext',

    # Configuration
    'get_env_config',
    'profile_key',
    'get_lock_dir',

    # Constants (re-exported for compatibility)
    'ACTION_LOCK_TTL_SECS',
    'ACTION_LOCK_WAIT_SECS',
    'FILE_MUTEX_STALE_SECS',
    'WINDOW_REGISTRY_STALE_THRESHOLD',
    'MAX_SNAPSHOT_CHARS',

    # Core functions needed by decorators (internal but exported)
    'ensure_process_tag',
    '_ensure_driver_and_window',
    '_ensure_singleton_window',
    '_acquire_action_lock_or_error',
    '_renew_action_lock',
    '_release_action_lock',
    'get_intra_process_lock',

    # Functions needed by tools (internal but exported)
    'close_singleton_window',
    '_cleanup_own_blank_tabs',
    '_wait_document_ready',
    '_make_page_snapshot',
    '_close_extra_blank_windows_safe',

    # Backwards compatibility - DEPRECATED
    # These are kept for old code but should not be used in new code
    'DRIVER',  # DEPRECATED: Use get_context().driver
    'DEBUGGER_HOST',  # DEPRECATED: Use get_context().debugger_host
    'DEBUGGER_PORT',  # DEPRECATED: Use get_context().debugger_port
    'TARGET_ID',  # DEPRECATED: Use get_context().target_id
    'WINDOW_ID',  # DEPRECATED: Use get_context().window_id
    'MY_TAG',  # DEPRECATED: Use get_context().process_tag
]
```

#### Task 5.4: Test Backwards Compatibility

Create test script:
**File:** `scripts/test_backwards_compat.py`
```python
#!/usr/bin/env python3
"""Test that old code still works."""

def test_old_imports():
    """Test that old import patterns still work."""
    print("Testing old import patterns...")

    # Old way (should still work)
    import mcp_browser_use.helpers as helpers

    # Test constants
    assert helpers.ACTION_LOCK_TTL_SECS is not None

    # Test functions
    assert hasattr(helpers, 'get_env_config')
    assert hasattr(helpers, 'ensure_process_tag')

    print("  ✓ Old imports work")


def test_new_imports():
    """Test that new import patterns work."""
    print("Testing new import patterns...")

    # New way (preferred)
    from mcp_browser_use.context import get_context
    from mcp_browser_use.constants import ACTION_LOCK_TTL_SECS
    from mcp_browser_use.config import get_env_config

    ctx = get_context()
    assert ctx is not None

    print("  ✓ New imports work")


if __name__ == "__main__":
    test_old_imports()
    test_new_imports()
    print("\n✅ All backwards compatibility tests passed")
```

Run:
```bash
python scripts/test_backwards_compat.py
```

#### Task 5.5: Commit
```bash
git add src/mcp_browser_use/helpers.py
git add scripts/test_backwards_compat.py
git commit -m "refactor(helpers): Reduce re-exports, improve structure

- Remove re-exports of internal implementation details
- Keep only public API and backwards compatibility items
- Reduce __all__ from 90+ to ~30 items
- Add backwards compatibility test script
- Force new code to import from specific modules

BREAKING: Only for code importing internal functions from helpers
MIGRATION: Import directly from browser/, actions/, etc.
Refs: REFACTOR-B-005"

git push origin refactor/browser-actions
```

---

## **WEEK 3: Days 15-17**

### **Day 15-16: Integration Testing**

#### Task 6.1: Test Full Browser Lifecycle
**File:** `scripts/test_browser_lifecycle.py`

```python
#!/usr/bin/env python3
"""
Test full browser lifecycle with context.
"""

import asyncio
import sys


async def test_lifecycle():
    """Test browser start -> action -> close cycle."""
    print("Testing browser lifecycle...")

    from mcp_browser_use.tools.browser_management import start_browser, close_browser
    from mcp_browser_use.context import get_context, reset_context

    # Reset for clean test
    reset_context()

    # Start browser
    result = await start_browser()
    print(f"  Start result: {result[:100]}...")

    # Check context
    ctx = get_context()
    assert ctx.driver is not None, "Driver should be initialized"
    assert ctx.target_id is not None, "Target ID should be set"
    print(f"  ✓ Browser started: {ctx.get_debugger_address()}")

    # Close browser
    result = await close_browser()
    print(f"  Close result: {result[:100]}...")

    # Check context reset
    assert ctx.target_id is None, "Target ID should be cleared"
    print("  ✓ Browser closed")


async def test_navigation():
    """Test navigation with context."""
    print("\nTesting navigation...")

    from mcp_browser_use.tools.browser_management import start_browser
    from mcp_browser_use.tools.navigation import navigate_to_url
    from mcp_browser_use.context import get_context, reset_context

    reset_context()
    await start_browser()

    # Navigate
    result = await navigate_to_url("https://example.com")
    print(f"  Navigate result: {result[:100]}...")

    ctx = get_context()
    assert ctx.driver is not None
    print("  ✓ Navigation successful")


async def main():
    """Run all tests."""
    try:
        await test_lifecycle()
        await test_navigation()
        print("\n✅ All lifecycle tests passed")
        return True
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
```

Run:
```bash
# Set up environment first
export CHROME_PROFILE_USER_DATA_DIR="/path/to/profile"
python scripts/test_browser_lifecycle.py
```

#### Task 6.2: Test Action Modules
**File:** `scripts/test_actions.py`

```python
#!/usr/bin/env python3
"""Test action modules with context."""

import asyncio


async def test_actions():
    """Test click, fill, etc."""
    from mcp_browser_use.tools.browser_management import start_browser
    from mcp_browser_use.tools.navigation import navigate_to_url
    from mcp_browser_use.tools.interaction import click_element, fill_text

    await start_browser()
    await navigate_to_url("https://example.com")

    # These should not crash (even if selectors don't exist)
    try:
        await click_element(selector="button", timeout=1)
    except Exception:
        pass  # Expected - button doesn't exist

    print("✓ Actions work with context")


if __name__ == "__main__":
    asyncio.run(test_actions())
```

#### Task 6.3: Manual Testing Checklist

Test each MCP tool manually:
- [ ] `start_browser` - Opens browser, sets context
- [ ] `navigate_to_url` - Navigates, uses context.driver
- [ ] `click_element` - Clicks, uses context.driver
- [ ] `fill_text` - Fills form, uses context.driver
- [ ] `take_screenshot` - Screenshots, uses context.driver
- [ ] `close_browser` - Closes window, resets context
- [ ] `get_debug_diagnostics_info` - Shows context state

---

### **Day 17: Documentation & PR**

#### Task 7.1: Create Migration Guide for Browser/Actions
**File:** `docs/MIGRATION_BROWSER_ACTIONS.md`

```markdown
# Migration Guide: Browser & Actions Modules

## For Developers

If you're working on browser/ or actions/ modules, here's how to migrate from the old global-based code to the new context-based code.

### Before (Old API)
```python
import mcp_browser_use.helpers as helpers

def my_function():
    driver = helpers.DRIVER
    if driver is None:
        helpers._ensure_driver()
        driver = helpers.DRIVER

    driver.get("https://example.com")
```

### After (New API)
```python
from mcp_browser_use.context import get_context

def my_function():
    ctx = get_context()

    if ctx.driver is None:
        from mcp_browser_use.browser.driver import _ensure_driver
        _ensure_driver()

    ctx.driver.get("https://example.com")
```

## Common Patterns

### Pattern 1: Getting Driver
```python
# OLD
driver = helpers.DRIVER

# NEW
ctx = get_context()
driver = ctx.driver
```

### Pattern 2: Setting Debugger Info
```python
# OLD
helpers.DEBUGGER_HOST = "127.0.0.1"
helpers.DEBUGGER_PORT = 9222

# NEW
ctx = get_context()
ctx.debugger_host = "127.0.0.1"
ctx.debugger_port = 9222
```

### Pattern 3: Window State
```python
# OLD
target_id = helpers.TARGET_ID
window_id = helpers.WINDOW_ID

# NEW
ctx = get_context()
target_id = ctx.target_id
window_id = ctx.window_id
```

## Module-Specific Guides

### browser/driver.py
- Replace `global DRIVER` with `ctx = get_context()`
- Replace `DRIVER = ...` with `ctx.driver = ...`
- Replace `TARGET_ID = None` with `ctx.reset_window_state()`

### actions/navigation.py
- Import context at top: `from ..context import get_context`
- Get driver from context: `ctx.driver`
- No need to import helpers

### actions/elements.py
- Same as navigation
- Pass driver from context to helper functions

## Testing Your Changes

```bash
# Run import test
python -c "from mcp_browser_use.actions import navigation"

# Run integration test
python scripts/test_browser_lifecycle.py
```
```

#### Task 7.2: Update Main README
**File:** `README.md`

Add section about the refactoring:
```markdown
## Architecture (v2.0)

The codebase uses `BrowserContext` for state management:

```python
from mcp_browser_use.context import get_context

ctx = get_context()
if ctx.driver is None:
    # Initialize browser
    ...
```

For backwards compatibility, the old helpers API still works:
```python
import mcp_browser_use.helpers as helpers
driver = helpers.DRIVER  # Works but deprecated
```

See `docs/STATE_CONTRACT.md` for details.
```

#### Task 7.3: Create Pull Request

```bash
git push origin refactor/browser-actions
```

PR Description:
```markdown
## Browser & Actions: Context Migration

### Summary
Migrates browser/ and actions/ modules to use BrowserContext instead of module-level globals.

### Changes
1. **browser/driver.py** - Complete context migration
2. **browser/ supporting modules** - Use context for state
3. **actions/ all modules** - Use ctx.driver throughout
4. **utils/diagnostics.py** - Context-aware diagnostics
5. **helpers.py** - Reduced re-exports to essentials

### Dependencies
✅ Depends on #[Dev A's PR number] (Foundation)
⏳ Blocks #[Dev C's PR number] (Tools)

### Testing
- ✅ All browser/ modules import successfully
- ✅ All actions/ modules import successfully
- ✅ Browser lifecycle test passes
- ✅ Backwards compatibility maintained
- ✅ No new circular dependencies

### Breaking Changes
**None for external users** - helpers.py maintains compatibility

**For internal developers:**
- Must import directly from browser/, actions/ modules
- Cannot import internal functions from helpers anymore

### Migration Guide
See `docs/MIGRATION_BROWSER_ACTIONS.md`

### Reviewers
@developer-a @developer-c @tech-lead

### Validation
```bash
python scripts/test_browser_lifecycle.py
python scripts/test_backwards_compat.py
```
```

---

## **Coordination with Other Developers**

### With Developer A
**Dependency:** You need Dev A's foundation (Day 5)
**Communication:**
- Ping Dev A when their Day 5 is done
- Review Dev A's context.py to understand the API
- Ask questions about context lifecycle

### With Developer C
**Coordination:**
- Dev C is updating tools/ - minimal overlap
- You may both touch utils/diagnostics.py - coordinate on that file
- Share your test scripts with Dev C

### Sync Points
**Day 6:** Pull Dev A's changes
**Day 10:** Push your progress so Dev C can see patterns
**Day 14:** Final push before PR
**Day 17:** PR ready - notify team

---

## **Success Criteria**

By end of Day 17:

- [x] browser/driver.py fully migrated to context
- [x] All browser/ modules use context
- [x] All actions/ modules use context
- [x] utils/ modules updated
- [x] helpers.py re-exports reduced
- [x] Backwards compatibility maintained
- [x] Integration tests pass
- [x] Documentation complete
- [x] PR created and ready for review

---

## **Troubleshooting**

### "Module not found" errors
- Ensure you pulled Dev A's changes
- Check that constants.py, context.py exist
- Run `git merge origin/refactor/foundation-state`

### Context not working
- Reset context: `from mcp_browser_use.context import reset_context; reset_context()`
- Check get_context() returns singleton
- Verify config is populated

### Tests failing
- Set environment variables (CHROME_PROFILE_USER_DATA_DIR)
- Close any existing Chrome instances
- Run in clean Python environment

---

## **Questions?**

Contact:
- **Foundation issues:** Developer A
- **Tools coordination:** Developer C
- **Testing help:** QA Team

**Remember:** Your work enables proper state management throughout the codebase. Take time to do it right! 🧩
