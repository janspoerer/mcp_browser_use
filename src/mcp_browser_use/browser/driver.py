"""WebDriver creation and window management."""

import os
import time
import shutil
import subprocess
from typing import Optional
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchWindowException,
    WebDriverException,
)

import logging
logger = logging.getLogger(__name__)

# Import context for state management
from ..context import get_context
from .devtools import _ensure_debugger_ready, _handle_for_target
from .process import make_process_tag, chromedriver_log_path
from ..locking.window_registry import (
    cleanup_orphaned_windows,
    _register_window,
    _unregister_window,
)


def _ensure_driver() -> None:
    """Attach Selenium to the debuggable Chrome instance (headed by default)."""
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


def ensure_process_tag() -> str:
    """Get or create process tag in context."""
    ctx = get_context()

    if ctx.process_tag is None:
        ctx.process_tag = make_process_tag()

    return ctx.process_tag


def _validate_window_context(driver: webdriver.Chrome, expected_target_id: str) -> bool:
    """
    Validate that the current window context matches the expected target.
    Returns True if validation passes, False otherwise.
    Handles NoSuchWindowException gracefully.
    """
    if not expected_target_id:
        return False

    try:
        # Check if current window handle exists and matches expected target
        current_handle = driver.current_window_handle
        if current_handle and current_handle.endswith(expected_target_id):
            return True

        # Double-check by getting target info via CDP
        try:
            info = driver.execute_cdp_cmd("Target.getTargetInfo", {}) or {}
            current_target = (info.get("targetInfo") or {}).get("targetId") or info.get("targetId")
            return current_target == expected_target_id
        except Exception:
            pass

        return False
    except Exception:
        # NoSuchWindowException or other window-related exceptions
        return False


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


def _ensure_driver_and_window() -> None:
    """Ensure both driver and window are ready."""
    _ensure_driver()

    ctx = get_context()
    if ctx.driver is None:
        return

    _ensure_singleton_window(ctx.driver)


def _close_extra_blank_windows_safe(driver, exclude_handles=None) -> int:
    """Close extra blank windows, only within our own OS window."""
    exclude = set(exclude_handles or ())

    ctx = get_context()
    own_window_id = ctx.window_id
    if own_window_id is None:
        return 0

    try:
        keep = driver.current_window_handle
    except Exception:
        keep = None

    closed = 0
    for h in list(getattr(driver, "window_handles", [])):
        if h in exclude or (keep and h == keep):
            continue
        try:
            driver.switch_to.window(h)
            # Map this handle -> targetId -> windowId
            info = driver.execute_cdp_cmd("Target.getTargetInfo", {}) or {}
            tid = (info.get("targetInfo") or {}).get("targetId") or info.get("targetId")
            if not tid:
                continue
            w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": tid}) or {}
            if w.get("windowId") != own_window_id:
                # Belongs to another agent's OS window; do not touch
                continue

            url = (driver.current_url or "").lower()
            title = (driver.title or "").strip()
            if url in ("about:blank", "chrome://newtab/") or (not url and not title):
                driver.close()
                closed += 1
        except Exception:
            continue

    # Restore our original window if it still exists
    if keep and keep in getattr(driver, "window_handles", []):
        try:
            driver.switch_to.window(keep)
        except Exception:
            pass
    return closed


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


def create_webdriver(debugger_host: str, debugger_port: int, config: dict) -> webdriver.Chrome:
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service as ChromeService

    options = Options()
    chrome_path = config.get("chrome_path")
    if chrome_path:
        options.binary_location = chrome_path
    options.add_experimental_option("debuggerAddress", f"{debugger_host}:{debugger_port}")

    # Handle differing Selenium versions that accept log_output vs. log_path
    log_file = chromedriver_log_path(config)
    try:
        service = ChromeService(log_output=log_file)  # newer Selenium
    except TypeError:
        service = ChromeService(log_path=log_file)    # older Selenium

    driver = webdriver.Chrome(service=service, options=options)
    return driver


def _cleanup_own_blank_tabs(driver):
    handle = getattr(driver, "current_window_handle", None)
    try:
        _close_extra_blank_windows_safe(
            driver,
            exclude_handles={handle} if handle else None,
        )
    except Exception:
        pass


def get_chromedriver_capability_version(driver: Optional[webdriver.Chrome] = None) -> Optional[str]:
    """
    Best effort Chromedriver version string.
    - If a driver is provided, prefer driver.capabilities['chromedriverVersion'].
    - Else, fall back to `chromedriver --version` if available in PATH.
    """
    try:
        if driver:
            v = driver.capabilities.get("chromedriverVersion")
            if isinstance(v, str) and v:
                # Typically like "114.0.5735.90 (some hash)"
                return v.split(" ")[0]
        path = shutil.which("chromedriver")
        if path:
            out = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT).decode().strip()
            return out
    except Exception:
        pass
    return None


__all__ = [
    'create_webdriver',
    '_ensure_driver',
    '_ensure_driver_and_window',
    '_ensure_singleton_window',
    'close_singleton_window',
    '_cleanup_own_blank_tabs',
    '_close_extra_blank_windows_safe',
    'get_chromedriver_capability_version',
    '_validate_window_context',
    'ensure_process_tag',
]
