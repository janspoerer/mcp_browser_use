"""Element interaction tool implementations."""

import json
import time
from typing import Optional
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)
import mcp_browser_use.helpers as helpers
from mcp_browser_use.utils.diagnostics import collect_diagnostics


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
    try:

        el = helpers.retry_op(op=lambda: helpers.find_element(
            driver=helpers.DRIVER,
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
        helpers._wait_document_ready(timeout=5.0)

        snapshot = helpers._make_page_snapshot(max_snapshot_chars=max_snapshot_chars, aggressive_cleaning=aggressive_cleaning, offset_chars=offset_chars)
        return json.dumps({"ok": True, "action": "fill_text", "selector": selector, "snapshot": snapshot})
    except Exception as e:
        diag = collect_diagnostics(driver=helpers.DRIVER, exc=e, config=helpers.get_env_config())
        snapshot = helpers._make_page_snapshot(max_snapshot_chars=max_snapshot_chars, aggressive_cleaning=aggressive_cleaning, offset_chars=offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if helpers.DRIVER is not None:
                helpers.DRIVER.switch_to.default_content()
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
    try:

        el = helpers.retry_op(op=lambda: helpers.find_element(
            driver=helpers.DRIVER,
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

        helpers._wait_clickable_element(el=el, driver=helpers.DRIVER, timeout=timeout)

        if force_js:
            helpers.DRIVER.execute_script("arguments[0].click();", el)
        else:
            try:
                el.click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                el = helpers.retry_op(op=lambda: helpers.find_element(
                    driver=helpers.DRIVER,
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
                helpers.DRIVER.execute_script("arguments[0].click();", el)

        helpers._wait_document_ready(timeout=10.0)

        snapshot = helpers._make_page_snapshot(max_snapshot_chars=max_snapshot_chars, aggressive_cleaning=aggressive_cleaning, offset_chars=offset_chars)
        return json.dumps({
            "ok": True,
            "action": "click",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })
    except TimeoutException:
        snapshot = helpers._make_page_snapshot(max_snapshot_chars=max_snapshot_chars, aggressive_cleaning=aggressive_cleaning, offset_chars=offset_chars)
        return json.dumps({
            "ok": False,
            "error": "timeout",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(driver=helpers.DRIVER, exc=e, config=helpers.get_env_config())
        snapshot = helpers._make_page_snapshot(max_snapshot_chars=max_snapshot_chars, aggressive_cleaning=aggressive_cleaning, offset_chars=offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if helpers.DRIVER is not None:
                helpers.DRIVER.switch_to.default_content()
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
    try:
        from selenium.webdriver.common.keys import Keys

        if helpers.DRIVER is None:
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
            el = helpers.retry_op(op=lambda: helpers.find_element(
                driver=helpers.DRIVER,
                selector=selector,
                selector_type=selector_type,
                timeout=int(timeout),
                visible_only=True,
            ))
            el.send_keys(selenium_key)
        else:
            # Send keys to active element (usually body or focused element)
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(helpers.DRIVER).send_keys(selenium_key).perform()

        time.sleep(0.2)  # Brief pause
        snapshot = helpers._make_page_snapshot()

        return json.dumps({
            "ok": True,
            "action": "send_keys",
            "key": key,
            "selector": selector,
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(driver=helpers.DRIVER, exc=e, config=helpers.get_env_config())
        snapshot = helpers._make_page_snapshot()
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
    try:
        if helpers.DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        visible_only = condition in ("visible", "clickable")

        el = helpers.find_element(
            driver=helpers.DRIVER,
            selector=selector,
            selector_type=selector_type,
            timeout=int(timeout),
            visible_only=visible_only,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
        )

        if condition == "clickable":
            helpers._wait_clickable_element(el=el, driver=helpers.DRIVER, timeout=timeout)

        snapshot = helpers._make_page_snapshot()
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
        snapshot = helpers._make_page_snapshot()
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
        diag = collect_diagnostics(driver=helpers.DRIVER, exc=e, config=helpers.get_env_config())
        snapshot = helpers._make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if helpers.DRIVER is not None:
                helpers.DRIVER.switch_to.default_content()
        except Exception:
            pass


__all__ = ['fill_text', 'click_element', 'send_keys', 'wait_for_element']
