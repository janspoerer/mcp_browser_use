"""Element interaction tool implementations."""

import json
import time
from typing import Optional
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics
from ..actions.elements import find_element, _wait_clickable_element
from ..actions.navigation import _wait_document_ready
from ..actions.screenshots import _make_page_snapshot
from ..utils.retry import retry_op


async def fill_text(
    selector,
    text,
    selector_type,
    clear_first,
    timeout,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_snapshot_chars=5000,
    aggressive_cleaning=False,
    offset_chars=0,
):
    """Fill text into an element."""
    ctx = get_context()

    try:
        el = retry_op(op=lambda: find_element(
            driver=ctx.driver,
            selector=selector,
            selector_type=selector_type,
            timeout=int(timeout),
            visible_only=True,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
            shadow_root_selector=shadow_root_selector,
            shadow_root_selector_type=shadow_root_selector_type,
            stay_in_context=True,
        ))

        if clear_first:
            try:
                el.clear()
            except Exception:
                pass
        el.send_keys(text)
        _wait_document_ready(timeout=5.0)

        snapshot = _make_page_snapshot(
            max_snapshot_chars=max_snapshot_chars,
            aggressive_cleaning=aggressive_cleaning,
            offset_chars=offset_chars
        )
        return json.dumps({"ok": True, "action": "fill_text", "selector": selector, "snapshot": snapshot})

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        snapshot = _make_page_snapshot(
            max_snapshot_chars=max_snapshot_chars,
            aggressive_cleaning=aggressive_cleaning,
            offset_chars=offset_chars
        )
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

    finally:
        try:
            if ctx.is_driver_initialized():
                ctx.driver.switch_to.default_content()
        except Exception:
            pass

async def click_element(
    selector,
    selector_type,
    timeout,
    force_js,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_snapshot_chars=5000,
    aggressive_cleaning=False,
    offset_chars=0,
) -> str:
    """Click an element."""
    ctx = get_context()

    try:
        el = retry_op(op=lambda: find_element(
            driver=ctx.driver,
            selector=selector,
            selector_type=selector_type,
            timeout=int(timeout),
            visible_only=True,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
            shadow_root_selector=shadow_root_selector,
            shadow_root_selector_type=shadow_root_selector_type,
            stay_in_context=True,
        ))

        _wait_clickable_element(el=el, driver=ctx.driver, timeout=timeout)

        if force_js:
            ctx.driver.execute_script("arguments[0].click();", el)
        else:
            try:
                el.click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                el = retry_op(op=lambda: find_element(
                    driver=ctx.driver,
                    selector=selector,
                    selector_type=selector_type,
                    timeout=int(timeout),
                    visible_only=True,
                    iframe_selector=iframe_selector,
                    iframe_selector_type=iframe_selector_type,
                    shadow_root_selector=shadow_root_selector,
                    shadow_root_selector_type=shadow_root_selector_type,
                    stay_in_context=True,
                ))
                ctx.driver.execute_script("arguments[0].click();", el)

        _wait_document_ready(timeout=10.0)

        snapshot = _make_page_snapshot(
            max_snapshot_chars=max_snapshot_chars,
            aggressive_cleaning=aggressive_cleaning,
            offset_chars=offset_chars
        )
        return json.dumps({
            "ok": True,
            "action": "click",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })

    except TimeoutException:
        snapshot = _make_page_snapshot(
            max_snapshot_chars=max_snapshot_chars,
            aggressive_cleaning=aggressive_cleaning,
            offset_chars=offset_chars
        )
        return json.dumps({
            "ok": False,
            "error": "timeout",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        snapshot = _make_page_snapshot(
            max_snapshot_chars=max_snapshot_chars,
            aggressive_cleaning=aggressive_cleaning,
            offset_chars=offset_chars
        )
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

    finally:
        try:
            if ctx.is_driver_initialized():
                ctx.driver.switch_to.default_content()
        except Exception:
            pass


async def send_keys(
    key: str,
    selector: Optional[str] = None,
    selector_type: str = "css",
    timeout: float = 10.0,
) -> str:
    """
    Send keyboard keys to an element or to the active element.

    Args:
        key: Key to send (ENTER, TAB, ESCAPE, ARROW_DOWN, etc.)
        selector: Optional CSS selector, XPath, or ID of element to send keys to
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait for element in seconds

    Returns:
        JSON string with ok status, action, key sent, and page snapshot
    """
    ctx = get_context()

    try:
        from selenium.webdriver.common.keys import Keys

        if not ctx.is_driver_initialized():
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        # Map string key names to Selenium Keys
        key_mapping = {
            "ENTER": Keys.ENTER,
            "RETURN": Keys.RETURN,
            "TAB": Keys.TAB,
            "ESCAPE": Keys.ESCAPE,
            "ESC": Keys.ESCAPE,
            "SPACE": Keys.SPACE,
            "BACKSPACE": Keys.BACKSPACE,
            "DELETE": Keys.DELETE,
            "ARROW_UP": Keys.ARROW_UP,
            "ARROW_DOWN": Keys.ARROW_DOWN,
            "ARROW_LEFT": Keys.ARROW_LEFT,
            "ARROW_RIGHT": Keys.ARROW_RIGHT,
            "PAGE_UP": Keys.PAGE_UP,
            "PAGE_DOWN": Keys.PAGE_DOWN,
            "HOME": Keys.HOME,
            "END": Keys.END,
            "F1": Keys.F1,
            "F2": Keys.F2,
            "F3": Keys.F3,
            "F4": Keys.F4,
            "F5": Keys.F5,
            "F6": Keys.F6,
            "F7": Keys.F7,
            "F8": Keys.F8,
            "F9": Keys.F9,
            "F10": Keys.F10,
            "F11": Keys.F11,
            "F12": Keys.F12,
        }

        selenium_key = key_mapping.get(key.upper(), key)

        if selector:
            # Send keys to specific element
            el = retry_op(op=lambda: find_element(
                driver=ctx.driver,
                selector=selector,
                selector_type=selector_type,
                timeout=int(timeout),
                visible_only=True,
            ))
            el.send_keys(selenium_key)
        else:
            # Send keys to active element (usually body or focused element)
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(ctx.driver).send_keys(selenium_key).perform()

        time.sleep(0.2)  # Brief pause
        snapshot = _make_page_snapshot()

        return json.dumps({
            "ok": True,
            "action": "send_keys",
            "key": key,
            "selector": selector,
            "snapshot": snapshot,
        })

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def wait_for_element(
    selector: str,
    selector_type: str = "css",
    timeout: float = 10.0,
    condition: str = "visible",
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
) -> str:
    """
    Wait for an element to meet a specific condition.

    Args:
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait in seconds
        condition: Condition to wait for - 'present', 'visible', or 'clickable'
        iframe_selector: Optional selector for iframe containing the element
        iframe_selector_type: Selector type for the iframe

    Returns:
        JSON string with ok status, element found status, and page snapshot
    """
    ctx = get_context()

    try:
        if not ctx.is_driver_initialized():
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        visible_only = condition in ("visible", "clickable")

        el = find_element(
            driver=ctx.driver,
            selector=selector,
            selector_type=selector_type,
            timeout=int(timeout),
            visible_only=visible_only,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
        )

        if condition == "clickable":
            _wait_clickable_element(el=el, driver=ctx.driver, timeout=timeout)

        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": True,
            "action": "wait_for_element",
            "selector": selector,
            "condition": condition,
            "found": True,
            "snapshot": snapshot,
            "message": f"Element '{selector}' is now {condition}"
        })

    except TimeoutException:
        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": False,
            "error": "timeout",
            "selector": selector,
            "condition": condition,
            "found": False,
            "snapshot": snapshot,
            "message": f"Element '{selector}' did not become {condition} within {timeout}s"
        })

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

    finally:
        try:
            if ctx.is_driver_initialized():
                ctx.driver.switch_to.default_content()
        except Exception:
            pass


__all__ = ['fill_text', 'click_element', 'send_keys', 'wait_for_element']
