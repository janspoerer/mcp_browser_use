
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


## Installation & Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/hd24-dev/mcp_browser_use.git
cd mcp_browser_use
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

### 2. Chrome setup (for `undetected-chromedriver` and `nodriver`)

Both Chrome-based engines require **Google Chrome** to be installed on your system. ChromeDriver is managed automatically by `chromedriver-autoinstaller` — you do not need to download it manually.

**macOS:**
```bash
# Install via Homebrew
brew install --cask google-chrome
```

**Ubuntu / Debian:**
```bash
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
    | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update && sudo apt install -y google-chrome-stable
```

**Windows:** Download and install Chrome from [google.com/chrome](https://www.google.com/chrome/).

After installing Chrome, verify the setup:
```bash
google-chrome --version      # Linux
# or
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version  # macOS
```

ChromeDriver will be downloaded automatically the first time a browser session starts.

#### Linux headless servers — Xvfb (virtual display)

Chrome-based engines need a display. On headless Linux servers (no GUI), use **Xvfb**:

```bash
sudo apt install -y xvfb

# Start a virtual display on screen :99
Xvfb :99 -screen 0 1920x1080x24 &

# Tell Chrome which display to use
export DISPLAY=:99
```

To make the display permanent across reboots, add it as a systemd service or run it in a `screen`/`tmux` session. The `export DISPLAY=:99` line should be in the same shell environment (or `.bashrc` / `.profile`) that launches the MCP server.

---

### 3. Camoufox setup

Camoufox is a **Firefox-based** browser with C++-level fingerprint spoofing. It requires a separate binary download on top of the Python package.

**Step 1 — install the Python package:**
```bash
pip install camoufox[geoip]
```

The `[geoip]` extra enables IP-based geolocation spoofing (recommended for Cloudflare bypass).

**Step 2 — download the Camoufox browser binary:**
```bash
python -m camoufox fetch
```

This downloads the patched Firefox binary (~100 MB) into the Python package's data directory. It only needs to be run once per environment.

**Verify the install:**
```bash
python -c "from camoufox.sync_api import Camoufox; print('Camoufox OK')"
```

#### Camoufox on Linux headless servers

Camoufox also needs a display on Linux. The same Xvfb setup described above works:

```bash
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
```

Always use `headless=False` with Camoufox when targeting Cloudflare-protected sites — Cloudflare Turnstile interactive checkboxes require a real visible window.

---

## Browser Engines

The `start_browser` tool supports three browser engines via the `driver` parameter:

| Engine | Description | Best For |
|--------|-------------|----------|
| `undetected-chromedriver` (default) | Chrome via patched Selenium driver | General-purpose stealth automation |
| `nodriver` | Chrome via direct CDP, no Selenium/WebDriver layer | Sites with aggressive bot detection |
| `camoufox` | **Firefox-based** with C++-level fingerprint spoofing (Playwright API internally) | **Cloudflare bypass, Turnstile challenges** |

### Choosing an engine

| Situation | Recommended engine |
|---|---|
| Default / most sites | `undetected-chromedriver` |
| Site blocks ChromeDriver | `nodriver` |
| Cloudflare / Turnstile challenge | `camoufox` |

### Parameters

`start_browser(driver, headless, locale)`

| Parameter | Default | Description |
|---|---|---|
| `driver` | `"undetected-chromedriver"` | Engine to use (see table above) |
| `headless` | `False` | Run without a visible window. Prefer `False` on all platforms and use Xvfb on Linux instead |
| `locale` | `"en-US"` | Browser locale, e.g. `"de-DE"`, `"fr-FR"` |

### When to use Camoufox

Use `driver="camoufox"` when:
- The site uses **Cloudflare** protection (Turnstile, JS challenges, "Just a moment..." pages)
- Other engines get blocked or return bot-detection pages
- You need Firefox fingerprinting instead of Chrome

```python
# Start a camoufox session for Cloudflare-protected sites
start_browser(driver="camoufox", headless=False, locale="de-DE")
```

**Note:** On Linux, always use `headless=False` and run inside Xvfb (virtual display). Camoufox with `headless=True` may not solve Cloudflare Turnstile interactive checkboxes — those require a real visible window for the user to click.

## Demo Video (YouTube)

[![Quick demo](https://img.youtube.com/vi/20B8trurlsI/hqdefault.jpg)](https://www.youtube.com/watch?v=20B8trurlsI)
