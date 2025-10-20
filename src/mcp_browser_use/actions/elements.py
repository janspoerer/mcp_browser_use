"""Element finding and interaction."""

import time
from typing import Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

from ..context import get_context


def _wait_clickable_element(el, driver, timeout: float = 10.0):
    """Wait for an element to be clickable (displayed and enabled)."""
    WebDriverWait(driver, timeout).until(lambda d: el.is_displayed() and el.is_enabled())
    return el

def get_by_selector(selector_type: str):
    return {
        'css': By.CSS_SELECTOR,
        'xpath': By.XPATH,
        'id': By.ID,
        'name': By.NAME,
        'tag': By.TAG_NAME,
        'class': By.CLASS_NAME,
        'link_text': By.LINK_TEXT,
        'partial_link_text': By.PARTIAL_LINK_TEXT
    }.get(selector_type.lower())


def find_element(
    driver: webdriver.Chrome,
    selector: str,
    selector_type: str = "css",
    timeout: int = 10,
    visible_only: bool = False,
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
    shadow_root_selector: Optional[str] = None,
    shadow_root_selector_type: str = "css",
    stay_in_context: bool = False,  # <-- added
):
    """
    Locate an element with optional iframe and shadow DOM support.

    - If stay_in_context is True and an iframe was entered, we do NOT switch back
      to default_content. This is needed for actions (click/type) inside iframes.
    - If stay_in_context is False (default), we restore to default_content() so
      callers aren't left in an iframe.
    """
    original_driver = driver
    switched_iframe = False
    try:
        if iframe_selector:
            by_iframe = get_by_selector(iframe_selector_type)
            if not by_iframe:
                raise ValueError(f"Unsupported iframe selector type: {iframe_selector_type}")
            iframe = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by_iframe, iframe_selector))
            )
            driver.switch_to.frame(iframe)
            switched_iframe = True

        search_context = driver
        if shadow_root_selector:
            by_shadow_host = get_by_selector(shadow_root_selector_type)
            if not by_shadow_host:
                raise ValueError(f"Unsupported shadow root selector type: {shadow_root_selector_type}")
            shadow_host = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by_shadow_host, shadow_root_selector))
            )
            shadow_root = shadow_host.shadow_root
            search_context = shadow_root

        by_selector = get_by_selector(selector_type)
        if not by_selector:
            raise ValueError(f"Unsupported selector type: {selector_type}")

        wait = WebDriverWait(search_context, timeout)
        if visible_only:
            element = wait.until(EC.visibility_of_element_located((by_selector, selector)))
        else:
            element = wait.until(EC.presence_of_element_located((by_selector, selector)))

        return element

    except TimeoutException:
        if switched_iframe and not stay_in_context:
            try:
                original_driver.switch_to.default_content()
            except Exception:
                pass
        raise
    except Exception:
        if switched_iframe and not stay_in_context:
            try:
                original_driver.switch_to.default_content()
            except Exception:
                pass
        raise
    finally:
        if switched_iframe and not stay_in_context:
            try:
                original_driver.switch_to.default_content()
            except Exception:
                pass



def click_element(selector: str, selector_type: str = "css") -> dict:
    """Click an element."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        el = find_element(driver=ctx.driver, selector=selector, selector_type=selector_type, timeout=10.0)
        if not el:
            return {"ok": False, "error": "Element not found"}
        el.click()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def fill_text(selector: str, text: str, selector_type: str = "css") -> dict:
    """Fill text into an element."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        el = find_element(driver=ctx.driver, selector=selector, selector_type=selector_type, timeout=10.0)
        if not el:
            return {"ok": False, "error": "Element not found"}
        el.clear()
        el.send_keys(text)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def debug_element(selector: str, selector_type: str = "css") -> dict:
    """Debug element information."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        el = find_element(driver=ctx.driver, selector=selector, selector_type=selector_type, timeout=5.0)
        if not el:
            return {"ok": False, "error": "Element not found"}
        return {
            "ok": True,
            "tag": el.tag_name,
            "text": el.text,
            "visible": el.is_displayed(),
            "enabled": el.is_enabled(),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = [
    'find_element',
    '_wait_clickable_element',
    'get_by_selector',
    'click_element',
    'fill_text',
    'debug_element',
]
