"""
## Known Limitation: Iframe Context

Multi-step iframe interactions require specifying iframe_selector for each action.
This is intentional design to prevent context state bugs.

## Performance Considerations

We do not mind additional overhead from validations. The most important thing is that the code is robust.

## Tip for Debugging

Do you find any obvious errors in the code? Please do rubber duck 
debugging. Imagine you are the first agent that establishes a 
connection. You connect and want to navigate. You call the function 
to go to a website, but probably receive an error, because you have
to open the browser first. Or do you not receive and error and the
MCP server automatically opens a browser? That would also be fine.
Then you open the browse, if not open yet. Then you click 
around a bit. Then another agent 
establishes a separate MCP server connection and does the same. 
Then the first agent is done with his work and closes the connection. 
The second continues working. In this rubber duck 
journey, is there anything that does not work well?
"""

#region Overview
"""
The MCP should allow multiple browser windows to be opened. Each AI agent can call the "start_browser" tool. If the browser is not open at all, it is opened, using the specified persistent user profile. If a browser is already open, so if the second agent calls "start_browser", a new window is opened. Each agent only uses their own window. The windows are identified by tags.

When an agent performs an action, the browser should be briefly locked until 10 seconds are over or until the agent unlocks the browser. This can be done with a lock file.

The MCP returns a cleaned HTML version of the page after each action, so the agent can see what changed and what it can do to further interact with the page or find information from the page.

## How Multiple Agents are Handled

We do not manage multiple sessions in one MCP connection. 

While each agent will connect to this very same mcp_browser_use code, 
they will still connect independently. They can start and stop their MCP server
connections at will without affecting the functioning of the browser. The 
agents are agnostic to whether other agents are currently running.
The MCP for browser use that we develop here should abstract the browser
handling away from the agents.

When a second agent opens a browser, the agent gets its own browser window. IT MUST NOT USE THE SAME BROWSER WINDOW! The second agent WILL NOT open another browser session.

## Feature Highlights

* **HTML Truncation:** The MCP allows you to configure truncation of the HTML pages. Other scraping MCPs may overwhelm the AI with accessibility snapshots or HTML dumps that are larger than the context window. This MCP will help you to manage the maximum page size by setting the `MCP_MAX_SNAPSHOT_CHARS` environment variable.
* **Multiple Browser Windows and Multiple Agents:** You can connect multiple agents to this MCP independently, without requiring coordination on behalf of the agents. Each agent can work with **the same** browser profile, which is helpful when logins should persist across agents. Each agent gets their own browser window, so they do not interfere with each other. 


"""
#endregion

#region Required Tools
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
>        url (str): The URL to navigate to.
>
>    Returns:
>        str: A message indicating successful navigation, along with the page title and HTML.

```
click_element
```
>     Clicks an element on the web page, with iframe and shadow root support.
>     
>     Note: For multi-step iframe interactions, specify iframe_selector in each call.
>     Browser context resets after each action for reliability.
>
>     Args:
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
> Note: For multi-step iframe interactions, specify iframe_selector in each call.
> Browser context resets after each action for reliability.
>
>     Args:
>         selector: CSS selector, XPath, or ID of the input field
>         text: Text to enter into the field
>         selector_type: Type of selector (css, xpath, id)
>         clear_first: Whether to clear the field before entering text
>         timeout: Maximum time to wait for the element in seconds
>         iframe_selector: Selector for the iframe (if element is inside iframe)
>         iframe_selector_type: Selector type for the iframe

```
send_keys
```
> Send keyboard keys to the browser.
> 
>     Args:
>         key: Key to send (e.g., ENTER, TAB, etc.)
>         selector: CSS selector, XPath, or ID of the element to send keys to (optional)
>         selector_type: Type of selector (css, xpath, id)

```
scroll
```
> Scroll the page.
> 
>     Args:
>         x: Horizontal scroll amount in pixels
>         y: Vertical scroll amount in pixels

```
take_screenshot
```
> Take a screenshot of the current page.
> 
>     Args:
>         screenshot_path: Optional path to save screenshot file


```
close_browser
```
> Close a browser session.
> 


```
wait_for_element
```
> Wait for an element to be present, visible, or clickable.
> 
>     Args:
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
>        lines (int): Number of lines to return from the top of the log.


```
get_debug_info
```
> Return user-data dir, profile name, full profile path, Chrome binary path,
> browser/driver/Selenium versions -- everything we need for debugging.



```
debug_element
```
> Debug why an element might not be clickable or visible.
> 
> Note: For iframe elements, specify iframe_selector to debug within iframe context.
> 
>     Args:
>         selector: CSS selector, XPath, or ID of the element
>         selector_type: Type of selector (css, xpath, id)
>         iframe_selector: Selector for the iframe (if element is inside iframe)
>         iframe_selector_type: Selector type for the iframe

```
"""
#endregion

#region Imports
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP
#endregion 

#region Import from your package __init__.py
import mcp_browser_use as MBU
from mcp_browser_use.decorators import (
    tool_envelope, 
    exclusive_browser_access,
    ensure_driver_ready,
)
#endregion

#region Logger
logger = logging.getLogger(__name__)
logger.warning(f"mcp_browser_use from: {getattr(MBU, '__file__', '<namespace>')}")
#endregion

#region FastMCP Initialization
mcp = FastMCP("mcp_browser_use")
#endregion

#region Tools -- Navigation
@mcp.tool()
@tool_envelope
@exclusive_browser_access
async def mcp_browser_use__start_browser() -> str:
    return await MBU.helpers.start_browser()

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__navigate_to_url(
    url: str, 
    timeout: float = 30.0
) -> str:
    return await MBU.helpers.navigate_to_url(url=url, timeout=timeout)

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__fill_text(
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
    snapshot = await MBU.helpers.fill_text(
        selector=selector,
        text=text,
        selector_type=selector_type,
        clear_first=clear_first,
        timeout=timeout,
        iframe_selector=iframe_selector,
        iframe_selector_type=iframe_selector_type,
        shadow_root_selector=shadow_root_selector,
        shadow_root_selector_type=shadow_root_selector_type,
    )

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")

    return snapshot

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__click_element(
    selector: str,
    selector_type: str = "css",
    timeout: float = 10.0,
    force_js: bool = False,
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
    shadow_root_selector: Optional[str] = None,
    shadow_root_selector_type: str = "css",
) -> str:
    snapshot = await MBU.helpers.click_element(
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
        force_js=force_js,
        iframe_selector=iframe_selector,
        iframe_selector_type=iframe_selector_type,
        shadow_root_selector=shadow_root_selector,
        shadow_root_selector_type=shadow_root_selector_type,
    )

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")
    
    return  snapshot

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__take_screenshot(screenshot_path: Optional[str] = None, return_base64: bool = False, return_snapshot: bool = False) -> str:
    snapshot = await MBU.helpers.take_screenshot(screenshot_path=screenshot_path, return_base64=return_base64, return_snapshot=return_snapshot)

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")
    
    return snapshot
#endregion

#region Tools -- Debugging
@mcp.tool()
@tool_envelope
async def mcp_browser_use__get_debug_diagnostics_info() -> str:
    diagnostics = await MBU.helpers.get_debug_diagnostics_info()
    return diagnostics
        
@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__debug_element(
    selector: str,
    selector_type: str = "css",
    timeout: float = 10.0,
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
    shadow_root_selector: Optional[str] = None,
    shadow_root_selector_type: str = "css",
) -> str:
    debug_info = await MBU.helpers.debug_element(
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
        iframe_selector=iframe_selector,
        iframe_selector_type=iframe_selector_type,
        shadow_root_selector=shadow_root_selector,
        shadow_root_selector_type=shadow_root_selector_type,
    )
    return debug_info
#endregion

#region Tools -- Session management
@mcp.tool()
@tool_envelope
@exclusive_browser_access
async def mcp_browser_use__unlock_browser() -> str:
    unlock_browser_info = await MBU.helpers.unlock_browser()
    return unlock_browser_info

@mcp.tool()
@tool_envelope
@exclusive_browser_access
async def mcp_browser_use__close_browser() -> str:
    close_browser_info = await MBU.helpers.close_browser()
    return close_browser_info
#endregion

#region Tools -- Page interaction
@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__scroll(x: int = 0, y: int = 0) -> str:
    """
    Scroll the page by the specified pixel amounts.

    Args:
        x: Horizontal scroll amount in pixels (positive = right, negative = left)
        y: Vertical scroll amount in pixels (positive = down, negative = up)
    """
    snapshot = await MBU.helpers.scroll(x=x, y=y)

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")

    return snapshot

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__send_keys(
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
    """
    snapshot = await MBU.helpers.send_keys(
        key=key,
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
    )

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")

    return snapshot

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__wait_for_element(
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
    """
    snapshot = await MBU.helpers.wait_for_element(
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
        condition=condition,
        iframe_selector=iframe_selector,
        iframe_selector_type=iframe_selector_type,
    )

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")

    return snapshot
#endregion

#region Tools -- Cookie management
@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__get_cookies() -> str:
    """Get all cookies for the current page/domain."""
    snapshot = await MBU.helpers.get_cookies()

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")

    return snapshot

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__add_cookie(
    name: str,
    value: str,
    domain: Optional[str] = None,
    path: str = "/",
    secure: bool = False,
    http_only: bool = False,
    expiry: Optional[int] = None,
) -> str:
    """
    Add a cookie to the browser.

    Args:
        name: Cookie name
        value: Cookie value
        domain: Optional domain for the cookie (defaults to current domain)
        path: Cookie path (default: "/")
        secure: Whether cookie should only be sent over HTTPS
        http_only: Whether cookie should be HTTP-only
        expiry: Optional expiry timestamp (Unix epoch seconds)
    """
    snapshot = await MBU.helpers.add_cookie(
        name=name,
        value=value,
        domain=domain,
        path=path,
        secure=secure,
        http_only=http_only,
        expiry=expiry,
    )

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")

    return snapshot

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__delete_cookie(name: str) -> str:
    """
    Delete a specific cookie by name.

    Args:
        name: Name of the cookie to delete
    """
    snapshot = await MBU.helpers.delete_cookie(name=name)

    if not isinstance(snapshot, str):
        raise TypeError(f"snapshot is not string, is type {type(snapshot)}, content: {snapshot}")

    return snapshot
#endregion

if __name__ == "__main__":
    mcp.run()