"""Screenshot and page snapshot functionality."""

import os
import time
import io
import base64
from typing import Optional

from ..context import get_context


def _make_page_snapshot() -> dict:
    """
    Capture the raw page snapshot (no cleaning, no truncation).
    Returns a dict: {"url": str|None, "title": str|None, "html": str}
    """
    from .navigation import _wait_document_ready

    ctx = get_context()
    url = None
    title = None
    html = ""
    try:
        if ctx.driver is not None:
            try:
                ctx.driver.switch_to.default_content()
            except Exception:
                pass
            try:
                url = ctx.driver.current_url
            except Exception:
                url = None
            try:
                title = ctx.driver.title
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
                html = ctx.driver.execute_script("return document.documentElement.outerHTML") or ""
                if not html:
                    html = ctx.driver.page_source or ""
            except Exception:
                try:
                    html = ctx.driver.page_source or ""
                except Exception:
                    html = ""
    except Exception:
        pass
    return {"url": url, "title": title, "html": html}


def take_screenshot(filename: Optional[str] = None) -> dict:
    """Take a screenshot."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        if filename:
            ctx.driver.save_screenshot(filename)
            return {"ok": True, "path": filename}
        else:
            png_data = ctx.driver.get_screenshot_as_png()
            b64 = base64.b64encode(png_data).decode('utf-8')
            return {"ok": True, "data": b64}
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = [
    '_make_page_snapshot',
    'take_screenshot',
]
