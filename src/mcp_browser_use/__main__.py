#region Overview
"""
## Known Limitation: Iframe Context

Multi-step iframe interactions require specifying iframe_selector for each action.
This is intentional design to prevent context state bugs.

## Price, Stock Quantity, and Delivery Times

If you cannot see detailed prices, stock quanities, and delivery times and you suspect that data might be available behind a login, please ask Jan on Slack for help. He can probably log you in.

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

* **Content Pagination:** The MCP supports paginating through large HTML pages using `html_offset` (for HTML mode) and `text_offset` (for TEXT mode). When pages exceed token limits, agents can make multiple calls with increasing offsets to retrieve all content. The offset is applied to cleaned content (after removing scripts/styles/ads), enabling efficient pagination through content-rich pages. Check the `hard_capped` flag in responses to detect truncation.

* **HTML Truncation & Token Management:** The MCP allows you to configure truncation of HTML pages via `token_budget` parameter on all tools. Other scraping MCPs may overwhelm the AI with accessibility snapshots or HTML dumps that are larger than the context window. This MCP provides precise control over snapshot size through configurable token budgets and cleaning levels.

* **Multiple Browser Windows and Multiple Agents:** You can connect multiple agents to this MCP independently, without requiring coordination on behalf of the agents. Each agent can work with **the same** browser profile, which is helpful when logins should persist across agents. Each agent gets their own browser window, so they do not interfere with each other.

* **Flexible Snapshot Modes:** Every tool returns configurable snapshots in multiple formats: `outline` (headings), `text` (extracted text), `html` (cleaned HTML), `dompaths` (element paths), or `mixed` (combination). Choose the representation that best fits your use case.

* **Fine-Grained Element Extraction:** The `extract_elements` tool allows you to extract specific data from the page using CSS selectors or XPath expressions. Specify multiple selectors and choose whether to extract HTML or text content from each matched element. This enables precise data extraction without overwhelming context with full page snapshots. The tool supports iframe and shadow DOM contexts, and can also serve as a standalone "get current page state" tool when called without selectors.


"""
#endregion

#region Required Tools
"""
```
start_browser
```
> Starts a browser if no browser session is open yet for the given user profile.
Opens a new window if an existing browser session is already there.
Multiple agents can share one browser profile (user directory) by each opening a different browser.
This has no impact on the individual agents. For them, they just open a browser
and they do not need to know if other agents are also working
alongside them. The browser handling is abstracted away by the MCP.

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
>         shadow_root_selector: Optional selector for shadow root containing the element
>         shadow_root_selector_type: Selector type for the shadow root

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
>         screenshot_path: Optional path to save the full screenshot
>         return_base64: Whether to return base64 encoded thumbnail (default: False)
>         return_snapshot: Whether to return page HTML snapshot (default: False)
>         thumbnail_width: Optional width in pixels for thumbnail (default: 200px if return_base64=True)
>                         Minimum: 50px. Only used when return_base64=True.
>                         Note: 200px accounts for MCP protocol overhead to stay under 25K token limit.


```
close_browser
```
> Close a browser session.
> This is a very destructive action and should not be done without explicit request from the user!
> Never use this tool unless you are explicitly being told to!


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
extract_elements
```
> Extract content from specific elements on the current page using CSS selectors or XPath.
> This tool enables fine-grained data extraction without requiring full page snapshots.
>
> **MODE 1: Simple Extraction** - Extract individual elements
>     Args:
>         selectors: List of selector specifications with optional "name" field
>         Examples:
>             - [{"selector": "span.price", "type": "css", "format": "text", "name": "price"}]
>             - Get current state: selectors=None (returns full page snapshot)
>
> **MODE 2: Structured Extraction** - Extract from multiple containers (ideal for product listings)
>     Args:
>         container_selector: CSS/XPath for containers (e.g., "article.product-item")
>         fields: List of field extractors with field_name, selector, attribute, regex, fallback
>         selector_type: "css" or "xpath" for container
>         wait_for_visible: Wait for containers to be visible
>         extraction_timeout: Timeout in seconds
>
>     Example (scrape all products on page):
>         container_selector = "article.product-item"  # or "//article[@class='product-item']"
>         fields = [
>             {"field_name": "product_name", "selector": "h3.title"},
>             {"field_name": "mpn", "selector": "span[data-mpn]", "attribute": "data-mpn"},
>             {"field_name": "price_brutto", "selector": ".price", "regex": "[0-9,.]+"},
>             {"field_name": "url", "selector": "a", "attribute": "href"}
>         ]
>         # selector_type is optional - auto-detects from container_selector syntax
>
>     Returns:
>         Structured array: [{"product_name": "...", "mpn": "...", "price_brutto": "..."}, ...]


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
from mcp_browser_use.helpers_context import to_context_pack as _to_context_pack

# Import tools directly (not via helpers) to break circular dependency
from mcp_browser_use.tools import browser_management, navigation, interaction, screenshots, debugging, extraction
#endregion

#region Logger
logger = logging.getLogger(__name__)
#endregion

#region Helper Functions
async def _merge_extraction_results(
    action_result_json: str,
    extract_selectors: Optional[list] = None,
    extract_container: Optional[str] = None,
    extract_fields: Optional[list] = None,
    extract_selector_type: Optional[str] = None,
    extract_wait_visible: bool = False,
    extract_timeout: int = 10,
    extract_max_items: Optional[int] = None,
    extract_discover: bool = False,
) -> str:
    """
    Helper to merge extraction results into action results.

    If extraction parameters are provided, performs extraction and merges results
    into the action result JSON before returning to _to_context_pack.

    Args:
        action_result_json: JSON result from the action
        extract_selectors: Simple extraction selectors
        extract_container: Container selector for structured extraction
        extract_fields: Fields for structured extraction
        extract_selector_type: Selector type for container
        extract_wait_visible: Wait for elements to be visible
        extract_timeout: Timeout for extraction
        extract_max_items: Limit number of containers to extract
        extract_discover: Discovery mode flag

    Returns:
        Merged JSON result with extraction data
    """
    import json as _json

    # If no extraction parameters, return original result
    if not extract_selectors and not extract_container:
        return action_result_json

    # Perform extraction
    extraction_result_json = await extraction.extract_elements(
        selectors=extract_selectors,
        container_selector=extract_container,
        fields=extract_fields,
        selector_type=extract_selector_type,
        wait_for_visible=extract_wait_visible,
        timeout=extract_timeout,
        max_items=extract_max_items,
        discover_containers=extract_discover
    )

    # Parse both results
    try:
        action_result = _json.loads(action_result_json)
        extraction_result = _json.loads(extraction_result_json)

        # Merge extraction data into action result
        # The extraction results will appear in the 'mixed' field via _to_context_pack
        action_result['extraction'] = {
            'mode': extraction_result.get('mode'),
            'extracted_elements': extraction_result.get('extracted_elements'),
            'items': extraction_result.get('items'),
            'count': extraction_result.get('count')
        }

        return _json.dumps(action_result)
    except Exception:
        # If merge fails, return original result
        return action_result_json
#endregion

#region Logging
logger.warning(f"mcp_browser_use from: {getattr(MBU, '__file__', '<namespace>')}")

#region FastMCP Initialization
mcp = FastMCP("mcp_browser_use")
#endregion

#region Tools -- Navigation
@mcp.tool()
@tool_envelope
@exclusive_browser_access
async def mcp_browser_use__start_browser(
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
) -> str:
    """
    Start a browser session or open a new window in an existing session.

    **Performance Recommendation**: Start with token_budget=1000 and cleaning_level=3
    (aggressive cleaning) unless you need more content. This reduces token usage
    significantly while preserving essential information.

    Returns:
        ContextPack JSON
    """
    result = await browser_management.start_browser()
    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget
    )

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__navigate_to_url(
    url: str,
    wait_for: str = "load",
    timeout_sec: int = 20,
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
    # Optional extraction parameters
    extract_selectors: Optional[list] = None,
    extract_container: Optional[str] = None,
    extract_fields: Optional[list] = None,
    extract_selector_type: Optional[str] = None,
    extract_wait_visible: bool = False,
    extract_timeout: int = 10,
    extract_max_items: Optional[int] = None,
    extract_discover: bool = False,
) -> str:
    """
    MCP tool: Navigate the current tab to the given URL and return a ContextPack snapshot.

    Loads the specified URL in the active window/tab and waits for the main document
    to be ready before capturing the snapshot.

    **Performance Recommendation**: Use token_budget=1000-2000 and cleaning_level=3
    (aggressive) by default. Only increase token_budget or decrease cleaning_level
    if you're missing critical information. Most pages work well with 1000 tokens
    and aggressive cleaning, which removes ads, scripts, and non-content elements.

    Args:
        url: Absolute URL to navigate to (e.g., "https://example.com").
        wait_for: Wait condition - "load" (default) or "complete".
        timeout_sec: Maximum time (seconds) to wait for navigation readiness. Waits for asynchronous data to load.
            Some shops such as Buderus.de are very slow and require a longer timeout of about 90 seconds.
        return_mode: Controls the content type in the ContextPack snapshot. One of
            {"outline", "text", "html", "dompaths", "mixed"}.
            **Recommendation**: Use "outline" for navigation, "text" for content extraction.
        cleaning_level: Structural/content cleaning intensity for snapshot rendering.
            0 = none, 1 = light, 2 = default, 3 = aggressive.
            **Recommendation**: Start with 3 (aggressive) to minimize tokens.
        token_budget: Approximate token cap for the returned snapshot. Should usually be 5_000 or lower.
            **Recommendation**: Start with 1000-2000, only increase if needed.
        text_offset: Optional character offset to start text extraction (for pagination).
            Only applies when return_mode="text".
            Example: Use text_offset=10000 to skip the first 10,000 characters.
        html_offset: Optional character offset to start HTML extraction (for pagination).
            Only applies when return_mode="html".
            Example: Use html_offset=50000 to skip the first 50,000 characters of cleaned HTML.
            Note: Offset is applied AFTER cleaning_level processing but BEFORE token_budget truncation.

        extract_selectors: [OPTIONAL EXTRACTION] Simple extraction selectors (MODE 1).
            See extract_elements tool for format.
        extract_container: [OPTIONAL EXTRACTION] Container selector for structured extraction (MODE 2).
        extract_fields: [OPTIONAL EXTRACTION] Field extractors for structured extraction (MODE 2).
        extract_selector_type: [OPTIONAL EXTRACTION] Selector type for container (auto-detects if None).
        extract_wait_visible: [OPTIONAL EXTRACTION] Wait for containers to be visible.
        extract_timeout: [OPTIONAL EXTRACTION] Timeout for extraction in seconds.

    Returns:
        str: JSON-serialized ContextPack with post-navigation snapshot.

    Raises:
        TimeoutError: If the page fails to load within `timeout`.
        ValueError: If `url` is invalid or `return_mode` is invalid.
        RuntimeError: If the browser/driver is not ready.

    Notes:
        - The snapshot reflects the DOM after the initial load. If the site performs
          heavy client-side hydration, consider waiting for a specific element with
          `wait_for_element` before subsequent actions.
        - **Pagination Strategy for Large Pages:**
          When dealing with pages that exceed token limits, use offset parameters to paginate:

          1. First call: Set return_mode="html", token_budget=50000, no offset
             - Check response for `hard_capped=true` to detect truncation

          2. Subsequent calls: Use html_offset to continue from where you left off
             - Example: html_offset=200000 (50000 tokens * 4 chars/token)
             - Continue until you receive less content than token_budget

          3. For TEXT mode pagination, use text_offset with return_mode="text"

        - **Important:** The offset is applied to the cleaned HTML (after removing scripts,
          styles, and noise), not the raw HTML. This means you're paginating through
          content-rich HTML only.

        - **Token Budget Interaction:**
          - Cleaning happens first (scripts/styles/noise removed)
          - Then html_offset is applied (skip first N chars)
          - Finally token_budget truncates the remaining content

        - **Use Cases:**
          - Product catalogs with 1000+ items
          - Long documentation pages
          - Search results with many pages loaded via infinite scroll
          - Large data tables with 10,000+ rows

        - **Extraction Integration:**
          You can optionally extract data immediately after navigation by providing
          extraction parameters. This combines navigation + extraction in a single call:

          Example:
              navigate_to_url(
                  url="https://example.com/products",
                  extract_container="article.product-item",
                  extract_fields=[
                      {"field_name": "product_name", "selector": "h3.title"},
                      {"field_name": "price", "selector": ".price", "regex": "[0-9,.]+"}
                  ]
              )

          This is more efficient than calling navigate followed by extract_elements separately.
    """
    result = await navigation.navigate_to_url(url=url, wait_for=wait_for, timeout_sec=timeout_sec)

    # Merge extraction results if extraction parameters provided
    result = await _merge_extraction_results(
        action_result_json=result,
        extract_selectors=extract_selectors,
        extract_container=extract_container,
        extract_fields=extract_fields,
        extract_selector_type=extract_selector_type,
        extract_wait_visible=extract_wait_visible,
        extract_timeout=extract_timeout,
        extract_max_items=extract_max_items,
        extract_discover=extract_discover
    )

    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )

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
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
    # Optional extraction parameters
    extract_selectors: Optional[list] = None,
    extract_container: Optional[str] = None,
    extract_fields: Optional[list] = None,
    extract_selector_type: Optional[str] = None,
    extract_wait_visible: bool = False,
    extract_timeout: int = 10,
    extract_max_items: Optional[int] = None,
    extract_discover: bool = False,
) -> str:
    """
    MCP tool: Set the value of an input/textarea and return a ContextPack snapshot.

    Focuses the target element, optionally clears existing content, and inserts `text`.

    **Performance Recommendation**: Use token_budget=1000 and cleaning_level=3
    for most form fills. This is sufficient to verify the action succeeded.

    Args:
        selector: Element locator (CSS or XPath).
        text: The exact text to set.
        selector_type: One of {"css", "xpath"}.
        clear_first: If True, clear any existing value before typing.
        click_to_focus: If True, click the element to focus before typing.
        timeout: Maximum time (seconds) to locate and interact with the element.
        iframe_selector: Optional iframe locator containing the element.
        iframe_selector_type: One of {"css", "xpath"}.
        shadow_root_selector: Optional shadow root host locator.
        shadow_root_selector_type: One of {"css", "xpath"}.
        return_mode: Snapshot content type {"outline","text","html","dompaths","mixed"}.
        cleaning_level: Structural/content cleaning intensity (0–3).
        token_budget: Approximate token cap for the returned snapshot. Should usually be 5_000 or lower.

        extract_selectors: [OPTIONAL EXTRACTION] Simple extraction selectors (MODE 1).
        extract_container: [OPTIONAL EXTRACTION] Container selector for structured extraction (MODE 2).
        extract_fields: [OPTIONAL EXTRACTION] Field extractors for structured extraction (MODE 2).
        extract_selector_type: [OPTIONAL EXTRACTION] Selector type for container (auto-detects if None).
        extract_wait_visible: [OPTIONAL EXTRACTION] Wait for containers to be visible.
        extract_timeout: [OPTIONAL EXTRACTION] Timeout for extraction in seconds.

    Returns:
        str: JSON-serialized ContextPack with post-input snapshot.

    Raises:
        TimeoutError: If the element is not ready within `timeout`.
        LookupError: If the selector cannot be resolved.
        ValueError: If `selector_type` or `return_mode` is invalid.
        RuntimeError: If the browser/driver is not ready.

    Notes:
        - Use `send_keys` for complex sequences or special keys.
        - For masked inputs or JS-only fields, consider `force_js` variants if available.
        - **Extraction Integration**: Useful for extracting search results after submitting
          a search query (e.g., fill search box + extract results).
    """
    result = await interaction.fill_text(
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

    # Merge extraction results if extraction parameters provided
    result = await _merge_extraction_results(
        action_result_json=result,
        extract_selectors=extract_selectors,
        extract_container=extract_container,
        extract_fields=extract_fields,
        extract_selector_type=extract_selector_type,
        extract_wait_visible=extract_wait_visible,
        extract_timeout=extract_timeout,
        extract_max_items=extract_max_items,
        extract_discover=extract_discover
    )

    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )

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
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
    # Optional extraction parameters
    extract_selectors: Optional[list] = None,
    extract_container: Optional[str] = None,
    extract_fields: Optional[list] = None,
    extract_selector_type: Optional[str] = None,
    extract_wait_visible: bool = False,
    extract_timeout: int = 10,
    extract_max_items: Optional[int] = None,
    extract_discover: bool = False,
) -> str:
    """
    MCP tool: Click an element (optionally inside an iframe or shadow root) and return a snapshot.

    Attempts a native WebDriver click by default; optionally falls back to JS-based click
    if `force_js` is True or native click is not possible.

    **Performance Recommendation**: Use token_budget=1000 and cleaning_level=3.
    After clicking, you typically only need to verify the action succeeded.

    Args:
        selector: Element locator (CSS or XPath).
        selector_type: How to interpret `selector`. One of {"css", "xpath"}.
        timeout: Maximum time (seconds) to locate a clickable element.
        force_js: If True, use JavaScript-based click instead of native click.
        iframe_selector: Optional locator of an iframe that contains the target element.
        iframe_selector_type: One of {"css", "xpath"}; applies to `iframe_selector`.
        shadow_root_selector: Optional locator whose shadowRoot contains the target element.
        shadow_root_selector_type: One of {"css", "xpath"}; applies to `shadow_root_selector`.
        return_mode: Controls the content type in the ContextPack snapshot.
            {"outline", "text", "html", "dompaths", "mixed"}.
        cleaning_level: Structural/content cleaning intensity (0–3).
        token_budget: Approximate token cap for the returned snapshot. Should usually be 5_000 or lower.

        extract_selectors: [OPTIONAL EXTRACTION] Simple extraction selectors (MODE 1).
        extract_container: [OPTIONAL EXTRACTION] Container selector for structured extraction (MODE 2).
        extract_fields: [OPTIONAL EXTRACTION] Field extractors for structured extraction (MODE 2).
        extract_selector_type: [OPTIONAL EXTRACTION] Selector type for container (auto-detects if None).
        extract_wait_visible: [OPTIONAL EXTRACTION] Wait for containers to be visible.
        extract_timeout: [OPTIONAL EXTRACTION] Timeout for extraction in seconds.

    Returns:
        str: JSON-serialized ContextPack with the snapshot after the click.

    Raises:
        TimeoutError: If the element is not clickable within `timeout`.
        LookupError: If the selector cannot be resolved.
        ValueError: If any selector_type is invalid or `return_mode` is invalid.
        RuntimeError: If the browser/driver is not ready.

    Notes:
        - If both `iframe_selector` and `shadow_root_selector` are provided, the function
          will first resolve the iframe context, then the shadow root context.
        - Some sites block native clicks; `force_js=True` can bypass those cases, but
          it may not trigger all browser-level side effects (e.g., focus).
        - **Extraction Integration**: Useful for extracting data after clicking (e.g.,
          clicking "Show More" and extracting newly loaded products).
    """
    result = await interaction.click_element(
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
        force_js=force_js,
        iframe_selector=iframe_selector,
        iframe_selector_type=iframe_selector_type,
        shadow_root_selector=shadow_root_selector,
        shadow_root_selector_type=shadow_root_selector_type,
    )

    # Merge extraction results if extraction parameters provided
    result = await _merge_extraction_results(
        action_result_json=result,
        extract_selectors=extract_selectors,
        extract_container=extract_container,
        extract_fields=extract_fields,
        extract_selector_type=extract_selector_type,
        extract_wait_visible=extract_wait_visible,
        extract_timeout=extract_timeout,
        extract_max_items=extract_max_items,
        extract_discover=extract_discover
    )

    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__take_screenshot(
    screenshot_path: Optional[str] = None,
    return_base64: bool = False,
    return_snapshot: bool = False,
    thumbnail_width: Optional[int] = None,
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
) -> str:
    result = await screenshots.take_screenshot(
        screenshot_path=screenshot_path,
        return_base64=return_base64,
        return_snapshot=return_snapshot,
        thumbnail_width=thumbnail_width,
    )
    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )
#endregion

#region Tools -- Debugging
@mcp.tool()
@tool_envelope
async def mcp_browser_use__get_debug_diagnostics_info(
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
) -> str:
    """
    MCP tool: Collect driver/browser diagnostics and return a ContextPack.

    Captures diagnostics such as driver session info, user agent, window size, active
    targets, and other implementation-specific debug fields. Diagnostics are included
    in the ContextPack's auxiliary section (e.g., `mixed.diagnostics`).

    **Performance Recommendation**: Use token_budget=500 and cleaning_level=3.
    Diagnostic info is typically metadata, not content.

    Args:
        return_mode: Snapshot content type {"outline","text","html","dompaths","mixed"}.
        cleaning_level: Structural/content cleaning intensity (0–3).
        token_budget: Approximate token cap for the returned snapshot. Should usually be 5_000 or lower.

    Returns:
        str: JSON-serialized ContextPack including diagnostics in `mixed`.

    Raises:
        RuntimeError: If diagnostics cannot be collected.
        ValueError: If `return_mode` is invalid.

    Notes:
        - Useful for troubleshooting issues such as stale sessions, blocked popups,
          or failed navigation. Avoid exposing sensitive values in logs.
    """
    diagnostics = await debugging.get_debug_diagnostics_info()
    return await _to_context_pack(
        result_json=diagnostics,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )

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
    max_html_length: int = 5000,
    include_html: bool = True,
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
) -> str:
    result = await debugging.debug_element(
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
        iframe_selector=iframe_selector,
        iframe_selector_type=iframe_selector_type,
        shadow_root_selector=shadow_root_selector,
        shadow_root_selector_type=shadow_root_selector_type,
        max_html_length=max_html_length,
        include_html=include_html,
    )
    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )
#endregion

#region Tools -- Session management
@mcp.tool()
@tool_envelope
@exclusive_browser_access
async def mcp_browser_use__unlock_browser() -> str:
    unlock_browser_info = await browser_management.unlock_browser()
    return unlock_browser_info

@mcp.tool()
@tool_envelope
@exclusive_browser_access
async def mcp_browser_use__close_browser() -> str:
    """
    This is a very destructive action and should not be done without explicit request from the user!

    Simply do not use this! It is very bad!
    """
    close_browser_info = await browser_management.close_browser()
    return close_browser_info

@mcp.tool()
@tool_envelope
async def mcp_browser_use__force_close_all_chrome() -> str:
    """
    Force close all Chrome processes and clean up all state.

    This is a very destructive action and should not be done without explicit request from the user!

    Simply do not use this! It is very bad!

    Use this to recover from stuck Chrome instances or when normal close_browser fails.
    This will:
    - Quit the Selenium driver
    - Kill all Chrome processes using the MCP profile
    - Clean up lock files and global state

    Returns:
        str: JSON with status, killed process IDs, and any errors encountered
    """
    return await browser_management.force_close_all_chrome()
#endregion

#region Tools -- Page interaction
@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__scroll(
    x: int = 0,
    y: int = 0,
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 100,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
    # Optional extraction parameters
    extract_selectors: Optional[list] = None,
    extract_container: Optional[str] = None,
    extract_fields: Optional[list] = None,
    extract_selector_type: Optional[str] = None,
    extract_wait_visible: bool = False,
    extract_timeout: int = 10,
    extract_max_items: Optional[int] = None,
    extract_discover: bool = False,
) -> str:
    """
    MCP tool: Scroll the page or bring an element into view, then return a snapshot.

    If `selector` is provided, the element is scrolled into view. Otherwise the viewport
    is scrolled by the given pixel deltas (`dx`, `dy`).

    **Performance Recommendation**: Use token_budget=500-1000 and cleaning_level=3.
    Scrolling typically reveals limited new content that needs minimal tokens.

    Args:
        dx: Horizontal pixels to scroll (+right / -left) when no selector is given.
        dy: Vertical pixels to scroll (+down / -up) when no selector is given.
        selector: Optional element to scroll into view instead of pixel-based scroll.
        selector_type: One of {"css", "xpath"}; applies to `selector`.
        smooth: If True, perform a smooth scroll animation (if supported).
        timeout: Maximum time (seconds) to locate the `selector` when provided.
        return_mode: Snapshot content type {"outline","text","html","dompaths","mixed"}.
        cleaning_level: Structural/content cleaning intensity (0–3).
        token_budget: Optional approximate token cap for the returned snapshot. It is generally advisable to set a very low token budget when scrolling.

        extract_selectors: [OPTIONAL EXTRACTION] Simple extraction selectors (MODE 1).
        extract_container: [OPTIONAL EXTRACTION] Container selector for structured extraction (MODE 2).
        extract_fields: [OPTIONAL EXTRACTION] Field extractors for structured extraction (MODE 2).
        extract_selector_type: [OPTIONAL EXTRACTION] Selector type for container (auto-detects if None).
        extract_wait_visible: [OPTIONAL EXTRACTION] Wait for containers to be visible.
        extract_timeout: [OPTIONAL EXTRACTION] Timeout for extraction in seconds.

    Returns:
        str: JSON-serialized ContextPack with post-scroll snapshot.

    Raises:
        TimeoutError: If `selector` is provided but not found within `timeout`.
        ValueError: If `selector_type` or `return_mode` is invalid.
        RuntimeError: If the browser/driver is not ready.

    Notes:
        - Some sticky headers may cover targets scrolled into view; consider an offset
          if your implementation supports it.
        - **Extraction Integration**: Useful for infinite scroll pages where you scroll
          and extract newly loaded items. Example:
              scroll(y=1000, extract_container="article.product", extract_fields=[...])
    """
    result = await navigation.scroll(x=x, y=y)

    # Merge extraction results if extraction parameters provided
    result = await _merge_extraction_results(
        action_result_json=result,
        extract_selectors=extract_selectors,
        extract_container=extract_container,
        extract_fields=extract_fields,
        extract_selector_type=extract_selector_type,
        extract_wait_visible=extract_wait_visible,
        extract_timeout=extract_timeout,
        extract_max_items=extract_max_items,
        extract_discover=extract_discover
    )

    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__send_keys(
    key: str,
    selector: Optional[str] = None,
    selector_type: str = "css",
    timeout: float = 10.0,
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 1_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
) -> str:
    """
    MCP tool: Send key strokes to an element and return a ContextPack snapshot.

    Useful for submitting forms (e.g., Enter) or sending special keys (e.g., Tab, Escape).

    Args:
        selector: Element locator (CSS or XPath).
        keys: A string or list of key tokens to send. Special keys can be supported by
            name (e.g., "ENTER", "TAB", "ESCAPE") depending on implementation.
        selector_type: One of {"css", "xpath"}.
        timeout: Maximum time (seconds) to locate and focus the element.
        iframe_selector: Optional iframe locator containing the element.
        iframe_selector_type: One of {"css", "xpath"}.
        shadow_root_selector: Optional shadow root host locator.
        shadow_root_selector_type: One of {"css", "xpath"}.
        return_mode: Snapshot content type {"outline","text","html","dompaths","mixed"}.
        cleaning_level: Structural/content cleaning intensity (0–3).
        token_budget: Approximate token cap for the returned snapshot. Should usually be 5_000 or lower.

    Returns:
        str: JSON-serialized ContextPack with snapshot after key events.

    Raises:
        TimeoutError: If the element is not ready within `timeout`.
        LookupError: If the selector cannot be resolved.
        ValueError: If `selector_type` or `return_mode` is invalid.
        RuntimeError: If the browser/driver is not ready.

    Notes:
        - Combine with `wait_for_element` to ensure predictable post-typing state.
    """
    result = await interaction.send_keys(
        key=key,
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
    )
    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )

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
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 1_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
) -> str:
    """
    MCP tool: Wait for an element to appear (and optionally be visible) and return a snapshot.

    Polls for the presence of the element and (if `visible=True`) a visible display state.

    Args:
        selector: Element locator (CSS or XPath).
        selector_type: One of {"css", "xpath"}.
        visible: If True, require that the element is visible (not just present).
        timeout: Maximum time (seconds) to wait.
        iframe_selector: Optional iframe locator containing the element.
        iframe_selector_type: One of {"css", "xpath"}.
        shadow_root_selector: Optional shadow root host locator.
        shadow_root_selector_type: One of {"css", "xpath"}.
        return_mode: Snapshot content type {"outline","text","html","dompaths","mixed"}.
        cleaning_level: Structural/content cleaning intensity (0–3).
        token_budget: Approximate token cap for the returned snapshot. Should usually be 5_000 or lower.

    Returns:
        str: JSON-serialized ContextPack capturing the page after the wait condition.

    Raises:
        TimeoutError: If the condition is not met within `timeout`.
        LookupError: If the selector context cannot be resolved.
        ValueError: If `selector_type` or `return_mode` is invalid.
        RuntimeError: If the browser/driver is not ready.
    """
    result = await interaction.wait_for_element(
        selector=selector,
        selector_type=selector_type,
        timeout=timeout,
        condition=condition,
        iframe_selector=iframe_selector,
        iframe_selector_type=iframe_selector_type,
    )
    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )

@mcp.tool()
@tool_envelope
@exclusive_browser_access
@ensure_driver_ready
async def mcp_browser_use__extract_elements(
    selectors: Optional[list] = None,
    container_selector: Optional[str] = None,
    fields: Optional[list] = None,
    selector_type: Optional[str] = None,
    wait_for_visible: bool = False,
    extraction_timeout: int = 10,
    max_items: Optional[int] = None,
    discover_containers: bool = False,
    return_mode: str = "outline",
    cleaning_level: int = 2,
    token_budget: int = 5_000,
    text_offset: Optional[int] = None,
    html_offset: Optional[int] = None,
) -> str:
    """
    MCP tool: Extract content from specific elements on the current page or get page snapshot.

    This tool provides two extraction modes:

    MODE 1: Simple Extraction (using 'selectors' parameter)
    - Extract individual elements with CSS/XPath
    - Returns list of extracted elements with optional field names

    MODE 2: Structured Extraction (using 'container_selector' + 'fields' parameters)
    - Find multiple containers (e.g., all product items on a page)
    - Extract named fields from each container
    - Support attribute extraction (href, data-*, etc.)
    - Apply regex patterns to clean extracted values
    - Returns array of structured objects (perfect for product listings)

    Args:
        selectors: [MODE 1] Optional list of selector specifications. Each dict contains:
            {
                "selector": str,           # CSS selector or XPath expression (required)
                "type": str,               # "css" or "xpath" (default: "css")
                "format": str,             # "html" or "text" (default: "html")
                "name": str,               # Optional: field name for the result
                "timeout": int,            # Timeout in seconds (default: 10)
                "iframe_selector": str,    # Optional: selector for parent iframe
                "iframe_type": str,        # Optional: "css" or "xpath" for iframe
                "shadow_root_selector": str,  # Optional: selector for shadow root host
                "shadow_root_type": str,   # Optional: "css" or "xpath" for shadow root
            }

        container_selector: [MODE 2] CSS or XPath selector for container elements
            Example: "article.product-item" or "//div[@class='product']"

        fields: [MODE 2] List of field extractors, each dict contains:
            {
                "field_name": str,         # Output field name (e.g., "price_net", "mpn")
                "selector": str,           # CSS/XPath relative to container
                "selector_type": str,      # "css" or "xpath" (default: "css")
                "attribute": str,          # Optional: extract attribute (e.g., "href", "data-id")
                "regex": str,              # Optional: regex to extract/clean value
                "fallback": str            # Optional: fallback value if extraction fails
            }

        selector_type: [MODE 2] Optional selector type for container_selector.
            If None, auto-detects from syntax:
            - Starts with "//" or "/" → xpath
            - Otherwise → css
            Note: Each field in 'fields' has its own selector_type inside the dict.

        wait_for_visible: [MODE 2] Wait for containers to be visible before extracting
        extraction_timeout: [MODE 2] Timeout in seconds (default: 10s, capped at 5s for discovery)

        max_items: [MODE 2] **NEW** Limit number of containers to extract (None = all).
            Prevents token explosions and enables testing.
            Recommended values:
            - 10 for testing selectors
            - 50-100 for production extraction
            Example: max_items=10 extracts only first 10 products

        discover_containers: [MODE 2] **NEW** Discovery mode flag (default: False).
            When True, returns container analysis instead of full extraction:
            - Fast (~5s timeout)
            - Lightweight (~1K tokens)
            - Returns: count, sample_html, sample_text, common_child_selectors
            Use this to explore page structure before committing to full extraction

        return_mode: Snapshot content type {"outline","text","html","dompaths","mixed"}
        cleaning_level: Structural/content cleaning intensity (0–3)
        token_budget: Approximate token cap for the returned snapshot. Should usually be 5_000 or lower.
        text_offset: Optional character offset for text mode pagination
        html_offset: Optional character offset for html mode pagination

    Returns:
        str: JSON-serialized ContextPack with extraction results in 'mixed' field:

        MODE 1 Response:
        {
            "mixed": {
                "mode": "simple",
                "extracted_elements": [
                    {"selector": "...", "found": true, "content": "...", "name": "price"},
                    ...
                ]
            },
            "snapshot": {...},
            ...
        }

        MODE 2 Response:
        {
            "mixed": {
                "mode": "structured",
                "items": [
                    {"product_name": "Widget A", "mpn": "12345", "price_brutto": "99.99", ...},
                    {"product_name": "Widget B", "mpn": "67890", "price_brutto": "149.99", ...}
                ],
                "count": 2
            },
            "snapshot": {...},
            ...
        }

    Examples:
        # MODE 1: Simple extraction with named fields
        selectors = [
            {"selector": "span.price", "type": "css", "format": "text", "name": "price"},
            {"selector": "div.stock", "type": "css", "format": "text", "name": "stock_status"}
        ]

        # MODE 2A: Discovery mode (NEW!) - Find containers first
        container_selector = "article.product-item"
        discover_containers = True
        # Fast response with: count, sample_html, common_child_selectors

        # MODE 2B: Test extraction - Small batch
        container_selector = "article.product-item"
        fields = [
            {"field_name": "product_name", "selector": "h3.product-title"},
            {"field_name": "price", "selector": ".price", "regex": r"[0-9,.]+"}
        ]
        max_items = 10  # Test on first 10 items only

        # MODE 2C: Full extraction - With safety limit
        container_selector = "article.product-item"
        fields = [
            {"field_name": "product_name", "selector": "h3.product-title", "selector_type": "css"},
            {"field_name": "mpn", "selector": "span[data-mpn]", "attribute": "data-mpn"},
            {"field_name": "price_brutto", "selector": ".price-brutto", "regex": r"[0-9,.]+"},
            {"field_name": "availability", "selector": ".availability-status"},
            {"field_name": "url", "selector": "a.product-link", "attribute": "href"}
        ]
        max_items = 100  # Safety limit to prevent token explosion
        wait_for_visible = True
        extraction_timeout = 10  # Lowered from 45s

        # Get current page state without extraction
        selectors = None, container_selector = None  # Returns full page snapshot

    Raises:
        ValueError: If selector specification is invalid
        RuntimeError: If the browser/driver is not ready
        TimeoutError: If containers not found within extraction_timeout

    Notes:
        MODE 1:
        - Each selector processed independently; if one fails, others continue
        - Failed extractions return found=False with error message
        - Use "name" field to label extractions
        - Supports iframes and shadow DOM

        MODE 2:
        - Ideal for scraping product listings, tables, search results
        - Extracts all matching containers (e.g., all products on page)
        - Fields extracted relative to each container
        - Regex patterns applied after extraction for cleaning
        - Attribute extraction for links, data-* attributes, etc.
        - Fallback values prevent missing fields
        - Returns structured array of objects ready for database insertion

        **NEW WORKFLOW (Recommended):**
        1. **Discover**: Use discover_containers=True to find correct selector (~5s, ~1K tokens)
        2. **Test**: Use max_items=10 to validate extraction (~10s, ~5K tokens)
        3. **Extract**: Use max_items=50-100 for production (~20s, controlled tokens)

        This 3-step workflow prevents:
        - Wasting time on wrong selectors (45s timeouts)
        - Token explosions (41K+ tokens from bad selectors)
        - Context clogging from oversized responses

        - Use return_mode="mixed" to see extraction results alongside page content
        - All extractions performed on current page state (no navigation)
    """
    result = await extraction.extract_elements(
        selectors=selectors,
        container_selector=container_selector,
        fields=fields,
        selector_type=selector_type,
        wait_for_visible=wait_for_visible,
        timeout=extraction_timeout,
        max_items=max_items,
        discover_containers=discover_containers
    )
    return await _to_context_pack(
        result_json=result,
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
        text_offset=text_offset,
        html_offset=html_offset
    )
#endregion


if __name__ == "__main__":
    mcp.run()