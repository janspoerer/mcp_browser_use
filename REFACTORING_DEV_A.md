# Developer A: Foundation & Core State Management

**Role:** Foundation Layer - Critical Path
**Timeline:** Days 1-14
**Branch:** `refactor/foundation-state`

## Your Responsibilities
You own the foundational changes that others depend on. Your work must be completed first as it unblocks Developers B and C.

---

## **WEEK 1: Days 1-5**

### **Day 1-2: CRITICAL - Fix Broken driver.py Module**

#### Task 1.1: Add Missing Imports
**File:** `src/mcp_browser_use/browser/driver.py`

Add these imports at the top (after existing imports):
```python
import shutil
import subprocess

# Add these to existing imports section
from .devtools import _ensure_debugger_ready, _handle_for_target
from .process import make_process_tag, chromedriver_log_path
from ..locking.window_registry import (
    cleanup_orphaned_windows,
    _register_window,
    _unregister_window,
)
```

#### Task 1.2: Fix Undefined Global References

The module references globals that don't exist locally. Add this at the top:

```python
# Import module-level globals (temporary - will refactor by Day 5)
def _get_helpers_module():
    """Lazy import to avoid circular dependencies."""
    import mcp_browser_use.helpers as helpers
    return helpers

# Local cache for frequently accessed globals
_helpers_cache = {}

def _get_global(name):
    """Get global from helpers module with caching."""
    helpers = _get_helpers_module()
    return getattr(helpers, name)

def _set_global(name, value):
    """Set global in helpers module."""
    helpers = _get_helpers_module()
    setattr(helpers, name, value)
```

Update each function that uses globals:

**Function: `_ensure_driver()` (line 21)**
```python
def _ensure_driver() -> None:
    """Attach Selenium to the debuggable Chrome instance (headed by default)."""
    DRIVER = _get_global('DRIVER')
    if DRIVER is not None:
        return

    cfg = _get_helpers_module().get_env_config()
    _ensure_debugger_ready(cfg)

    DEBUGGER_HOST = _get_global('DEBUGGER_HOST')
    DEBUGGER_PORT = _get_global('DEBUGGER_PORT')
    if not (DEBUGGER_HOST and DEBUGGER_PORT):
        return

    driver = create_webdriver(DEBUGGER_HOST, DEBUGGER_PORT, cfg)
    _set_global('DRIVER', driver)
```

**Function: `ensure_process_tag()` (line 35)**
```python
def ensure_process_tag() -> str:
    MY_TAG = _get_global('MY_TAG')
    if MY_TAG is None:
        MY_TAG = make_process_tag()
        _set_global('MY_TAG', MY_TAG)
    return MY_TAG
```

Apply similar pattern to all functions using: `TARGET_ID`, `WINDOW_ID`, `DRIVER`

#### Task 1.3: Test Imports
```bash
# Run this to verify no import errors
python -c "from mcp_browser_use.browser import driver; print('✓ driver.py imports successfully')"

# Run a more thorough check
python -c "
from mcp_browser_use.browser.driver import (
    create_webdriver,
    _ensure_driver,
    _ensure_driver_and_window,
    _ensure_singleton_window,
    close_singleton_window,
)
print('✓ All functions importable')
"
```

#### Task 1.4: Commit & Push
```bash
git add src/mcp_browser_use/browser/driver.py
git commit -m "fix(driver): Add missing imports and fix undefined globals

- Add imports for shutil, subprocess, devtools, process, locking modules
- Add temporary global accessors to fix undefined references
- All functions now have proper imports
- Module imports without errors

BREAKING: None (internal implementation only)
Refs: REFACTOR-001"

git push origin refactor/foundation-state
```

**🔴 BLOCKER ALERT:** Create PR immediately after this commit. Developers B & C are blocked until this merges.

---

### **Day 3-5: Create BrowserContext (UNBLOCKS DEV B & C)**

#### Task 2.1: Create constants.py Module
**File:** `src/mcp_browser_use/constants.py` (NEW)

```python
"""
Global constants and configuration defaults.
No dependencies - safe to import from anywhere.

This module extracts constants from helpers.py to break circular dependencies.
"""

import os

# ============================================================================
# Lock Configuration
# ============================================================================

ACTION_LOCK_TTL_SECS = int(os.getenv("MCP_ACTION_LOCK_TTL", "30"))
"""Time-to-live for action locks in seconds."""

ACTION_LOCK_WAIT_SECS = int(os.getenv("MCP_ACTION_LOCK_WAIT", "60"))
"""Maximum time to wait for action lock acquisition in seconds."""

FILE_MUTEX_STALE_SECS = int(os.getenv("MCP_FILE_MUTEX_STALE_SECS", "60"))
"""Consider file mutex stale after this many seconds."""


# ============================================================================
# Window Registry Configuration
# ============================================================================

WINDOW_REGISTRY_STALE_THRESHOLD = int(os.getenv("MCP_WINDOW_REGISTRY_STALE_SECS", "300"))
"""Consider window registry entry stale after this many seconds."""


# ============================================================================
# Rendering Configuration
# ============================================================================

MAX_SNAPSHOT_CHARS = int(os.getenv("MCP_MAX_SNAPSHOT_CHARS", "10000"))
"""Maximum characters in HTML snapshots."""


# ============================================================================
# Chrome Startup Configuration
# ============================================================================

START_LOCK_WAIT_SEC = 8.0
"""How long to wait to acquire the startup lock."""

RENDEZVOUS_TTL_SEC = 24 * 3600
"""How long a rendezvous file is considered valid (24 hours)."""


# ============================================================================
# Feature Flags
# ============================================================================

ALLOW_ATTACH_ANY = os.getenv("MCP_ATTACH_ANY_PROFILE", "0") == "1"
"""Allow attaching to any Chrome profile, not just the configured one."""


__all__ = [
    "ACTION_LOCK_TTL_SECS",
    "ACTION_LOCK_WAIT_SECS",
    "FILE_MUTEX_STALE_SECS",
    "WINDOW_REGISTRY_STALE_THRESHOLD",
    "MAX_SNAPSHOT_CHARS",
    "START_LOCK_WAIT_SEC",
    "RENDEZVOUS_TTL_SEC",
    "ALLOW_ATTACH_ANY",
]
```

#### Task 2.2: Create context.py Module
**File:** `src/mcp_browser_use/context.py` (NEW)

```python
"""
Centralized browser state management.

This module replaces module-level globals with a context object,
providing a single source of truth for browser session state.

Thread Safety:
    The BrowserContext itself is NOT thread-safe. Access should be
    coordinated using the locking decorators (exclusive_browser_access).

Usage:
    from mcp_browser_use.context import get_context

    ctx = get_context()
    if ctx.driver is None:
        # Initialize driver
        ctx.driver = create_driver()
"""

from typing import Optional
from selenium import webdriver
from dataclasses import dataclass, field
import asyncio


@dataclass
class BrowserContext:
    """
    Encapsulates all browser session state.

    This replaces the module-level globals:
        DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, TARGET_ID,
        WINDOW_ID, MY_TAG, LOCK_DIR, etc.

    Attributes:
        driver: Selenium WebDriver instance
        debugger_host: Chrome DevTools debugger hostname
        debugger_port: Chrome DevTools debugger port
        target_id: Chrome DevTools Protocol target ID for this window
        window_id: Chrome window ID (from Browser.getWindowForTarget)
        process_tag: Unique identifier for this process/session
        config: Environment configuration dictionary
        lock_dir: Directory for lock files
        intra_process_lock: Asyncio lock for serializing operations within this process
    """

    # Driver state
    driver: Optional[webdriver.Chrome] = None
    debugger_host: Optional[str] = None
    debugger_port: Optional[int] = None

    # Window state
    target_id: Optional[str] = None
    window_id: Optional[int] = None

    # Process identity
    process_tag: Optional[str] = None

    # Configuration (should be immutable after initialization)
    config: dict = field(default_factory=dict)

    # Lock directory
    lock_dir: str = ""

    # Intra-process lock
    intra_process_lock: Optional[asyncio.Lock] = None

    def is_driver_initialized(self) -> bool:
        """Check if driver is initialized."""
        return self.driver is not None

    def is_window_ready(self) -> bool:
        """Check if browser window is ready."""
        return (
            self.driver is not None
            and self.target_id is not None
        )

    def get_debugger_address(self) -> Optional[str]:
        """Get debugger address as host:port string."""
        if self.debugger_host and self.debugger_port:
            return f"{self.debugger_host}:{self.debugger_port}"
        return None

    def reset_window_state(self) -> None:
        """Reset window state (useful after window close)."""
        self.target_id = None
        self.window_id = None

    def get_intra_process_lock(self) -> asyncio.Lock:
        """Get or create the intra-process asyncio lock."""
        if self.intra_process_lock is None:
            self.intra_process_lock = asyncio.Lock()
        return self.intra_process_lock


# ============================================================================
# Global Context Management
# ============================================================================

_global_context: Optional[BrowserContext] = None


def get_context() -> BrowserContext:
    """
    Get or create the global browser context.

    This is a singleton pattern - all calls return the same context instance.
    Use reset_context() to clear the singleton (mainly for testing).

    Returns:
        The global BrowserContext instance
    """
    global _global_context

    if _global_context is None:
        # Lazy initialization
        from .config.environment import get_env_config
        from .config.paths import get_lock_dir

        _global_context = BrowserContext(
            config=get_env_config(),
            lock_dir=get_lock_dir(),
        )

    return _global_context


def reset_context() -> None:
    """
    Reset the global context.

    ⚠️  WARNING: This is primarily for testing. In production code,
    use close_browser() instead of directly resetting context.

    This will clear all state including driver, window IDs, etc.
    """
    global _global_context
    _global_context = None


__all__ = [
    "BrowserContext",
    "get_context",
    "reset_context",
]
```

#### Task 2.3: Create config/environment.py Module
**File:** `src/mcp_browser_use/config/__init__.py` (NEW)
```python
"""Configuration management."""

from .environment import get_env_config, profile_key
from .paths import get_lock_dir

__all__ = [
    "get_env_config",
    "profile_key",
    "get_lock_dir",
]
```

**File:** `src/mcp_browser_use/config/environment.py` (NEW)
```python
"""
Environment configuration management.

Extracts configuration logic from helpers.py to provide a clean
separation of concerns.
"""

import os
import hashlib
from pathlib import Path
from typing import Dict, Any


def get_env_config() -> Dict[str, Any]:
    """
    Read environment variables and validate required ones.

    Prioritizes Chrome Beta over Chrome Canary over Chrome. This is to free
    the Chrome instance. Chrome is likely used by the user already. It is
    easier to separate the executables. If a user already has the Chrome
    executable open, the MCP will not work properly as the Chrome DevTool
    Debug mode will not open when Chrome is already open in normal mode.
    We prioritize Chrome Beta because it is more stable than Canary.

    Required:
        Either CHROME_PROFILE_USER_DATA_DIR, BETA_PROFILE_USER_DATA_DIR,
        or CANARY_PROFILE_USER_DATA_DIR

    Optional:
        CHROME_PROFILE_NAME (default 'Default')
        CHROME_EXECUTABLE_PATH
        BETA_EXECUTABLE_PATH (overrides CHROME_EXECUTABLE_PATH)
        CANARY_EXECUTABLE_PATH (overrides BETA and CHROME)
        CHROME_REMOTE_DEBUG_PORT

    If BETA_EXECUTABLE_PATH is set, expects:
        BETA_PROFILE_USER_DATA_DIR
        BETA_PROFILE_NAME

    If CANARY_EXECUTABLE_PATH is set, expects:
        CANARY_PROFILE_USER_DATA_DIR
        CANARY_PROFILE_NAME

    Returns:
        Configuration dictionary with keys:
            - user_data_dir: str
            - profile_name: str
            - chrome_path: Optional[str]
            - fixed_port: Optional[int]

    Raises:
        EnvironmentError: If required environment variables are missing
    """
    # Base (generic) config
    user_data_dir = (os.getenv("CHROME_PROFILE_USER_DATA_DIR") or "").strip()
    if not user_data_dir and not os.getenv("BETA_PROFILE_USER_DATA_DIR") and not os.getenv("CANARY_PROFILE_USER_DATA_DIR"):
        raise EnvironmentError(
            "CHROME_PROFILE_USER_DATA_DIR is required. Alternatively, set "
            "BETA_PROFILE_USER_DATA_DIR or CANARY_PROFILE_USER_DATA_DIR."
        )

    profile_name = (os.getenv("CHROME_PROFILE_NAME") or "Default").strip() or "Default"
    chrome_path = (os.getenv("CHROME_EXECUTABLE_PATH") or "").strip() or None

    # Prefer Beta > Canary > Generic Chrome
    canary_path = (os.getenv("CANARY_EXECUTABLE_PATH") or "").strip()
    if canary_path:
        chrome_path = canary_path
        user_data_dir = (os.getenv("CANARY_PROFILE_USER_DATA_DIR") or "").strip()
        profile_name = (os.getenv("CANARY_PROFILE_NAME") or "").strip() or "Default"
        if not user_data_dir:
            raise EnvironmentError(
                "CANARY_PROFILE_USER_DATA_DIR is required when "
                "CANARY_EXECUTABLE_PATH is set."
            )

    beta_path = (os.getenv("BETA_EXECUTABLE_PATH") or "").strip()
    if beta_path:
        chrome_path = beta_path
        user_data_dir = (os.getenv("BETA_PROFILE_USER_DATA_DIR") or "").strip()
        profile_name = (os.getenv("BETA_PROFILE_NAME") or "").strip() or "Default"
        if not user_data_dir:
            raise EnvironmentError(
                "BETA_PROFILE_USER_DATA_DIR is required when "
                "BETA_EXECUTABLE_PATH is set."
            )

    fixed_port_env = (os.getenv("CHROME_REMOTE_DEBUG_PORT") or "").strip()
    fixed_port = int(fixed_port_env) if fixed_port_env.isdigit() else None

    if not user_data_dir:
        raise EnvironmentError(
            "No user_data_dir selected. Set CHROME_PROFILE_USER_DATA_DIR, or "
            "provide BETA_EXECUTABLE_PATH + BETA_PROFILE_USER_DATA_DIR "
            "(or CANARY_* equivalents)."
        )

    return {
        "user_data_dir": user_data_dir,
        "profile_name": profile_name,
        "chrome_path": chrome_path,
        "fixed_port": fixed_port,
    }


def profile_key(config: Dict[str, Any] = None) -> str:
    """
    Generate a stable key for cross-process locks.

    Based on absolute user_data_dir + profile_name.

    Args:
        config: Configuration dictionary (if None, will call get_env_config())

    Returns:
        SHA256 hex digest of the normalized profile path

    Raises:
        EnvironmentError: If user_data_dir is missing/blank
        FileNotFoundError: If CHROME_PROFILE_STRICT=1 and dir doesn't exist
    """
    if config is None:
        config = get_env_config()

    user_data_dir = (config.get("user_data_dir") or "").strip()
    profile_name = (config.get("profile_name") or "Default").strip() or "Default"

    if not user_data_dir:
        raise EnvironmentError(
            "CHROME_PROFILE_USER_DATA_DIR is required and cannot be empty."
        )

    strict = os.getenv("CHROME_PROFILE_STRICT", "0") == "1"
    p = Path(user_data_dir)
    if strict and not p.exists():
        raise FileNotFoundError(f"user_data_dir does not exist: {p}")

    # Normalize to a stable absolute string
    try:
        user_data_dir = str(p.resolve())
    except Exception:
        user_data_dir = str(p.absolute())

    raw = f"{user_data_dir}|{profile_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "get_env_config",
    "profile_key",
]
```

**File:** `src/mcp_browser_use/config/paths.py` (NEW)
```python
"""
Path resolution for locks, logs, and other filesystem resources.
"""

import os
from pathlib import Path
from typing import Dict, Any


_DEFAULT_LOCK_DIR = None


def get_lock_dir() -> str:
    """
    Get the lock directory path.

    Uses MCP_BROWSER_LOCK_DIR env var if set, otherwise uses:
        <repo_root>/tmp/mcp_locks

    The directory is created if it doesn't exist.

    Returns:
        Absolute path to lock directory
    """
    global _DEFAULT_LOCK_DIR

    if _DEFAULT_LOCK_DIR is None:
        # Calculate default: <repo_root>/tmp/mcp_locks
        repo_root = Path(__file__).parent.parent.parent.parent
        _DEFAULT_LOCK_DIR = str(repo_root / "tmp" / "mcp_locks")

    lock_dir = os.getenv("MCP_BROWSER_LOCK_DIR") or _DEFAULT_LOCK_DIR

    # Ensure directory exists
    Path(lock_dir).mkdir(parents=True, exist_ok=True)

    return lock_dir


__all__ = [
    "get_lock_dir",
]
```

#### Task 2.4: Update helpers.py to Use Context (Backwards Compatibility)
**File:** `src/mcp_browser_use/helpers.py`

Add at the top (after existing imports, around line 40):
```python
#region Context Integration (Phase 2)
# Import new modules
from .context import get_context, reset_context, BrowserContext
from .constants import (
    ACTION_LOCK_TTL_SECS as _ACTION_LOCK_TTL_SECS,
    ACTION_LOCK_WAIT_SECS as _ACTION_LOCK_WAIT_SECS,
    FILE_MUTEX_STALE_SECS as _FILE_MUTEX_STALE_SECS,
    WINDOW_REGISTRY_STALE_THRESHOLD as _WINDOW_REGISTRY_STALE_THRESHOLD,
    MAX_SNAPSHOT_CHARS as _MAX_SNAPSHOT_CHARS,
    START_LOCK_WAIT_SEC as _START_LOCK_WAIT_SEC,
    RENDEZVOUS_TTL_SEC as _RENDEZVOUS_TTL_SEC,
    ALLOW_ATTACH_ANY as _ALLOW_ATTACH_ANY,
)
from .config.environment import get_env_config, profile_key
from .config.paths import get_lock_dir

# Re-export for backwards compatibility
__all__ = ['get_context', 'reset_context', 'BrowserContext'] + __all__
#endregion
```

Replace the existing constants (lines 62-192) with backwards-compatible accessors:
```python
#region Constants (Backwards Compatible - delegates to constants.py)
# These now delegate to constants.py but maintain the old API
ACTION_LOCK_TTL_SECS = _ACTION_LOCK_TTL_SECS
ACTION_LOCK_WAIT_SECS = _ACTION_LOCK_WAIT_SECS
FILE_MUTEX_STALE_SECS = _FILE_MUTEX_STALE_SECS
WINDOW_REGISTRY_STALE_THRESHOLD = _WINDOW_REGISTRY_STALE_THRESHOLD
MAX_SNAPSHOT_CHARS = _MAX_SNAPSHOT_CHARS
START_LOCK_WAIT_SEC = _START_LOCK_WAIT_SEC
RENDEZVOUS_TTL_SEC = _RENDEZVOUS_TTL_SEC
ALLOW_ATTACH_ANY = _ALLOW_ATTACH_ANY
#endregion

#region Globals (Backwards Compatible - delegates to context)
# These maintain the old global variable API but delegate to context
# DEPRECATED: Use get_context() instead

def _sync_from_context():
    """Sync module globals from context (for backwards compatibility)."""
    ctx = get_context()
    global DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, MY_TAG, TARGET_ID, WINDOW_ID, LOCK_DIR
    DRIVER = ctx.driver
    DEBUGGER_HOST = ctx.debugger_host
    DEBUGGER_PORT = ctx.debugger_port
    MY_TAG = ctx.process_tag
    TARGET_ID = ctx.target_id
    WINDOW_ID = ctx.window_id
    LOCK_DIR = ctx.lock_dir

def _sync_to_context():
    """Sync context from module globals (for backwards compatibility)."""
    ctx = get_context()
    global DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, MY_TAG, TARGET_ID, WINDOW_ID
    ctx.driver = DRIVER
    ctx.debugger_host = DEBUGGER_HOST
    ctx.debugger_port = DEBUGGER_PORT
    ctx.process_tag = MY_TAG
    ctx.target_id = TARGET_ID
    ctx.window_id = WINDOW_ID

# Initialize globals from context
DRIVER = None
DEBUGGER_HOST = None
DEBUGGER_PORT = None
MY_TAG = None
TARGET_ID = None
WINDOW_ID = None
LOCK_DIR = get_lock_dir()
MCP_INTRA_PROCESS_LOCK = None

# Sync from context
_sync_from_context()
#endregion
```

Remove the old `get_env_config()` and `profile_key()` functions (lines 68-162) since they're now in config/environment.py.

#### Task 2.5: Test New Modules
```bash
# Test imports
python -c "
from mcp_browser_use.constants import *
from mcp_browser_use.context import get_context, reset_context
from mcp_browser_use.config import get_env_config, profile_key, get_lock_dir
print('✓ All new modules import successfully')
"

# Test context lifecycle
python -c "
from mcp_browser_use.context import get_context, reset_context

reset_context()
ctx1 = get_context()
ctx2 = get_context()
assert ctx1 is ctx2, 'Context should be singleton'
assert ctx1.driver is None, 'Driver should start as None'
print('✓ Context singleton works')
"

# Test backwards compatibility
python -c "
import mcp_browser_use.helpers as helpers
assert helpers.ACTION_LOCK_TTL_SECS is not None
assert helpers.get_env_config is not None
print('✓ Backwards compatibility maintained')
"
```

#### Task 2.6: Commit & Push Foundation
```bash
git add src/mcp_browser_use/constants.py
git add src/mcp_browser_use/context.py
git add src/mcp_browser_use/config/
git add src/mcp_browser_use/helpers.py
git commit -m "feat(core): Add BrowserContext and config modules

- Add constants.py: Extract constants to break circular deps
- Add context.py: BrowserContext class for state management
- Add config/environment.py: Configuration management
- Add config/paths.py: Path resolution
- Update helpers.py: Maintain backwards compatibility

BREAKING: None (backwards compatible via helpers.py delegation)
UNBLOCKS: Developers B & C can now proceed
Refs: REFACTOR-002"

git push origin refactor/foundation-state
```

**🚀 UNBLOCK POINT:** Notify Developers B & C that foundation is ready.

---

## **WEEK 2: Days 6-10**

### **Day 6-8: Update Locking Modules to Use Constants**

Update all locking modules to import from constants.py instead of helpers.py.

#### Task 3.1: Update action_lock.py
**File:** `src/mcp_browser_use/locking/action_lock.py`

Replace imports (lines 54, 167):
```python
# OLD
from ..helpers import FILE_MUTEX_STALE_SECS, ACTION_LOCK_WAIT_SECS
from ..helpers import ACTION_LOCK_TTL_SECS, ACTION_LOCK_WAIT_SECS

# NEW
from ..constants import (
    FILE_MUTEX_STALE_SECS,
    ACTION_LOCK_WAIT_SECS,
    ACTION_LOCK_TTL_SECS,
)
```

#### Task 3.2: Update file_mutex.py
**File:** `src/mcp_browser_use/locking/file_mutex.py`

Check if it imports constants from helpers. If so, update:
```python
from ..constants import FILE_MUTEX_STALE_SECS
```

#### Task 3.3: Update window_registry.py
**File:** `src/mcp_browser_use/locking/window_registry.py`

Update imports:
```python
from ..constants import WINDOW_REGISTRY_STALE_THRESHOLD
```

#### Task 3.4: Test Locking Modules
```bash
python -c "
from mcp_browser_use.locking.action_lock import get_intra_process_lock
from mcp_browser_use.locking.file_mutex import _file_mutex
from mcp_browser_use.locking.window_registry import _read_window_registry
print('✓ All locking modules import successfully')
"
```

#### Task 3.5: Commit
```bash
git add src/mcp_browser_use/locking/
git commit -m "refactor(locking): Use constants.py instead of helpers

- Update action_lock.py to import from constants
- Update file_mutex.py to import from constants
- Update window_registry.py to import from constants
- Breaks circular dependency: locking <-> helpers

BREAKING: None (internal imports only)
Refs: REFACTOR-003"

git push origin refactor/foundation-state
```

---

### **Day 9-10: Update Decorators to Use Constants & Context**

#### Task 4.1: Update decorators/locking.py
**File:** `src/mcp_browser_use/decorators/locking.py`

Update imports (around line 86-92):
```python
# OLD
from mcp_browser_use.helpers import (
    get_intra_process_lock,
    ensure_process_tag,
    _acquire_action_lock_or_error,
    _renew_action_lock,
    ACTION_LOCK_TTL_SECS,
)

# NEW
from ..constants import ACTION_LOCK_TTL_SECS
from ..context import get_context
# Keep these from helpers for now (will be migrated by Dev B)
from ..locking.action_lock import (
    get_intra_process_lock as _get_intra_process_lock,
    _acquire_action_lock_or_error,
    _renew_action_lock,
)
```

Update the function to use context:
```python
async def wrapper(*args, **kwargs):
    # Early config validation
    config_error = _validate_config_or_error()
    if config_error:
        return config_error

    # Get context
    ctx = get_context()

    # Ensure process tag
    if ctx.process_tag is None:
        from ..browser.process import make_process_tag
        ctx.process_tag = make_process_tag()

    owner = ctx.process_tag

    # Use context's lock
    lock = ctx.get_intra_process_lock()
    async with lock:
        # ... rest of function
```

#### Task 4.2: Update decorators/ensure.py
**File:** `src/mcp_browser_use/decorators/ensure.py`

```python
# At top of file
from ..context import get_context

def ensure_driver_ready(_func=None, *, include_snapshot=False, include_diagnostics=False):
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                ctx = get_context()

                # Check if driver is initialized
                if not ctx.is_driver_initialized():
                    payload = {
                        "ok": False,
                        "error": "browser_not_started",
                        "message": "Browser session not started. Please call 'start_browser' first."
                    }
                    if include_snapshot:
                        payload["snapshot"] = {"url": None, "title": None, "html": "", "truncated": False}
                    if include_diagnostics:
                        try:
                            from ..utils.diagnostics import collect_diagnostics
                            payload["diagnostics"] = collect_diagnostics(None, None, ctx.config)
                        except Exception:
                            pass
                    return json.dumps(payload)

                # Ensure we have a valid window
                try:
                    from ..browser.driver import _ensure_singleton_window
                    _ensure_singleton_window(ctx.driver)
                except Exception:
                    payload = {
                        "ok": False,
                        "error": "browser_window_lost",
                        "message": "Browser window was lost. Please call 'start_browser' to create a new session."
                    }
                    if include_snapshot:
                        payload["snapshot"] = {"url": None, "title": None, "html": "", "truncated": False}
                    return json.dumps(payload)

                return await fn(*args, **kwargs)
            return wrapper
        # ... sync version similar
```

#### Task 4.3: Test Decorators
```bash
python -c "
from mcp_browser_use.decorators import (
    ensure_driver_ready,
    exclusive_browser_access,
    tool_envelope,
)
print('✓ All decorators import successfully')
"
```

#### Task 4.4: Commit
```bash
git add src/mcp_browser_use/decorators/
git commit -m "refactor(decorators): Use constants and context

- Update locking.py to use constants and context
- Update ensure.py to use context instead of helpers globals
- Removes imports from helpers, breaking circular dependency

BREAKING: None (internal implementation only)
Refs: REFACTOR-004"

git push origin refactor/foundation-state
```

---

## **WEEK 2-3: Days 11-14**

### **Day 11-14: Integration Testing & Documentation**

#### Task 5.1: Create Validation Script
**File:** `scripts/validate_foundation.py` (NEW)

```python
#!/usr/bin/env python3
"""
Validate Developer A's foundation changes.

Tests:
1. All new modules import without errors
2. No circular dependencies
3. Backwards compatibility maintained
4. Context singleton works correctly
"""

import sys
import importlib
from pathlib import Path


def test_imports():
    """Test that all new modules import successfully."""
    print("Testing imports...")

    modules = [
        "mcp_browser_use.constants",
        "mcp_browser_use.context",
        "mcp_browser_use.config",
        "mcp_browser_use.config.environment",
        "mcp_browser_use.config.paths",
        "mcp_browser_use.browser.driver",
        "mcp_browser_use.locking.action_lock",
        "mcp_browser_use.decorators.locking",
        "mcp_browser_use.decorators.ensure",
    ]

    for module_name in modules:
        try:
            importlib.import_module(module_name)
            print(f"  ✓ {module_name}")
        except Exception as e:
            print(f"  ✗ {module_name}: {e}")
            return False

    return True


def test_context_singleton():
    """Test context singleton pattern."""
    print("\nTesting context singleton...")

    from mcp_browser_use.context import get_context, reset_context

    reset_context()
    ctx1 = get_context()
    ctx2 = get_context()

    if ctx1 is not ctx2:
        print("  ✗ Context is not singleton")
        return False

    print("  ✓ Context singleton works")
    return True


def test_backwards_compatibility():
    """Test that old helpers.py API still works."""
    print("\nTesting backwards compatibility...")

    import mcp_browser_use.helpers as helpers

    # Test constants
    if helpers.ACTION_LOCK_TTL_SECS is None:
        print("  ✗ ACTION_LOCK_TTL_SECS not available")
        return False

    # Test functions
    if not hasattr(helpers, 'get_env_config'):
        print("  ✗ get_env_config not available")
        return False

    if not hasattr(helpers, 'profile_key'):
        print("  ✗ profile_key not available")
        return False

    print("  ✓ Backwards compatibility maintained")
    return True


def test_no_circular_imports():
    """Test that circular imports are resolved."""
    print("\nTesting for circular dependencies...")

    # Try importing in different orders
    import mcp_browser_use.constants
    import mcp_browser_use.locking.action_lock
    import mcp_browser_use.decorators.locking

    # If we get here, no circular imports
    print("  ✓ No circular import errors detected")
    return True


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("DEVELOPER A FOUNDATION VALIDATION")
    print("=" * 60)

    tests = [
        test_imports,
        test_context_singleton,
        test_backwards_compatibility,
        test_no_circular_imports,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 60)

    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

Run validation:
```bash
python scripts/validate_foundation.py
```

#### Task 5.2: Create State Contract Documentation
**File:** `docs/STATE_CONTRACT.md` (NEW)

```markdown
# Browser State Contract

**Author:** Developer A
**Date:** [Current Date]
**Version:** 2.0 (Post-Context Refactoring)

## Overview

Browser state is now managed through `BrowserContext` instead of module-level globals.

## BrowserContext Attributes

| Attribute | Type | Purpose | Set By | Read By |
|-----------|------|---------|--------|---------|
| `driver` | `webdriver.Chrome | None` | Selenium WebDriver instance | `browser.driver._ensure_driver()` | All modules |
| `debugger_host` | `str | None` | Chrome DevTools host | `browser.chrome.start_or_attach_chrome()` | `browser.driver` |
| `debugger_port` | `int | None` | Chrome DevTools port | `browser.chrome.start_or_attach_chrome()` | `browser.driver` |
| `target_id` | `str | None` | CDP target ID for window | `browser.driver._ensure_singleton_window()` | `browser.driver`, `actions/*` |
| `window_id` | `int | None` | Chrome window ID | `browser.driver._ensure_singleton_window()` | `browser.driver` |
| `process_tag` | `str | None` | Unique process identifier | `browser.process.ensure_process_tag()` | `locking/*`, `decorators/*` |
| `config` | `dict` | Environment configuration | `config.environment.get_env_config()` | All modules |
| `lock_dir` | `str` | Lock file directory | `config.paths.get_lock_dir()` | `locking/*` |
| `intra_process_lock` | `asyncio.Lock | None` | Async lock for serialization | `context.get_intra_process_lock()` | `decorators/locking.py` |

## Lifecycle

### 1. Initialization
```python
from mcp_browser_use.context import get_context

ctx = get_context()
# At this point:
# - ctx.config is populated from environment
# - ctx.lock_dir is set
# - All other attributes are None
```

### 2. Browser Start
```python
# User calls: start_browser()
# Internal flow:
ctx = get_context()
chrome.start_or_attach_chrome()  # Sets debugger_host, debugger_port
driver._ensure_driver()           # Sets driver
driver._ensure_singleton_window() # Sets target_id, window_id
process.ensure_process_tag()      # Sets process_tag
```

### 3. Browser Operations
```python
# User calls: navigate_to_url(), click_element(), etc.
# Decorators ensure:
# - exclusive_browser_access: Acquires lock using process_tag
# - ensure_driver_ready: Validates driver is not None
```

### 4. Browser Close
```python
# User calls: close_browser()
ctx = get_context()
ctx.reset_window_state()  # Clears target_id, window_id
# driver remains for reuse
```

### 5. Full Teardown
```python
# User calls: force_close_all_chrome()
ctx = get_context()
ctx.driver.quit()
ctx.driver = None
ctx.debugger_host = None
ctx.debugger_port = None
ctx.reset_window_state()
```

## Thread Safety

⚠️ **IMPORTANT:** `BrowserContext` is **NOT** thread-safe by itself.

Thread safety is provided by:
- **Intra-process:** `exclusive_browser_access` decorator uses `ctx.intra_process_lock`
- **Inter-process:** File-based locks in `locking/action_lock.py`

## Migration from Globals

### Before (Old API)
```python
import mcp_browser_use.helpers as helpers

if helpers.DRIVER is None:
    helpers._ensure_driver()

driver = helpers.DRIVER
target_id = helpers.TARGET_ID
```

### After (New API)
```python
from mcp_browser_use.context import get_context
from mcp_browser_use.browser.driver import _ensure_driver

ctx = get_context()
if ctx.driver is None:
    _ensure_driver()

driver = ctx.driver
target_id = ctx.target_id
```

### Backwards Compatibility (Temporary)
```python
# helpers.py maintains global variables that sync with context
import mcp_browser_use.helpers as helpers

# This still works (but is deprecated):
driver = helpers.DRIVER
target_id = helpers.TARGET_ID
```

## Access Patterns by Module

### browser/driver.py
- **Reads:** `driver`, `debugger_host`, `debugger_port`, `target_id`, `window_id`
- **Writes:** `driver`, `target_id`, `window_id`

### decorators/locking.py
- **Reads:** `process_tag`, `intra_process_lock`
- **Writes:** `process_tag` (if None)

### actions/*.py
- **Reads:** `driver`, `target_id`
- **Writes:** None

### tools/*.py
- **Reads:** `driver`, `process_tag`, `debugger_host`, `debugger_port`
- **Writes:** None (delegates to other modules)

## Constants

All constants moved to `constants.py`:
- `ACTION_LOCK_TTL_SECS`
- `ACTION_LOCK_WAIT_SECS`
- `FILE_MUTEX_STALE_SECS`
- `WINDOW_REGISTRY_STALE_THRESHOLD`
- `MAX_SNAPSHOT_CHARS`
- `START_LOCK_WAIT_SEC`
- `RENDEZVOUS_TTL_SEC`
- `ALLOW_ATTACH_ANY`

## For Developers B & C

You can now safely:
1. Import from `mcp_browser_use.context` to access state
2. Import from `mcp_browser_use.constants` for configuration values
3. Import from `mcp_browser_use.config` for environment functions
4. Update your modules to use context instead of helpers globals

## Examples

See Developer B and Developer C instructions for migration patterns in specific modules.
```

#### Task 5.3: Commit Documentation
```bash
git add scripts/validate_foundation.py
git add docs/STATE_CONTRACT.md
git commit -m "docs: Add foundation validation and state contract

- Add validation script for foundation changes
- Add state contract documentation
- Documents context lifecycle and migration patterns

Refs: REFACTOR-005"

git push origin refactor/foundation-state
```

#### Task 5.4: Create Pull Request

Create PR with this description:

```markdown
## Foundation: Browser State Management Refactoring

### Summary
Introduces `BrowserContext` for centralized state management and breaks circular dependencies by extracting constants and configuration.

### Changes
1. **Fixed broken driver.py** - Added missing imports and resolved undefined globals
2. **Created BrowserContext** - Single source of truth for browser state
3. **Extracted constants** - Moved to `constants.py` to break circular dependencies
4. **Extracted configuration** - New `config/` module for environment management
5. **Updated locking modules** - Now import from `constants.py`
6. **Updated decorators** - Now use context and constants

### Backwards Compatibility
✅ **100% backwards compatible** - helpers.py maintains old API via delegation

### Breaking Changes
None - all changes are internal

### Testing
- ✅ All new modules import without errors
- ✅ Context singleton pattern validated
- ✅ Backwards compatibility verified
- ✅ No circular import errors

### Unblocks
- Developer B: Can now update browser/ and actions/ modules
- Developer C: Can now update tools/ modules

### Migration Path
See `docs/STATE_CONTRACT.md` for detailed migration guide.

### Reviewers
@developer-b @developer-c @tech-lead

### Validation
```bash
python scripts/validate_foundation.py
```
```

---

## **Coordination with Other Developers**

### Sync Points

**After Day 2 (driver.py fix):**
- Create PR immediately
- Notify Developers B & C
- They are blocked until this merges

**After Day 5 (BrowserContext):**
- Push to origin
- Notify Developers B & C that foundation is ready
- They can start their work

**After Day 10 (Decorators):**
- Final validation
- Create PR for full foundation
- Developers B & C should wait for final PR approval

### Communication

Use this Slack message template:

```
🚀 **Foundation Update - Day [X]**

**Status:** [In Progress / Complete / Blocked]

**Completed:**
- [List completed tasks]

**Next:**
- [List next tasks]

**Blockers:**
- [List any blockers]

**Impact on Dev B:** [None / Ready to start / Waiting for...]
**Impact on Dev C:** [None / Ready to start / Waiting for...]

**Branch:** `refactor/foundation-state`
**Commits:** [Number] commits, [Number] files changed
```

### Code Review

You'll review:
- Developer B's browser/ and actions/ updates
- Developer C's tools/ and decorators/ updates

Look for:
- Proper use of `get_context()` instead of globals
- Imports from `constants.py` instead of `helpers.py`
- No new circular dependencies

---

## **Success Criteria**

By end of Day 14, you should have:

- [x] driver.py imports without errors
- [x] BrowserContext created and tested
- [x] constants.py created
- [x] config/ module created
- [x] Locking modules updated
- [x] Decorators updated
- [x] Validation script passing
- [x] Documentation complete
- [x] PR approved and merged
- [x] Developers B & C unblocked

---

## **Troubleshooting**

### Import Errors
If you get import errors, check:
1. All `__init__.py` files exist
2. Imports use relative imports within package
3. Run from repo root

### Test Failures
If validation fails:
1. Check git status - ensure all files committed
2. Try in clean virtual environment
3. Check for typos in module names

### Merge Conflicts
Your branch should merge cleanly. If conflicts:
1. Your work is foundational, so you have priority
2. Ask other developers to rebase on your changes
3. Don't compromise your architecture to avoid conflicts

---

## **Daily Checklist**

### Day 1-2
- [ ] Add missing imports to driver.py
- [ ] Fix all undefined global references
- [ ] Test imports
- [ ] Commit & push
- [ ] Create emergency PR
- [ ] Notify team

### Day 3-5
- [ ] Create constants.py
- [ ] Create context.py
- [ ] Create config/ module
- [ ] Update helpers.py for backwards compat
- [ ] Test all new modules
- [ ] Commit & push
- [ ] Notify Dev B & C they can start

### Day 6-8
- [ ] Update locking/action_lock.py
- [ ] Update locking/file_mutex.py
- [ ] Update locking/window_registry.py
- [ ] Test locking modules
- [ ] Commit & push

### Day 9-10
- [ ] Update decorators/locking.py
- [ ] Update decorators/ensure.py
- [ ] Test decorators
- [ ] Commit & push

### Day 11-14
- [ ] Create validation script
- [ ] Run validation
- [ ] Fix any issues
- [ ] Create state contract docs
- [ ] Create final PR
- [ ] Code review with team
- [ ] Merge after approval

---

## **Questions?**

Contact:
- **Architecture questions:** Tech Lead
- **Merge conflicts:** Developer B or C
- **Environment issues:** DevOps

**Remember:** Your work is the foundation. Quality over speed. 🏗️
