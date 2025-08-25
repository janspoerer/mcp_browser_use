#begin Overview
"""
The MCP should allow multiple browser windows to be opened. Each AI agent can call the "start_browser" tool. If the browser is not open at all, it is opened, using the specified persistent user profile. If a browser is already open, so if the second agent calls "start_browser", a new window is opened. Each agent only uses their own window. The windows are identified by tags.

When an agent performs an action, the browser should be briefly locked until 10 seconds are over or until the agent unlocks the browser. This can be done with a lock file.

The MCP returns a cleaned HTML version of the page after each action, so the agent can see what changed and what it can do to further interact with the page or find information from the page.


## Feature Highlights

* **HTML Truncation:** The MCP allows you to configure truncation of the HTML pages. Other scraping MCPs may overwhelm the AI with accessibility snapshots or HTML dumps that are larger than the context window. This MCP will help you to manage the maximum page size by setting the `MCP_MAX_SNAPSHOT_CHARS` environment variable.
* **Multiple Browser Windows and Multiple Agents:** You can connect multiple agents to this MCP independently, without requiring coordination on behalf of the agents. Each agent can work with **the same** browser profile, which is helpful when logins should persist across agents. Each agent gets their own browser window, so they do not interfere with each other. 


"""
#endregion

#begin Required Tools
"""
```
start_browser
```
> Starts a browser if no browser session is open yet for the given user profile.
Opens a new window if an exisitng browser session is already there.
Multiple agents can share one browser profile (user directory) by each opening a different browser.
This has no impact on the individual agents. For them, they just open a browser 
and they do not need to know if other agents are also working
alongside them. The browser handling is abstracted away by the MCP.

```
get_browser_versions
```
> Return the installed Chrome and Chromedriver versions to verify compatibility.

```
navigate
```
>     Navigates the browser to a specified URL.
>
>    Args:
>        session_id (str): The ID of the browser session.
>        url (str): The URL to navigate to.
>
>    Returns:
>        str: A message indicating successful navigation, along with the page title and HTML.

```
click_element
```
>     Clicks an element on the web page, with iframe and shadow root support.
>
>     Args:
>        session_id (str): The ID of the browser session.
>        selector (str): The selector for the element to click.
>        selector_type (str, optional): The type of selector. Defaults to 'css'.
>        timeout (int, optional): Maximum wait time for the element to be clickable. Defaults to 10.
>        force_js (bool, optional): If True, uses JavaScript to click the element. Defaults to False.
>        iframe_selector (str, optional): Selector for the iframe. Defaults to None.
>        iframe_selector_type (str, optional): Selector type for the iframe. Defaults to 'css'.
>        shadow_root_selector (str, optional): Selector for the shadow root. Defaults to None.
>        shadow_root_selector_type (str, optional): Selector type for the shadow root. Defaults to 'css'.
>
>    Returns:
>        str: A message indicating successful click, along with the current URL and page title.

```
fill_text
```
> Input text into an element.
>
>     Args:
>         session_id: Session ID of the browser
>         selector: CSS selector, XPath, or ID of the input field
>         text: Text to enter into the field
>         selector_type: Type of selector (css, xpath, id)
>         clear_first: Whether to clear the field before entering text
>         timeout: Maximum time to wait for the element in seconds

```
send_keys
```
> Send keyboard keys to the browser.
> 
>     Args:
>         session_id: Session ID of the browser
>         key: Key to send (e.g., ENTER, TAB, etc.)
>         selector: CSS selector, XPath, or ID of the element to send keys to (optional)
>         selector_type: Type of selector (css, xpath, id)

```
scroll
```
> Scroll the page.
> 
>     Args:
>         session_id: Session ID of the browser
>         x: Horizontal scroll amount in pixels
>         y: Vertical scroll amount in pixels

```
take_screenshot
```
> Take a screenshot of the current page.
> 
>     Args:
>         session_id: Session ID of the browser
>         screenshot_path: Optional path to save screenshot file


```
close_browser
```
> Close a browser session.
> 
>     Args:
>         session_id: Session ID of the browser to close

```
wait_for_element
```
> Wait for an element to be present, visible, or clickable.
> 
>     Args:
>         session_id: Session ID of the browser
>         selector: CSS selector, XPath, or ID of the element
>         selector_type: Type of selector (css, xpath, id)
>         timeout: Maximum time to wait in seconds
>         condition: What to wait for - 'present', 'visible', or 'clickable'


```
read_chromedriver_log
```
>     Fetch the first N lines of the Chromedriver log for debugging.
>
>    Args:
>        session_id (str): Browser session ID.
>        lines (int): Number of lines to return from the top of the log.


```
get_debug_info
```
> Return user-data dir, profile name, full profile path, Chrome binary path,
> browser/driver/Selenium versions – everything we need for debugging.



```
debug_element
```
> Debug why an element might not be clickable or visible.
> 
>     Args:
>         session_id: Session ID of the browser
>         selector: CSS selector, XPath, or ID of the element
>         selector_type: Type of selector (css, xpath, id)

```
"""
#endregion

# mcp_browser_use/__main__.py
# main.py (patched snippet)



import json
import logging
import os
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional
from mcp.server.fastmcp import FastMCP
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.support.ui import WebDriverWait

# Import from your package __init__.py
from mcp_browser_use.helpers import (
    INTRA_PROCESS_LOCK,
    DRIVER,
    DEBUGGER_HOST,
    DEBUGGER_PORT,

    # session/process/window management
    ensure_process_tag,
    _ensure_driver_and_window,
    _wait_document_ready,
    _make_page_snapshot,
    _wait_clickable_element,
    close_singleton_window,

    # locking
    _acquire_action_lock_or_error,
    _renew_action_lock,
    _release_action_lock,

    # DOM utils and diagnostics
    retry_op,
    find_element,
    get_cleaned_html,
    collect_diagnostics,
    get_env_config,
)

logger = logging.getLogger(__name__)

#region FastMCP Initialization
mcp = FastMCP("mcp_browser_use")
#endregion

#region Tools -- Navigation
@mcp.tool()
async def start_browser() -> str:
    async with INTRA_PROCESS_LOCK:
        had_lock = False
        owner = ensure_process_tag()
        try:
            err = _acquire_action_lock_or_error(owner)
            if err:
                return err
            had_lock = True

            _ensure_driver_and_window()
            _wait_document_ready(timeout=5.0)
            snapshot = _make_page_snapshot()

            return json.dumps({
                "ok": True,
                # Expose the process tag so clients can correlate logs/locks if they want
                "session_id": owner,
                "debugger": f"{DEBUGGER_HOST}:{DEBUGGER_PORT}",
                "lock_ttl_seconds": int(os.getenv("MCP_ACTION_LOCK_TTL", "10")),
                "snapshot": snapshot,
            })
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
        finally:
            if had_lock:
                _renew_action_lock(owner)

@mcp.tool()
async def navigate(url: str, timeout: float = 30.0) -> str:
    async with INTRA_PROCESS_LOCK:
        had_lock = False
        owner = ensure_process_tag()
        try:
            if not url:
                snapshot = _make_page_snapshot()
                return json.dumps({"ok": False, "error": "invalid_url", "snapshot": snapshot})

            err = _acquire_action_lock_or_error(owner)
            if err:
                return err
            had_lock = True

            _ensure_driver_and_window()
            DRIVER.get(url)
            _wait_document_ready(timeout=min(15.0, float(timeout)))

            snapshot = _make_page_snapshot()
            return json.dumps({"ok": True, "url": url, "snapshot": snapshot})
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
        finally:
            if had_lock:
                _renew_action_lock(owner)

@mcp.tool()
async def fill_text(
    selector: str,
    text: str,
    selector_type: str = "css",
    clear_first: bool = True,
    timeout: float = 10.0,
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
    shadow_root_selector: Optional[str] = None,
    shadow_root_selector_type: str = "css",
) -> str:
    async with INTRA_PROCESS_LOCK:
        had_lock = False
        owner = ensure_process_tag()
        try:
            err = _acquire_action_lock_or_error(owner)
            if err:
                return err
            had_lock = True

            _ensure_driver_and_window()

            el = retry_op(lambda: find_element(
                DRIVER,
                selector,
                selector_type,
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

            snapshot = _make_page_snapshot()
            return json.dumps({"ok": True, "action": "fill_text", "selector": selector, "snapshot": snapshot})
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
        finally:
            try:
                if DRIVER is not None:
                    DRIVER.switch_to.default_content()
            except Exception:
                pass
            if had_lock:
                _renew_action_lock(owner)

@mcp.tool()
async def click_element(
    selector: str,
    selector_type: str = "css",
    timeout: float = 10.0,
    force_js: bool = False,
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
    shadow_root_selector: Optional[str] = None,
    shadow_root_selector_type: str = "css",
) -> str:
    async with INTRA_PROCESS_LOCK:
        had_lock = False
        owner = ensure_process_tag()
        try:
            err = _acquire_action_lock_or_error(owner)
            if err:
                return err
            had_lock = True

            _ensure_driver_and_window()

            el = retry_op(lambda: find_element(
                DRIVER,
                selector,
                selector_type,
                timeout=int(timeout),
                visible_only=True,
                iframe_selector=iframe_selector,
                iframe_selector_type=iframe_selector_type,
                shadow_root_selector=shadow_root_selector,
                shadow_root_selector_type=shadow_root_selector_type,
                stay_in_context=True,
            ))

            _wait_clickable_element(el, timeout=timeout)

            if force_js:
                DRIVER.execute_script("arguments[0].click();", el)
            else:
                try:
                    el.click()
                except (ElementClickInterceptedException, StaleElementReferenceException):
                    DRIVER.execute_script("arguments[0].click();", el)

            _wait_document_ready(timeout=10.0)

            snapshot = _make_page_snapshot()
            return json.dumps({
                "ok": True,
                "action": "click",
                "selector": selector,
                "selector_type": selector_type,
                "snapshot": snapshot,
            })
        except TimeoutException:
            snapshot = _make_page_snapshot()
            return json.dumps({
                "ok": False,
                "error": "timeout",
                "selector": selector,
                "selector_type": selector_type,
                "snapshot": snapshot,
            })
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
        finally:
            try:
                if DRIVER is not None:
                    DRIVER.switch_to.default_content()
            except Exception:
                pass
            if had_lock:
                _renew_action_lock(owner)

@mcp.tool()
async def take_screenshot(screenshot_path: Optional[str] = None, return_base64: bool = False) -> str:
    async with INTRA_PROCESS_LOCK:
        had_lock = False
        owner = ensure_process_tag()
        try:
            err = _acquire_action_lock_or_error(owner)
            if err:
                return err
            had_lock = True

            _ensure_driver_and_window()

            png_b64 = DRIVER.get_screenshot_as_base64()
            if screenshot_path:
                with open(screenshot_path, "wb") as f:
                    f.write(DRIVER.get_screenshot_as_png())
            payload = {"ok": True, "saved_to": screenshot_path}
            if return_base64:
                payload["base64"] = png_b64
            payload["snapshot"] = _make_page_snapshot()
            return json.dumps(payload)
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
        finally:
            if had_lock:
                _renew_action_lock(owner)
#endregion

#region Tools -- Debugging
@mcp.tool()
async def get_debug_diagnostics_info() -> str:
    async with INTRA_PROCESS_LOCK:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})
        try:
            info = collect_diagnostics(DRIVER, None, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": True, "diagnostics": info, "snapshot": snapshot})
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})


@mcp.tool()
async def debug_element(
    selector: str,
    selector_type: str = "css",
    timeout: float = 10.0,
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
    shadow_root_selector: Optional[str] = None,
    shadow_root_selector_type: str = "css",
) -> str:
    async with INTRA_PROCESS_LOCK:
        had_lock = False
        owner = ensure_process_tag()
        try:
            err = _acquire_action_lock_or_error(owner)
            if err:
                return err
            had_lock = True

            _ensure_driver_and_window()

            info: Dict[str, Any] = {
                "selector": selector,
                "selector_type": selector_type,
                "exists": False,
                "displayed": None,
                "enabled": None,
                "clickable": None,
                "rect": None,
                "outerHTML": None,
                "notes": [],
            }

            try:
                el = retry_op(lambda: find_element(
                    DRIVER,
                    selector,
                    selector_type,
                    timeout=int(timeout),
                    visible_only=False,
                    iframe_selector=iframe_selector,
                    iframe_selector_type=iframe_selector_type,
                    shadow_root_selector=shadow_root_selector,
                    shadow_root_selector_type=shadow_root_selector_type,
                    stay_in_context=True,
                ))
                info["exists"] = True

                try:
                    info["displayed"] = bool(el.is_displayed())
                except Exception:
                    info["displayed"] = None
                try:
                    info["enabled"] = bool(el.is_enabled())
                except Exception:
                    info["enabled"] = None

                try:
                    _wait_clickable_element(el, timeout=timeout)
                    info["clickable"] = True
                except Exception:
                    info["clickable"] = False

                try:
                    r = el.rect
                    info["rect"] = {
                        "x": r.get("x"),
                        "y": r.get("y"),
                        "width": r.get("width"),
                        "height": r.get("height"),
                    }
                except Exception:
                    info["rect"] = None

                try:
                    html = DRIVER.execute_script("return arguments[0].outerHTML;", el)
                    info["outerHTML"] = html
                except Exception:
                    info["outerHTML"] = None

            except TimeoutException:
                info["notes"].append("Element not found within timeout")
            except Exception as e:
                info["notes"].append(f"Error while probing element: {repr(e)}")

            snapshot = _make_page_snapshot()
            return json.dumps({"ok": True, "debug": info, "snapshot": snapshot})
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            snapshot = _make_page_snapshot()
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
        finally:
            try:
                if DRIVER is not None:
                    DRIVER.switch_to.default_content()
            except Exception:
                pass
            if had_lock:
                _renew_action_lock(owner)
#endregion

#region Tools -- Session management
@mcp.tool()
async def unlock_browser() -> str:
    async with INTRA_PROCESS_LOCK:
        owner = ensure_process_tag()
        released = _release_action_lock(owner)
        return json.dumps({"ok": True, "released": bool(released)})

@mcp.tool()
async def close_browser() -> str:
    async with INTRA_PROCESS_LOCK:
        had_lock = False
        owner = ensure_process_tag()
        try:
            err = _acquire_action_lock_or_error(owner)
            if err:
                return err
            had_lock = True

            closed = close_singleton_window()
            return json.dumps({"ok": True, "closed": bool(closed)})
        except Exception as e:
            diag = collect_diagnostics(DRIVER, e, get_env_config())
            return json.dumps({"ok": False, "error": str(e), "diagnostics": diag})
        finally:
            if had_lock:
                _renew_action_lock(owner)
#endregion