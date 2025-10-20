"""Navigation and scrolling tool implementations."""

import json
import time
from selenium.webdriver.support.ui import WebDriverWait
import mcp_browser_use.helpers as helpers
from mcp_browser_use.utils.diagnostics import collect_diagnostics


async def navigate_to_url(
    url: str,
    wait_for: str = "load",     # "load" or "complete"
    timeout_sec: int = 30,
) -> str:
    """
    Navigate to a URL and return JSON with a raw snapshot.
    """
    try:
        if helpers.DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        helpers.DRIVER.get(url)

        # DOM readiness
        try:
            helpers._wait_document_ready(timeout=min(max(timeout_sec, 0), 60))
        except Exception:
            pass

        if (wait_for or "load").lower() == "complete":
            try:
                WebDriverWait(helpers.DRIVER, timeout_sec).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

        snapshot = helpers._make_page_snapshot()
        return json.dumps({"ok": True, "action": "navigate", "url": url, "snapshot": snapshot})
    except Exception as e:
        diag = collect_diagnostics(helpers.DRIVER, e, helpers.get_env_config())
        snapshot = helpers._make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})


async def scroll(x: int, y: int, max_snapshot_chars=0, aggressive_cleaning=False, offset_chars=0) -> str:
    """
    Scroll the page by the specified pixel amounts.

    Args:
        x: Horizontal scroll amount in pixels (positive = right, negative = left)
        y: Vertical scroll amount in pixels (positive = down, negative = up)
        max_snapshot_chars: Maximum HTML characters to return (default: 0 to save context)
        aggressive_cleaning: Whether to apply aggressive HTML cleaning
        offset_chars: Number of characters to skip from start of HTML (default: 0)

    Returns:
        JSON string with ok status, action, scroll amounts, and page snapshot
    """
    try:
        if helpers.DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        helpers.DRIVER.execute_script(f"window.scrollBy({int(x)}, {int(y)});")
        time.sleep(0.3)  # Brief pause to allow scroll to complete

        snapshot = helpers._make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({
            "ok": True,
            "action": "scroll",
            "x": int(x),
            "y": int(y),
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(helpers.DRIVER, e, helpers.get_env_config())
        snapshot = helpers._make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})


__all__ = ['navigate_to_url', 'scroll']
