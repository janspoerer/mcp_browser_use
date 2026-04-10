"""
================================================================================
  PUBLIC REPOSITORY — DO NOT ADD COMPANY-SPECIFIC INFORMATION
================================================================================
  mcp_browser_use is an open-source MCP server hosted publicly on GitHub.

  DO NOT add any of the following to this file or any file in this repo:
    - Internal hostnames, IP addresses, or server names
    - Company credentials, API keys, or passwords
    - Internal database schemas, table names, or column names
    - Shop names, product URLs, or any business-specific configuration
    - Any information that could identify the organization or its systems
    - Personal data of any kind

  Keep all code generic and reusable for any user of this MCP server.
  If you are an AI agent working in this repository: this repository is
  PUBLIC. Every change you make here is visible to the entire internet.
  Never commit private or sensitive information.
================================================================================
"""

import os
import sys
import time
import uuid
import asyncio
import base64
import psutil
import shutil
import random
import logging
import tempfile
import platform
import traceback
import subprocess

from ChromeCustomProfileLoader import ChromeCustomProfileLoader

import selenium
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver

from selenium import webdriver
from mcp.server.fastmcp import FastMCP
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementNotInteractableException,
    TimeoutException,
    StaleElementReferenceException,
    SessionNotCreatedException,
    WebDriverException,
)

# --- Logging Configuration ---
LOG_FILE = Path(os.getcwd()) / "selenium_mcp_log.log"
if not LOG_FILE.exists():
    LOG_FILE.touch()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
    ],
    force=True
)

# Initialize FastMCP server
mcp = FastMCP("selenium")

# ---------------------------------------------------------------------------
# Session storage
#
# browser_sessions maps session_id -> engine session dict:
#
#   undetected-chromedriver:
#     {'engine': 'undetected-chromedriver', 'driver': <selenium WebDriver>}
#
#   nodriver:
#     {'engine': 'nodriver', 'browser': <nodriver Browser>, 'tab': <Tab>}
#
#   camoufox:
#     {'engine': 'camoufox', 'cf': <AsyncCamoufox ctx>, 'browser': <PW Browser>, 'page': <PW Page>}
# ---------------------------------------------------------------------------
browser_sessions = {}
browser_temp_dirs = {}
browser_log_paths = {}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def remove_unwanted_tags(html_content):
    """Remove script/style/meta/link/noscript tags from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup.find_all(['script', 'style', 'meta', 'link', 'noscript']):
        tag.extract()
    return ' '.join(str(soup).split())


def get_cleaned_html(driver):
    """Return cleaned HTML from a Selenium WebDriver."""
    return remove_unwanted_tags(driver.page_source)


def cleanup_old_temp_dirs():
    """Remove stale selenium_profile_ temp dirs older than 24 h."""
    temp_root = tempfile.gettempdir()
    current_time = time.time()
    max_age = 24 * 3600
    for item in os.listdir(temp_root):
        if item.startswith("selenium_profile_"):
            item_path = os.path.join(temp_root, item)
            try:
                if os.path.isdir(item_path):
                    stat = os.stat(item_path)
                    if current_time - stat.st_mtime > max_age:
                        shutil.rmtree(item_path, ignore_errors=True)
                        logging.info(f"Cleaned up old temp directory: {item_path}")
            except Exception as e:
                logging.warning(f"Failed to check/clean temp dir {item_path}: {e}")


def kill_chrome_processes():
    """Kill any existing Chrome and ChromeDriver processes."""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] in ['chrome', 'chromedriver', 'Google Chrome']:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    time.sleep(2)


def cleanup_chrome_tmp_files():
    """Clean up Chrome temporary files and directories."""
    tmp_dir = tempfile.gettempdir()
    patterns = ['selenium_profile_*', 'chromedriver_*']
    for pattern in patterns:
        for item in Path(tmp_dir).glob(pattern):
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            except Exception as e:
                logging.warning(f"Failed to remove {item}: {e}")


def _find_google_chrome() -> str:
    """Return path to a real Google Chrome binary, or None."""
    candidates = [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/chrome",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    # Last resort: Playwright Chromium (less stealthy)
    import glob as _glob
    pw = sorted(_glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))
    return pw[-1] if pw else None


def _sess(session_id: str):
    """Return the session dict or raise KeyError."""
    if session_id not in browser_sessions:
        raise KeyError(f"Session {session_id} not found. Please start a new browser session.")
    return browser_sessions[session_id]


# ---------------------------------------------------------------------------
# start_browser
# ---------------------------------------------------------------------------

@mcp.tool()
async def start_browser(
    headless: bool = False,
    driver: str = "undetected-chromedriver",
    locale: str = "en-US",
    is_persistent_browser_session: bool = False,
) -> str:
    """
    Start a browser session for web automation.

    Args:
        headless: Run the browser without a visible window.
                  For anti-bot bypass, prefer False — on Linux use Xvfb instead.
        driver: Browser engine to use. Options:
                  - "undetected-chromedriver" (default): Chrome via patched
                    Selenium driver. Good general-purpose stealth option.
                  - "nodriver": Chrome via direct CDP without Selenium/WebDriver
                    layer. Lower detection surface than undetected-chromedriver.
                    Best for sites with aggressive bot detection.
                  - "camoufox": Firefox-based browser with C++-level fingerprint
                    spoofing. Excellent Cloudflare bypass rates. Uses Playwright
                    API internally.
        locale: Browser locale string (e.g. "en-US", "de-DE"). Affects
                navigator.language and Accept-Language headers.
        is_persistent_browser_session: Unused; kept for API compatibility.

    Returns:
        Session ID string on success, or an error message.
    """
    session_id = str(uuid.uuid4())
    log_path = os.path.join(tempfile.gettempdir(), f"browser_{session_id}.log")
    browser_log_paths[session_id] = log_path

    logging.info(f"Starting browser session {session_id} with engine={driver}, headless={headless}, locale={locale}")

    try:
        if driver == "undetected-chromedriver":
            await _start_undetected_chromedriver(session_id, headless, locale)
        elif driver == "nodriver":
            await _start_nodriver(session_id, headless, locale)
        elif driver == "camoufox":
            await _start_camoufox(session_id, headless, locale)
        else:
            return (
                f"Unknown driver '{driver}'. "
                "Choose from: 'undetected-chromedriver', 'nodriver', 'camoufox'."
            )
    except Exception as e:
        logging.error(f"Error starting browser (engine={driver}): {traceback.format_exc()}")
        return f"Error starting browser with engine '{driver}': {e}"

    return (
        f"Session {session_id} started successfully.\n"
        f"Engine: {driver}\n"
        f"Headless: {headless}\n"
        f"Locale: {locale}\n"
        f"Log path: {log_path}"
    )


async def _start_undetected_chromedriver(session_id: str, headless: bool, locale: str):
    import undetected_chromedriver as uc

    temp_dir = tempfile.mkdtemp(prefix="selenium_profile_")
    browser_temp_dirs[session_id] = temp_dir

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument(f"--user-data-dir={temp_dir}")
    chrome_options.add_argument(f"--lang={locale}")

    if platform.system() != "Windows":
        chrome_binary = os.environ.get("CHROME_BINARY") or _find_google_chrome()
        if chrome_binary:
            chrome_options.binary_location = chrome_binary
            logging.info(f"Using Chrome binary: {chrome_binary}")

    chrome_major = None
    try:
        binary = chrome_options.binary_location or "google-chrome"
        ver_out = subprocess.check_output([binary, "--version"], text=True, stderr=subprocess.DEVNULL).strip()
        chrome_major = int(ver_out.split()[-1].split(".")[0])
        logging.info(f"Detected Chrome major version: {chrome_major}")
    except Exception as e:
        logging.warning(f"Could not detect Chrome version: {e}")

    drv = uc.Chrome(
        options=chrome_options,
        headless=headless,
        use_subprocess=True,
        version_main=chrome_major,
    )

    # Patch navigator via CDP for extra stealth
    lang_list = [locale, locale.split("-")[0], "en-US", "en"] if not locale.startswith("en") else [locale, "en"]
    drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": f"""
            Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});
            Object.defineProperty(navigator, 'plugins', {{get: () => [1, 2, 3, 4, 5]}});
            Object.defineProperty(navigator, 'languages', {{get: () => {lang_list}}});
            if (!window.chrome) window.chrome = {{runtime: {{}}}};
        """
    })
    drv.get("about:blank")
    time.sleep(1)

    browser_sessions[session_id] = {'engine': 'undetected-chromedriver', 'driver': drv}
    logging.info(f"undetected-chromedriver session {session_id} started.")


async def _start_nodriver(session_id: str, headless: bool, locale: str):
    import nodriver as uc

    lang = locale  # e.g. "de-DE"
    browser = await uc.start(
        headless=headless,
        lang=lang,
        browser_args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1920,1080",
            f"--lang={lang}",
        ],
    )
    tab = await browser.get("about:blank")
    browser_sessions[session_id] = {'engine': 'nodriver', 'browser': browser, 'tab': tab}
    logging.info(f"nodriver session {session_id} started.")


async def _start_camoufox(session_id: str, headless: bool, locale: str):
    from camoufox.async_api import AsyncCamoufox

    cf = AsyncCamoufox(
        headless=headless,
        geoip=True,
        os=["windows", "macos", "linux"],
    )
    browser = await cf.__aenter__()
    page = await browser.new_page()
    browser_sessions[session_id] = {'engine': 'camoufox', 'cf': cf, 'browser': browser, 'page': page}
    logging.info(f"camoufox session {session_id} started.")


# ---------------------------------------------------------------------------
# get_browser_versions
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_browser_versions() -> str:
    """Return installed Chrome and ChromeDriver versions to verify compatibility."""
    try:
        chrome_version = subprocess.check_output(
            ["google-chrome", "--version"], stderr=subprocess.STDOUT
        ).decode().strip()
    except Exception as e:
        chrome_version = f"Error fetching Chrome version: {e}"

    try:
        drv = webdriver.Chrome()
        chromedriver_version = drv.capabilities.get("browserVersion") or "<unknown>"
        drv.quit()
    except Exception as e:
        chromedriver_version = f"Error fetching ChromeDriver version: {e}"

    return f"{chrome_version}\nChromeDriver (Selenium): {chromedriver_version}"


# ---------------------------------------------------------------------------
# navigate
# ---------------------------------------------------------------------------

@mcp.tool()
async def navigate(session_id: str, url: str) -> str:
    """Navigate to a URL. Returns only the page title (not the full HTML).
    Use execute_js() to extract specific data from the page after navigating.

    Args:
        session_id: Session ID of the browser
        url: URL to navigate to
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'undetected-chromedriver':
            drv = sess['driver']
            drv.get(url)
            time.sleep(2)
            return f"Navigated to {url}\nTitle: {drv.title}"

        elif engine == 'nodriver':
            browser = sess['browser']
            tab = await browser.get(url)
            sess['tab'] = tab  # update current tab
            await asyncio.sleep(2)
            return f"Navigated to {url}\nTitle: {tab.title}"

        elif engine == 'camoufox':
            page = sess['page']
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            title = await page.title()
            return f"Navigated to {url}\nTitle: {title}"

    except Exception:
        return f"Error navigating to {url}: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# execute_js
# ---------------------------------------------------------------------------

@mcp.tool()
async def execute_js(session_id: str, script: str) -> str:
    """Execute JavaScript in the browser and return the result.

    Use this to extract structured data from the current page.
    The script should return a value (use 'return ...' in the script).

    Example: Extract all product names:
        script: "return Array.from(document.querySelectorAll('.product-name')).map(el => el.textContent.trim())"

    Args:
        session_id: Session ID of the browser
        script: JavaScript code to execute. Must use 'return' to return data.
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        import json as _json

        if engine == 'undetected-chromedriver':
            result = sess['driver'].execute_script(script)

        elif engine == 'nodriver':
            # nodriver evaluate does not need 'return'; strip it
            js = script.strip()
            if js.startswith("return "):
                js = js[len("return "):]
            result = await sess['tab'].evaluate(js)

        elif engine == 'camoufox':
            # Playwright evaluate does not need 'return'; strip it
            js = script.strip()
            if js.startswith("return "):
                js = js[len("return "):]
            result = await sess['page'].evaluate(js)

        if result is None:
            return "Script executed successfully (returned null/undefined)."
        try:
            return _json.dumps(result, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(result)

    except Exception:
        return f"Error executing script: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# click_element
# ---------------------------------------------------------------------------

@mcp.tool()
async def click_element(
    session_id: str,
    selector: str,
    selector_type: str = "css",
    timeout: int = 10,
    force_js: bool = False,
) -> str:
    """Click an element on the page.

    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the element to click
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait for the element in seconds
        force_js: Whether to force a JavaScript click instead of a native click
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'undetected-chromedriver':
            drv = sess['driver']
            by_selector = get_by_selector(selector_type)
            wait = WebDriverWait(drv, timeout)
            element = wait.until(EC.element_to_be_clickable((by_selector, selector)))
            drv.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            try:
                if not force_js:
                    element.click()
                else:
                    raise ElementNotInteractableException("Forcing JavaScript click")
            except (ElementNotInteractableException, StaleElementReferenceException):
                drv.execute_script("arguments[0].click();", element)
            time.sleep(1)
            return f"Clicked element matching '{selector}'\nCurrent URL: {drv.current_url}\nTitle: {drv.title}"

        elif engine == 'nodriver':
            tab = sess['tab']
            element = await tab.find(selector, best_match=True, timeout=timeout)
            await element.click()
            await asyncio.sleep(1)
            return f"Clicked element matching '{selector}'\nCurrent URL: {tab.url}\nTitle: {tab.title}"

        elif engine == 'camoufox':
            page = sess['page']
            loc = page.locator(selector).first
            await loc.scroll_into_view_if_needed(timeout=timeout * 1000)
            await loc.click(timeout=timeout * 1000)
            title = await page.title()
            return f"Clicked element matching '{selector}'\nCurrent URL: {page.url}\nTitle: {title}"

    except TimeoutException:
        return f"Timeout waiting for element matching '{selector}' to be clickable."
    except Exception:
        return f"Error clicking element: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# read_chromedriver_log
# ---------------------------------------------------------------------------

@mcp.tool()
async def read_chromedriver_log(session_id: str, lines: int = 50) -> str:
    """Fetch the first N lines of the driver log for debugging.

    Args:
        session_id (str): Browser session ID.
        lines (int): Number of lines to return from the top of the log.
    """
    log_path = browser_log_paths.get(session_id)
    if not log_path or not os.path.exists(log_path):
        return f"No log found for session {session_id}. Expected at: {log_path}"

    output = []
    with open(log_path, "r", errors="ignore") as f:
        for _ in range(lines):
            line = f.readline()
            if not line:
                break
            output.append(line.rstrip("\n"))
    return "\n".join(output) or f"Log for session {session_id} is empty."


# ---------------------------------------------------------------------------
# fill_text
# ---------------------------------------------------------------------------

@mcp.tool()
async def fill_text(
    session_id: str,
    selector: str,
    text: str,
    selector_type: str = "css",
    clear_first: bool = True,
    timeout: int = 10,
) -> str:
    """Input text into an element.

    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the input field
        text: Text to enter into the field
        selector_type: Type of selector (css, xpath, id)
        clear_first: Whether to clear the field before entering text
        timeout: Maximum time to wait for the element in seconds
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'undetected-chromedriver':
            drv = sess['driver']
            by_selector = get_by_selector(selector_type)
            wait = WebDriverWait(drv, timeout)
            element = wait.until(EC.element_to_be_clickable((by_selector, selector)))
            drv.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            if clear_first:
                element.click()
                element.clear()
                element.send_keys(Keys.CONTROL + "a")
                element.send_keys(Keys.DELETE)
            for char in text:
                element.send_keys(char)
                time.sleep(0.01)
            drv.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", element)
            return f"Entered text '{text}' into element matching '{selector}'\nCurrent URL: {drv.current_url}\nTitle: {drv.title}"

        elif engine == 'nodriver':
            tab = sess['tab']
            element = await tab.find(selector, best_match=True, timeout=timeout)
            await element.clear_input()
            await element.send_keys(text)
            return f"Entered text '{text}' into element matching '{selector}'\nCurrent URL: {tab.url}\nTitle: {tab.title}"

        elif engine == 'camoufox':
            page = sess['page']
            loc = page.locator(selector).first
            if clear_first:
                await loc.clear(timeout=timeout * 1000)
            await loc.fill(text, timeout=timeout * 1000)
            title = await page.title()
            return f"Entered text '{text}' into element matching '{selector}'\nCurrent URL: {page.url}\nTitle: {title}"

    except TimeoutException:
        return f"Timeout waiting for element matching '{selector}' to be clickable"
    except Exception:
        return f"Error entering text: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# send_keys
# ---------------------------------------------------------------------------

@mcp.tool()
async def send_keys(
    session_id: str,
    key: str,
    selector: str = None,
    selector_type: str = "css",
) -> str:
    """Send keyboard keys to the browser.

    Args:
        session_id: Session ID of the browser
        key: Key to send (e.g., ENTER, TAB, ESCAPE, etc.)
        selector: CSS selector, XPath, or ID of the element (optional)
        selector_type: Type of selector (css, xpath, id)
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'undetected-chromedriver':
            drv = sess['driver']
            key_to_send = getattr(Keys, key.upper(), None)
            if key_to_send is None:
                return f"Invalid key: {key}"
            if selector:
                element = find_element(drv, selector, selector_type)
                element.send_keys(key_to_send)
            else:
                webdriver.ActionChains(drv).send_keys(key_to_send).perform()
            time.sleep(1)
            clean_html = get_cleaned_html(drv)
            return f"Sent key '{key}'\nCurrent URL: {drv.current_url}\nTitle: {drv.title}\nHTML: {clean_html}"

        elif engine == 'nodriver':
            tab = sess['tab']
            await tab.send_keys(key)
            await asyncio.sleep(1)
            return f"Sent key '{key}'\nCurrent URL: {tab.url}\nTitle: {tab.title}"

        elif engine == 'camoufox':
            page = sess['page']
            await page.keyboard.press(key)
            await asyncio.sleep(1)
            title = await page.title()
            return f"Sent key '{key}'\nCurrent URL: {page.url}\nTitle: {title}"

    except Exception:
        return f"Error sending key: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# scroll
# ---------------------------------------------------------------------------

@mcp.tool()
async def scroll(session_id: str, x: int = 0, y: int = 500) -> str:
    """Scroll the page.

    Args:
        session_id: Session ID of the browser
        x: Horizontal scroll amount in pixels
        y: Vertical scroll amount in pixels
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'undetected-chromedriver':
            drv = sess['driver']
            drv.execute_script(f"window.scrollBy({x}, {y});")
            time.sleep(1)
            clean_html = get_cleaned_html(drv)
            return f"Scrolled by x={x}, y={y}\nCurrent URL: {drv.current_url}\nTitle: {drv.title}\nHTML: {clean_html}"

        elif engine == 'nodriver':
            tab = sess['tab']
            if y > 0:
                await tab.scroll_down(y)
            elif y < 0:
                await tab.scroll_up(-y)
            await asyncio.sleep(1)
            return f"Scrolled by x={x}, y={y}\nCurrent URL: {tab.url}\nTitle: {tab.title}"

        elif engine == 'camoufox':
            page = sess['page']
            await page.mouse.wheel(x, y)
            await asyncio.sleep(1)
            title = await page.title()
            return f"Scrolled by x={x}, y={y}\nCurrent URL: {page.url}\nTitle: {title}"

    except Exception:
        return f"Error scrolling: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# click_at_coordinates
# ---------------------------------------------------------------------------

@mcp.tool()
async def click_at_coordinates(session_id: str, x: int, y: int) -> str:
    """Click at specific screen coordinates (pixels from top-left of browser viewport).

    Useful for interacting with elements that are not in the DOM (e.g. canvas, shadow DOM,
    Cloudflare Turnstile checkbox).

    Args:
        session_id: Session ID of the browser
        x: Horizontal pixel coordinate
        y: Vertical pixel coordinate
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'camoufox':
            page = sess['page']
            await page.mouse.click(x, y)
            await asyncio.sleep(1)
            title = await page.title()
            return f"Clicked at ({x}, {y})\nCurrent URL: {page.url}\nTitle: {title}"

        elif engine == 'undetected-chromedriver':
            drv = sess['driver']
            from selenium.webdriver import ActionChains
            ActionChains(drv).move_by_offset(x, y).click().perform()
            time.sleep(1)
            return f"Clicked at ({x}, {y})\nCurrent URL: {drv.current_url}\nTitle: {drv.title}"

        elif engine == 'nodriver':
            tab = sess['tab']
            await tab.evaluate(f"document.elementFromPoint({x}, {y})?.click()")
            await asyncio.sleep(1)
            return f"Clicked at ({x}, {y})\nCurrent URL: {tab.url}\nTitle: {tab.title}"

    except Exception:
        return f"Error clicking at ({x}, {y}): {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# take_screenshot
# ---------------------------------------------------------------------------

@mcp.tool()
async def take_screenshot(session_id: str, screenshot_path: str = None) -> str:
    """Take a screenshot of the current page.

    Args:
        session_id: Session ID of the browser
        screenshot_path: Optional file path to save the screenshot as PNG
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'undetected-chromedriver':
            drv = sess['driver']
            screenshot_b64 = drv.get_screenshot_as_base64()
            if screenshot_path:
                with open(screenshot_path, "wb") as f:
                    f.write(drv.get_screenshot_as_png())

        elif engine == 'nodriver':
            tab = sess['tab']
            tmp_path = screenshot_path or os.path.join(tempfile.gettempdir(), f"nodriver_{session_id}.png")
            await tab.save_screenshot(tmp_path)
            with open(tmp_path, "rb") as f:
                screenshot_b64 = base64.b64encode(f.read()).decode()
            if not screenshot_path:
                os.unlink(tmp_path)

        elif engine == 'camoufox':
            page = sess['page']
            png_bytes = await page.screenshot()
            screenshot_b64 = base64.b64encode(png_bytes).decode()
            if screenshot_path:
                with open(screenshot_path, "wb") as f:
                    f.write(png_bytes)

        # Truncate base64 for return value (full data in file if path given)
        try:
            screenshot_preview = screenshot_b64[:10] + "..."
        except Exception:
            screenshot_preview = "<error>"

        return f"Screenshot taken successfully. Base64 data: {screenshot_preview}"

    except Exception:
        return f"Error taking screenshot: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# mouse_click
# ---------------------------------------------------------------------------

@mcp.tool()
async def mouse_click(session_id: str, x: float, y: float) -> str:
    """Click at specific page coordinates (x, y) using the browser's mouse.

    Useful for interacting with elements that cannot be found via CSS/XPath selectors,
    such as Cloudflare Turnstile checkboxes rendered in isolated frames.

    Args:
        session_id: Session ID of the browser
        x: Horizontal coordinate in CSS pixels (relative to the viewport)
        y: Vertical coordinate in CSS pixels (relative to the viewport)
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'camoufox':
            page = sess['page']
            await page.mouse.click(x, y)
        elif engine == 'undetected-chromedriver':
            drv = sess['driver']
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(drv)
            actions.move_by_offset(int(x), int(y)).click().perform()
        elif engine == 'nodriver':
            tab = sess['tab']
            await tab.evaluate(f"document.elementFromPoint({x}, {y})?.click()")
        else:
            return f"mouse_click not supported for engine '{engine}'"

        return f"Clicked at ({x}, {y})"
    except Exception:
        return f"Error clicking at ({x}, {y}): {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# close_browser
# ---------------------------------------------------------------------------

@mcp.tool()
async def close_browser(session_id: str) -> str:
    """Close a browser session.

    Args:
        session_id: Session ID of the browser to close
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found."

    sess = browser_sessions[session_id]
    engine = sess.get('engine', 'undetected-chromedriver')

    try:
        if engine == 'undetected-chromedriver':
            sess['driver'].quit()

        elif engine == 'nodriver':
            sess['browser'].stop()

        elif engine == 'camoufox':
            try:
                await sess['cf'].__aexit__(None, None, None)
            except Exception as e:
                logging.warning(f"Error closing camoufox context: {e}")

        # Clean up temp dir
        if session_id in browser_temp_dirs:
            user_data_dir = browser_temp_dirs[session_id]
            if os.path.exists(user_data_dir):
                shutil.rmtree(user_data_dir, ignore_errors=True)
            del browser_temp_dirs[session_id]

        del browser_sessions[session_id]
        return f"Session {session_id} closed successfully"

    except Exception:
        return f"Error closing session: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# wait_for_element
# ---------------------------------------------------------------------------

@mcp.tool()
async def wait_for_element(
    session_id: str,
    selector: str,
    selector_type: str = "css",
    timeout: int = 10,
    condition: str = "visible",
) -> str:
    """Wait for an element to be present, visible, or clickable.

    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait in seconds
        condition: What to wait for - 'present', 'visible', or 'clickable'
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    try:
        if engine == 'undetected-chromedriver':
            drv = sess['driver']
            by_selector = get_by_selector(selector_type)
            wait = WebDriverWait(drv, timeout)
            if condition == "present":
                wait.until(EC.presence_of_element_located((by_selector, selector)))
            elif condition == "visible":
                wait.until(EC.visibility_of_element_located((by_selector, selector)))
            elif condition == "clickable":
                wait.until(EC.element_to_be_clickable((by_selector, selector)))
            else:
                return f"Invalid condition: {condition}. Use 'present', 'visible', or 'clickable'."
            return f"Element matching '{selector}' is now {condition}"

        elif engine == 'nodriver':
            tab = sess['tab']
            element = await tab.find(selector, best_match=True, timeout=timeout)
            return f"Element matching '{selector}' found" if element else f"Element matching '{selector}' not found within {timeout}s"

        elif engine == 'camoufox':
            page = sess['page']
            loc = page.locator(selector).first
            if condition in ("visible", "present"):
                await loc.wait_for(state="visible", timeout=timeout * 1000)
            elif condition == "clickable":
                await loc.wait_for(state="visible", timeout=timeout * 1000)
            return f"Element matching '{selector}' is now {condition}"

    except TimeoutException:
        return f"Timeout waiting for element matching '{selector}' to be {condition}"
    except Exception:
        return f"Error waiting for element: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# debug_element (Selenium/undetected-chromedriver only)
# ---------------------------------------------------------------------------

@mcp.tool()
async def debug_element(
    session_id: str,
    selector: str,
    selector_type: str = "css",
) -> str:
    """Debug why an element might not be clickable or visible.
    Currently supported for undetected-chromedriver sessions only.

    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
    """
    try:
        sess = _sess(session_id)
    except KeyError as e:
        return str(e)

    engine = sess['engine']
    if engine != 'undetected-chromedriver':
        return f"debug_element is only supported for undetected-chromedriver sessions (current engine: {engine})."

    drv = sess['driver']
    try:
        by_selector = get_by_selector(selector_type)
        try:
            element = drv.find_element(by_selector, selector)
        except Exception:
            return f"Element not found: {traceback.format_exc()}"

        is_displayed = element.is_displayed()
        is_enabled = element.is_enabled()
        tag_name = element.tag_name

        css_properties = {}
        for prop in ['display', 'visibility', 'opacity', 'height', 'width', 'position', 'z-index']:
            css_properties[prop] = drv.execute_script(
                f"return window.getComputedStyle(arguments[0]).getPropertyValue('{prop}')", element
            )

        in_viewport = drv.execute_script("""
            var elem = arguments[0];
            var rect = elem.getBoundingClientRect();
            return (
                rect.top >= 0 && rect.left >= 0 &&
                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
            );
        """, element)

        is_covered = drv.execute_script("""
            var elem = arguments[0];
            var rect = elem.getBoundingClientRect();
            var centerX = rect.left + rect.width / 2;
            var centerY = rect.top + rect.height / 2;
            var element = document.elementFromPoint(centerX, centerY);
            return element !== elem;
        """, element)

        return (
            f"Debug info for element matching '{selector}':\n"
            f"- Tag name: {tag_name}\n"
            f"- Displayed: {is_displayed}\n"
            f"- Enabled: {is_enabled}\n"
            f"- In viewport: {in_viewport}\n"
            f"- Covered by another element: {is_covered}\n"
            f"- CSS properties: {css_properties}\n"
        )
    except Exception:
        return f"Error debugging element: {traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_by_selector(selector_type):
    """Return the appropriate Selenium By selector."""
    selectors = {
        'css': By.CSS_SELECTOR,
        'xpath': By.XPATH,
        'id': By.ID,
        'name': By.NAME,
        'tag': By.TAG_NAME,
        'class': By.CLASS_NAME,
        'link_text': By.LINK_TEXT,
        'partial_link_text': By.PARTIAL_LINK_TEXT,
    }
    return selectors.get(selector_type.lower())


def find_element(driver, selector, selector_type, timeout=10, visible_only=False):
    """Find a Selenium element with waiting."""
    by_selector = get_by_selector(selector_type)
    if not by_selector:
        raise ValueError(f"Unsupported selector type: {selector_type}")
    wait = WebDriverWait(driver, timeout)
    if visible_only:
        return wait.until(EC.visibility_of_element_located((by_selector, selector)))
    else:
        return wait.until(EC.presence_of_element_located((by_selector, selector)))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    mcp.run(transport='stdio')
