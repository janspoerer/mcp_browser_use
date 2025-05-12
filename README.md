
# MCP Browser Use

<img src="docs/mcp_browser_use_logo.jpg" alt="Description" width="300">


<br>
<br>
<br>

## What You Can Achieve With This MCP

This project aims to empower AI agents to perform web use, browser automation, scraping, and automation with Model Context Protocol (MCP) and Selenium.

> Our mission is to let AI agents complete any web task with minimal human supervision -- all based on natural language instructions.

## How to Use This MCP

Please refer to the [MCP documentation on modelcontextprotocol.io](https://modelcontextprotocol.io/quickstart/user).

Please note that you will need to install all dependencies in the Python environment that your MCP config file points to. For example, if you point to the `python` or `python3` executable, you will point to the global Python environment. Usually it is preferred to point to a virtual environment such as:

```
/Users/yourname/code/mcp_browser_use/.venv/bin/python
```

If you have cloned this repository to your local `code` folder, your MCP config file should look like this:

```
{
    "mcpServers": {
        "mcp_browser_use": {
            "command": "/Users/janspoerer/code/mcp_browser_use/.venv/bin/python",
            "args": [
                "/Users/janspoerer/code/mcp_browser_use/mcp_browser_use"
            ]
        }
    }
}
```

and it will be here (in macOS): `/Users/janspoerer/Library/Application Support/Claude/claude_desktop_config.json`.

Please refer to the `requirements.txt` to see which dependencies you need to install.

Restart Claude to see if the JSON config is valid. Claude will lead to you the error logs for the MCP if something is off.

If the setup was successful, you will see a small hammer icon in the bottom-right of the "New Chat" window in Claude. Next to the hammer will be the number of functions that the MCP provides.

Click to hammer to see something like this:

```
Available MCP Tools

Claude can use tools provided by specialized servers using Model Context Protocol. Learn more about MCP.

click_element
Click an element on the page. Args: session_id: Session ID of the browser selector: CSS selector, XPath, or ID of the element to click selector_type: Type of selector (css, xpath, id)

From server: mcp_browser_use

close_browser
Close a browser session. Args: session_id: Session ID of the browser to close

From server: mcp_browser_use

fill_text
Input text into an element. Args: session_id: Session ID of the browser selector: CSS selector, XPath, or ID of the input field text: Text to enter into the field selector_type: Type of selector (css, xpath, id) clear_first: Whether to clear the field before entering text

From server: mcp_browser_use

navigate
Navigate to a URL. Args: session_id: Session ID of the browser url: URL to navigate to

From server: mcp_browser_use

scroll
Scroll the page. Args: session_id: Session ID of the browser x: Horizontal scroll amount in pixels y: Vertical scroll amount in pixels

From server: mcp_browser_use

send_keys
Send keyboard keys to the browser. Args: session_id: Session ID of the browser key: Key to send (e.g., ENTER, TAB, etc.) selector: CSS selector, XPath, or ID of the element to send keys to (optional) selector_type: Type of selector (css, xpath, id)

From server: mcp_browser_use

start_browser
Start a new browser session. Args: headless: Whether to run the browser in headless mode

From server: mcp_browser_use

take_screenshot
Take a screenshot of the current page. Args: session_id: Session ID of the browser

From server: mcp_browser_use
```


## Demo Video (YouTube)

[![Quick demo](https://img.youtube.com/vi/20B8trurlsI/hqdefault.jpg)](https://www.youtube.com/watch?v=20B8trurlsI)
