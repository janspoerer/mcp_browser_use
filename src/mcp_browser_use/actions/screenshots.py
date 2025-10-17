"""Screenshot and page snapshot functionality."""

import io
import base64
from typing import Optional


def _make_page_snapshot(
    max_snapshot_chars: Optional[int] = None,   # ignored (legacy)
    aggressive_cleaning: bool = False,          # ignored (legacy)
    offset_chars: int = 0,                      # ignored (legacy)
) -> dict:
    """
    Capture the raw page snapshot (no cleaning, no truncation).
    Returns a dict: {"url": str|None, "title": str|None, "html": str}
    """
    url = None
    title = None
    html = ""
    try:
        if DRIVER is not None:
            try:
                DRIVER.switch_to.default_content()
            except Exception:
                pass
            try:
                url = DRIVER.current_url
            except Exception:
                url = None
            try:
                title = DRIVER.title
            except Exception:
                title = None

            # Ensure DOM is ready, then apply configurable settle
            try:
                _wait_document_ready(timeout=5.0)
            except Exception:
                pass
            try:
                settle_ms = int(os.getenv("SNAPSHOT_SETTLE_MS", "200") or "0")
                if settle_ms > 0:
                    time.sleep(settle_ms / 1000.0)
            except Exception:
                pass

            # Prefer outerHTML; fall back to page_source
            try:
                html = DRIVER.execute_script("return document.documentElement.outerHTML") or ""
                if not html:
                    html = DRIVER.page_source or ""
            except Exception:
                try:
                    html = DRIVER.page_source or ""
                except Exception:
                    html = ""
    except Exception:
        pass
    return {"url": url, "title": title, "html": html}
#endregion

#region Tool helpers (clickable wait using a lambda on the element)


def take_screenshot(filename: Optional[str] = None) -> dict:
    """Take a screenshot (placeholder)"""
    from ..helpers import DRIVER
    if not DRIVER:
        return {"ok": False, "error": "No driver available"}
    try:
        if filename:
            DRIVER.save_screenshot(filename)
            return {"ok": True, "path": filename}
        else:
            png_data = DRIVER.get_screenshot_as_png()
            b64 = base64.b64encode(png_data).decode('utf-8')
            return {"ok": True, "data": b64}
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = [
    '_make_page_snapshot',
    'take_screenshot',
]
