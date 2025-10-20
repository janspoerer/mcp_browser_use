"""Navigation and scrolling tool implementations."""

import json
import time
from selenium.webdriver.support.ui import WebDriverWait
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics
from ..actions.navigation import _wait_document_ready
from ..actions.screenshots import _make_page_snapshot


async def navigate_to_url(
    url: str,
    wait_for: str = "load",     # "load" or "complete"
    timeout_sec: int = 30,
) -> str:
    """Navigate to a URL and return JSON with a raw snapshot."""
    ctx = get_context()

    try:
        if not ctx.is_driver_initialized():
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        ctx.driver.get(url)

        # DOM readiness
        try:
            _wait_document_ready(timeout=min(max(timeout_sec, 0), 60))
        except Exception:
            pass

        if (wait_for or "load").lower() == "complete":
            try:
                WebDriverWait(ctx.driver, timeout_sec).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

        snapshot = _make_page_snapshot()
        return json.dumps({"ok": True, "action": "navigate", "url": url, "snapshot": snapshot})

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})


async def scroll(x: int, y: int) -> str:
    """
    Scroll the page by the specified pixel amounts.

    Args:
        x: Horizontal scroll amount in pixels (positive = right, negative = left)
        y: Vertical scroll amount in pixels (positive = down, negative = up)

    Returns:
        JSON string with ok status, action, scroll amounts, and page snapshot
    """
    ctx = get_context()

    try:
        if not ctx.is_driver_initialized():
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        ctx.driver.execute_script(f"window.scrollBy({int(x)}, {int(y)});")
        time.sleep(0.3)  # Brief pause to allow scroll to complete

        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": True,
            "action": "scroll",
            "x": int(x),
            "y": int(y),
            "snapshot": snapshot,
        })

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})


__all__ = ['navigate_to_url', 'scroll']
