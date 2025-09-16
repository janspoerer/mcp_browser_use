
# MCP Browser Use

[![Verified on MseeP](https://mseep.ai/badge.svg)](https://mseep.ai/app/9e05b912-08dc-41f5-b7fa-1087315883d5)

<img src="docs/mcp_browser_use_logo.jpg" alt="Description" width="300">


<br>
<br>
<br>

## What You Can Achieve With This MCP

This project aims to empower AI agents to perform web use, browser automation, scraping, and automation with Model Context Protocol (MCP) and Selenium.

The special feature of this MCP is that it can handle multiple agents accessing multiple browser **windows**. One does not need to start multiple Docker images, VMs, or computers to have multiple scraping agents. And one can still use **one single browser profile** across all agents. Each agent will have its own windows, and they will not interfere with each other.

_This makes the handling of multiple agents seamless: Just start as many agents as you want, and it will just work!_ Use two Claude Code instances, one Codex CLI instance, one Gemini CLI instance and a `fast-agent` instance -- all on one computer, all using the same browser profile, and all working (somewhat) in parallel.

> Our mission is to let AI agents complete any web task with minimal human supervision -- all based on natural language instructions.

## Feature Highlights

* **HTML Truncation:** The MCP allows you to configure truncation of the HTML pages. Other scraping MCPs may overwhelm the AI with accessibility snapshots or HTML dumps that are larger than the context window. This MCP will help you to manage the maximum page size by setting the `MCP_MAX_SNAPSHOT_CHARS` environment variable.
* **Multiple Browser Windows and Multiple Agents:** You can connect multiple agents to this MCP independently, without requiring coordination on behalf of the agents. Each agent can work with **the same** browser profile, which is helpful when logins should persist across agents. Each agent gets their own browser window, so they do not interfere with each other. Uses Chrome DevTools Protocol TargetId to identify browser windows.

## Known Limitations

* **Iframe Context:** Multi-step interactions within iframes require specifying `iframe_selector` for each action. Browser context resets after each tool call for reliability. For iframe workflows, repeat the iframe selector parameter in each `click_element`, `fill_text`, or `debug_element` call.

## Configuration / Installation

* We recommend using Chrome Canary or Chrome Beta. This will ensure that your AI agents will not interfere with your Chrome instance. While this MCP can handle an arbitrary number of agents to use a single Chrome executable, the MCP does require the instance to be started in developer mode. If you, as a normal human user, start your normal Chrome instance manually, the Chrome instance **won't be in developer mode**. This is a problem. Thus, allow you to use your Chrome browser normally, please just install Chrome Beta (recommended) or Chrome Canary (not recommended due to instability).
* After installing Chrome Beta, point to the Chrome Beta executable in the `.env` file as described below.
* Start the MCP server (if you do not know how to do this, check the section "How to Use (This) MCP below).

## How to Use (This) MCP

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

Click the hammer to see the available tools.

## `.env` Variables

```
CHROME_PROFILE_NAME=Selenium
CHROME_EXECUTABLE_PATH=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
CHROME_PROFILE_USER_DATA_DIR=/Users/janspoerer/Library/Application Support/Google/Chrome
CHROME_PROFILE_NAME=Profile 15
MCP_MAX_SNAPSHOT_CHARS=10000
```

## Available Tools


## Debugging

Check if the browser is running by visiting this URL in your main browser (not the automated browser):

```
http://127.0.0.1:9223/json/version
```

It will display something like this if the browser is running:

```
{
   "Browser": "Chrome/140.0.7339.24",
   "Protocol-Version": "1.3",
   "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
   "V8-Version": "14.0.365.3",
   "WebKit-Version": "537.36 (@f8765868e23d9ee5209061fc999f6495c525cd13)",
   "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/d8f511eb-947c-4eb1-833d-917212a92394"
}
```

## Demo Video (YouTube)

[![Quick demo](https://img.youtube.com/vi/20B8trurlsI/hqdefault.jpg)](https://www.youtube.com/watch?v=20B8trurlsI)



## Run Tests

We DO NOT want to use pytest-asyncio.

```
pip install -e ".[test]"`
```
