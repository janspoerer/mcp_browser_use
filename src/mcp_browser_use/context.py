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
        # Lazy initialization - import here to avoid circular dependencies
        try:
            from .config.environment import get_env_config
            from .config.paths import get_lock_dir

            _global_context = BrowserContext(
                config=get_env_config(),
                lock_dir=get_lock_dir(),
            )
        except Exception:
            # If config not available yet, create minimal context
            _global_context = BrowserContext()

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
