"""WebDriver creation and window management."""

import os
import time
from typing import Optional
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchWindowException,
    WebDriverException,
)

import logging
logger = logging.getLogger(__name__)

# Global driver state
_global_driver: Optional[webdriver.Chrome] = None
_global_target_id: Optional[str] = None
_global_window_id: Optional[int] = None


def _ensure_driver() -> None:
    """Attach Selenium to the debuggable Chrome instance (headed by default)."""
    global DRIVER
    if DRIVER is not None:
        return

    cfg = get_env_config()
    _ensure_debugger_ready(cfg)  # allow full wait (e.g., 30s via env)
    if not (DEBUGGER_HOST and DEBUGGER_PORT):
        return  # caller will return driver_not_initialized

    # Use the shared factory so Chromedriver logs and options are consistent
    DRIVER = create_webdriver(DEBUGGER_HOST, DEBUGGER_PORT, cfg)

def ensure_process_tag() -> str:
    global MY_TAG
    if MY_TAG is None:
        MY_TAG = make_process_tag()
    return MY_TAG


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
    global TARGET_ID, WINDOW_ID

    # 0) If we already have a target, validate context and attempt recovery
    if TARGET_ID:
        # First validate we're in the correct window context
        if _validate_window_context(driver, TARGET_ID):
            return  # Already in correct window

        # Context validation failed - attempt recovery
        h = _handle_for_target(driver, TARGET_ID)
        if h:
            try:
                driver.switch_to.window(h)
                # Verify recovery succeeded
                if _validate_window_context(driver, TARGET_ID):
                    return
            except Exception:
                pass  # Recovery failed, will recreate window below

        # Window handle not found or recovery failed - clear target and recreate
        TARGET_ID = None
        WINDOW_ID = None

    # 1) First-time in this process or recovery failed: create a new real OS window for this agent
    if not TARGET_ID:
        # Cleanup orphaned windows from dead/stale processes before creating new window
        try:
            cleanup_orphaned_windows(driver)
        except Exception as e:
            logger.debug(f"Window cleanup failed (non-critical): {e}")
        try:
            win = driver.execute_cdp_cmd("Browser.createWindow", {"state": "normal"})
            if not isinstance(win, dict):
                raise RuntimeError(f"Browser.createWindow returned {win!r}")
            WINDOW_ID = win.get("windowId")
            TARGET_ID = win.get("targetId")

            if not TARGET_ID:
                # Fallback: ensure there is a page target tied to a new window
                t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
                if not isinstance(t, dict) or "targetId" not in t:
                    raise RuntimeError(f"Target.createTarget returned {t!r}")
                TARGET_ID = t["targetId"]
                if not WINDOW_ID:
                    try:
                        w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": TARGET_ID}) or {}
                        WINDOW_ID = w.get("windowId")
                    except Exception:
                        WINDOW_ID = None
        except Exception:
            # Last resort: create via Target API
            t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
            if not isinstance(t, dict) or "targetId" not in t:
                raise RuntimeError(f"Target.createTarget returned {t!r}")
            TARGET_ID = t["targetId"]
            try:
                w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": TARGET_ID}) or {}
                WINDOW_ID = w.get("windowId")
            except Exception:
                WINDOW_ID = None

    # 2) Map targetId -> Selenium handle (with brief retry)
    h = _handle_for_target(driver, TARGET_ID)
    if not h:
        for _ in range(20):  # ~1s
            time.sleep(0.05)
            h = _handle_for_target(driver, TARGET_ID)
            if h:
                break
    
    if h:
        driver.switch_to.window(h)
        # Final validation to ensure we're in the correct window
        if not _validate_window_context(driver, TARGET_ID):
            raise RuntimeError(f"Failed to establish correct window context for target {TARGET_ID}")

        # Register this window in the registry
        try:
            owner = ensure_process_tag()
            _register_window(owner, TARGET_ID, WINDOW_ID)
        except Exception as e:
            logger.debug(f"Window registration failed (non-critical): {e}")
    else:
        raise RuntimeError(f"Failed to find window handle for target {TARGET_ID}")


def _ensure_driver_and_window() -> None:
    global DRIVER, TARGET_ID
    _ensure_driver()
    if DRIVER is None:
        return
    _ensure_singleton_window(DRIVER)



def _close_extra_blank_windows_safe(driver, exclude_handles=None) -> int:
    exclude = set(exclude_handles or ())
    # Only operate within our own OS window
    own_window_id = WINDOW_ID
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
    """
    Close the singleton window (by targetId) without quitting Chrome.
    Resets TARGET_ID/WINDOW_ID so a subsequent start will create a new window.
    Also unregisters the window from the registry.
    """
    global DRIVER, TARGET_ID, WINDOW_ID
    if DRIVER is None or not TARGET_ID:
        return False

    closed = False
    try:
        DRIVER.execute_cdp_cmd("Target.closeTarget", {"targetId": TARGET_ID})
        closed = True
    except Exception:
        # Fallback: find Selenium handle for this target and close it
        try:
            h = _handle_for_target(DRIVER, TARGET_ID)
            if h:
                DRIVER.switch_to.window(h)
                DRIVER.close()
                closed = True
        except Exception:
            pass

    # Unregister from window registry
    if closed:
        try:
            owner = ensure_process_tag()
            _unregister_window(owner)
        except Exception as e:
            logger.debug(f"Window unregistration failed (non-critical): {e}")

    TARGET_ID = None
    WINDOW_ID = None
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
#endregion

#region Per-process window ownership

def _cleanup_own_blank_tabs(driver):
    handle = getattr(driver, "current_window_handle", None)
    try:
        _close_extra_blank_windows_safe(
            driver,
            exclude_handles={handle} if handle else None,
        )
    except Exception:
        pass
#endregion

#region Resilience: retries and DOM utils

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
]
