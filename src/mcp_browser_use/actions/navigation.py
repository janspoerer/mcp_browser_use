"""Navigation and page interaction."""

import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ..context import get_context


def _wait_document_ready(timeout: float = 10.0):
    """Wait for document to be ready."""
    ctx = get_context()
    if not ctx.driver:
        return

    try:
        WebDriverWait(ctx.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )
    except Exception:
        # Not fatal
        pass


def navigate_to_url(url: str) -> dict:
    """Navigate to URL."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        ctx.driver.get(url)
        _wait_document_ready()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def wait_for_element(selector: str, timeout: float = 10.0) -> dict:
    """Wait for element to appear."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        from selenium.webdriver.common.by import By
        WebDriverWait(ctx.driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_current_page_meta() -> dict:
    """Get current page metadata."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        return {
            "ok": True,
            "url": ctx.driver.current_url,
            "title": ctx.driver.title,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = [
    '_wait_document_ready',
    'navigate_to_url',
    'wait_for_element',
    'get_current_page_meta',
]
