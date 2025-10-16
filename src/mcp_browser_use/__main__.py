import os
import sys
import time
import uuid
import logging
import traceback
import tempfile
import platform
import subprocess
import psutil
import shutil
import random
from pathlib import Path

import selenium
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    WebDriverException,
    ElementNotInteractableException,
    TimeoutException,
    StaleElementReferenceException,
    SessionNotCreatedException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from mcp.server.fastmcp import FastMCP


"""
Maybe use this. But run in headed mode, not headless.

class ChromeCustomProfileLoader:
    '''Launch ChromeDriver against a custom profile location.'''

    @staticmethod
    def launch_with_custom_profile(
        custom_data_dir: str, # The path to the custom user data directory
        profile_folder: str = "Default", # The profile folder name within the custom dir
        is_headless: bool = False,
        is_force_custom_profile: bool = True
    ) -> webdriver.Chrome:
        print(f"Using custom user data directory: {custom_data_dir}")
        print(f"Targeting profile folder: {profile_folder}")

        options = webdriver.ChromeOptions()

        options.add_argument(f"--user-data-dir={custom_data_dir}")
        options.add_argument(f"--profile-directory={profile_folder}") # This should now load the copied Default profile
        options.add_argument("--no-proxy-server")
        options.add_argument("--no-sandbox") # options.add_argument("--disable-dev-shm-usage")

        # Optional: Keep logging enabled for troubleshooting if needed
        log_directory = os.path.join(os.path.expanduser("~"), "Documents")
        log_file = os.path.join(log_directory, f"chromedriver_custom_{profile_folder}_log.txt")
        service_args = ['--verbose', f'--log-path={log_file}'] # print(f"ChromeDriver service args: {service_args}") # Keep commented unless needed for debugging # print(f"Logging to: {log_file}") # Keep commented unless needed for debugging

        # Optional: Enable Chrome internal verbose logging (might create chrome_debug.log)
        options.add_argument("--verbose")


        if is_headless:
            options.add_argument("--headless=new")

        print(f"Chrome Options being used: {options.arguments}")

        try:
            chrome_driver_path = ChromeDriverManager().install()
            # print(f"Using ChromeDriver at: {chrome_driver_path}") # Keep commented unless needed

            service = Service(executable_path=chrome_driver_path)#, service_args=service_args) # Keep service_args commented unless needed

            print(f"Attempting to launch Chrome with custom profile at {custom_data_dir}...")
            # Add a small delay before initiating the session - important for extensions
            time.sleep(1)

            driver = webdriver.Chrome(service=service, options=options)
            print(f"Chrome launched successfully with custom profile!")
            return driver
        except Exception as e:
            print(f"Failed to launch Chrome with custom profile: {e}")
            if not is_force_custom_profile:
                options = webdriver.ChromeOptions()

                options.add_argument(f"--user-data-dir={custom_data_dir}")
                options.add_argument(f"--profile-directory={profile_folder}") # This should now load the copied Default profile
                options.add_argument("--no-proxy-server")
                options.add_argument("--no-sandbox") # options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--headless=new")
                driver = webdriver.Chrome(service=service, options=options)
                return driver

            else:
                # print(f"Check the ChromeDriver log file at {log_file} for details.") # Keep commented unless needed
                # print("Also check for Chrome internal log files (e.g., chrome_debug.log in the custom data dir or temp).") # Keep commented
                raise # Re-raise the exception

"""


# --- Logging Configuration ---
LOG_FILE = Path(os.getcwd()) / "selenium_mcp_log.log"
if not LOG_FILE.exists():
    LOG_FILE.touch()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
    ],
    force=True
)

log_filename = os.path.join(tempfile.gettempdir(), "mcp_browser_use.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("selenium")

# Store browser sessions
browser_sessions = {}
browser_temp_dirs = {}
browser_log_paths = {}


def remove_unwanted_tags(html_content):
    """Remove specific tags (<script>, <style>, <meta>, <link>, <noscript>) from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove specified tags
    for tag in soup.find_all(['script', 'style', 'meta', 'link', 'noscript']):
        tag.extract()

    # Getting the text and stripping whitespace.
    return ' '.join(str(soup).split())


def get_cleaned_html(driver):
    """Get cleaned HTML content without script tags."""
    html_content = driver.page_source
    # Remove script tags
    cleaned_html = remove_unwanted_tags(html_content)
    return cleaned_html


def cleanup_old_temp_dirs():
    """Clean up old temporary directories that might have been left behind."""
    temp_root = tempfile.gettempdir()
    current_time = time.time()
    max_age = 24 * 3600  # 24 hours in seconds

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
    """Kill any existing Chrome and ChromeDriver processes"""
    for proc in psutil.process_iter(['name']):
        try:
            # Check for both Chrome and ChromeDriver processes
            if proc.info['name'] in ['chrome', 'chromedriver', 'Google Chrome']:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    time.sleep(2)  # Give processes time to fully terminate


def cleanup_chrome_tmp_files():
    """Clean up Chrome temporary files and directories"""
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


def get_by_selector(selector_type):
    """Helper function to get the appropriate By selector"""
    selectors = {
        'css': By.CSS_SELECTOR,
        'xpath': By.XPATH,
        'id': By.ID,
        'name': By.NAME,
        'tag': By.TAG_NAME,
        'class': By.CLASS_NAME,
        'link_text': By.LINK_TEXT,
        'partial_link_text': By.PARTIAL_LINK_TEXT
    }
    return selectors.get(selector_type.lower())


def find_element(driver, selector, selector_type, timeout=10, visible_only=False, iframe_selector=None, iframe_selector_type="css", shadow_root_selector=None, shadow_root_selector_type="css"):
    """
    Finds a web element using various selectors, handling iframes and shadow roots.

    This helper function locates an element on a web page, optionally within an iframe or shadow root.

    Args:
        driver (WebDriver): The Selenium WebDriver instance.
        selector (str): The selector string (e.g., CSS selector, XPath).
        selector_type (str): The type of selector ('css', 'xpath', 'id', etc.).
        timeout (int, optional): Maximum time to wait for the element in seconds. Defaults to 10.
        visible_only (bool, optional): If True, waits for the element to be visible. Defaults to False.
        iframe_selector (str, optional): Selector for the iframe containing the element. Defaults to None.
        iframe_selector_type (str, optional): Selector type for the iframe. Defaults to 'css'.
        shadow_root_selector (str, optional): Selector for the shadow root containing the element. Defaults to None.
        shadow_root_selector_type (str, optional): Selector type for the shadow root. Defaults to 'css'.

    Returns:
        WebElement: The found WebElement.

    Raises:
        TimeoutException: If the element is not found within the timeout.
        ValueError: If an unsupported selector type is provided.
        Exception: If any other error occurs during element finding.
    """
    try:
        original_driver = driver
        if iframe_selector:
            by_iframe = get_by_selector(iframe_selector_type)
            iframe = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by_iframe, iframe_selector))
            )
            driver = driver.switch_to.frame(iframe)

        if shadow_root_selector:
            by_shadow_root = get_by_selector(shadow_root_selector_type)
            shadow_host = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by_shadow_root, shadow_root_selector))
            )
            shadow_root = shadow_host.shadow_root
            driver = shadow_root

        by_selector = get_by_selector(selector_type)

        if not by_selector:
            raise ValueError(f"Unsupported selector type: {selector_type}")

        wait = WebDriverWait(driver, timeout)

        if visible_only:
            element = wait.until(EC.visibility_of_element_located((by_selector, selector)))
        else:
            element = wait.until(EC.presence_of_element_located((by_selector, selector)))

        if iframe_selector or shadow_root_selector:
            original_driver.switch_to.default_content()

        return element

    except TimeoutException:
        if iframe_selector:
            original_driver.switch_to.default_content()
        logger.error(traceback.format_exc())
        raise
    except Exception as e:
        if iframe_selector:
            original_driver.switch_to.default_content()
        logger.error(traceback.format_exc())
        raise e


@mcp.tool()
async def start_browser(headless: bool = False, is_persistent_browser_session: bool = False) -> str:
    """
    Start Chrome with WSL2-specific configurations and without user-data-dir

    Args:
        headless (bool): If True, the browser will run in headless mode
        is_persistent_browser_session (bool): If True, uses persistent session (currently unused)

    Returns:
        str: Success message with session ID or error message
    """
    session_id = str(uuid.uuid4())
    chrome_options = Options()

    # Basic options without user-data-dir
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-popup-blocking")

    # WSL2-specific options
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-zygote")
    chrome_options.add_argument("--no-first-run")

    # Use temporary preferences instead of user-data-dir
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_experimental_option("prefs", {
        "profile.default_content_settings.popups": 0,
        "download.default_directory": "/tmp",
        "download.prompt_for_download": False
    })

    if headless:
        chrome_options.add_argument("--headless=new")

    # Create a unique log path
    log_path = os.path.join(tempfile.gettempdir(), f"chromedriver_{session_id}.log")
    service = ChromeService(log_path=log_path)
    browser_log_paths[session_id] = log_path

    try:
        # Add a retry mechanism
        max_retries = 3
        for attempt in range(max_retries):
            try:
                driver = webdriver.Chrome(service=service, options=chrome_options)
                browser_sessions[session_id] = driver
                logger.info(f"Browser session created successfully. Session ID: {session_id}")
                return f"Browser session created successfully. Session ID: {session_id}"
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Attempt {attempt + 1} failed, retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    raise
    except Exception as exc:
        error_msg = (
            f"=== CHROME LAUNCH ERROR ===\n"
            f"Session ID: {session_id}\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Python: {sys.version.split()[0]}\n"
            f"Selenium: {selenium.__version__}\n"
            f"Error Type: {type(exc).__name__}\n"
            f"Error Msg: {str(exc)}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        logging.error(error_msg)
        return error_msg


@mcp.tool()
async def get_browser_versions() -> str:
    """
    Return the installed Chrome and Chromedriver versions to verify compatibility.
    """
    try:
        # Get Chrome version
        chrome_version = (
            subprocess.check_output(["google-chrome", "--version"], stderr=subprocess.STDOUT)
            .decode()
            .strip()
        )
    except Exception as e:
        chrome_version = f"Error fetching Chrome version: {e}"

    try:
        # Get Chromedriver version
        driver = webdriver.Chrome()  # temporary driver just to query version
        chromedriver_version = driver.capabilities.get("browserVersion") or "<unknown>"
        driver.quit()
    except Exception as e:
        chromedriver_version = f"Error fetching Chromedriver version via Selenium: {e}"

    return f"{chrome_version}\nChromedriver (Selenium): {chromedriver_version}"


@mcp.tool()
async def navigate(session_id: str, url: str) -> str:
    """
    Navigates the browser to a specified URL.

    Args:
        session_id (str): The ID of the browser session.
        url (str): The URL to navigate to.

    Returns:
        str: A message indicating successful navigation, along with the page title and HTML.
    """
    if session_id not in browser_sessions:
        logger.error(f"Session {session_id} not found.")
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        driver.get(url)
        time.sleep(2)  # Allow page to load

        clean_html = get_cleaned_html(driver)

        return f"Navigated to {url}\nTitle: {driver.title}\nHTML: {clean_html}"
    except Exception as e:
        return f"Error navigating to {url}: {traceback.format_exc()}"


@mcp.tool()
async def click_element(session_id: str, selector: str, selector_type: str = "css", timeout: int = 10, force_js: bool = False, iframe_selector: str = None, iframe_selector_type: str = "css", shadow_root_selector: str = None, shadow_root_selector_type: str = "css") -> str:
    """
    Clicks an element on the web page, with iframe and shadow root support.

    Args:
        session_id (str): The ID of the browser session.
        selector (str): The selector for the element to click.
        selector_type (str, optional): The type of selector. Defaults to 'css'.
        timeout (int, optional): Maximum wait time for the element to be clickable. Defaults to 10.
        force_js (bool, optional): If True, uses JavaScript to click the element. Defaults to False.
        iframe_selector (str, optional): Selector for the iframe. Defaults to None.
        iframe_selector_type (str, optional): Selector type for the iframe. Defaults to 'css'.
        shadow_root_selector (str, optional): Selector for the shadow root. Defaults to None.
        shadow_root_selector_type (str, optional): Selector type for the shadow root. Defaults to 'css'.

    Returns:
        str: A message indicating successful click, along with the current URL and page title.
    """
    if session_id not in browser_sessions:
        logger.error(f"Session {session_id} not found.")
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        element = find_element(driver, selector, selector_type, timeout, iframe_selector=iframe_selector, iframe_selector_type=iframe_selector_type, shadow_root_selector=shadow_root_selector, shadow_root_selector_type=shadow_root_selector_type)

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)

        try:
            if not force_js:
                element.click()
            else:
                raise ElementNotInteractableException("Forcing JavaScript click")
        except (ElementNotInteractableException, StaleElementReferenceException):
            try:
                driver.execute_script("arguments[0].click();", element)
            except Exception as js_err:
                logger.error(f"JavaScript click failed: {js_err}")
                return f"Both native and JavaScript click attempts failed: {js_err}"

        logger.info(f"Clicked element matching '{selector}'. Current URL: {driver.current_url}")
        return f"Clicked element matching '{selector}'. Current URL: {driver.current_url}\nTitle: {driver.title}"
    except Exception as e:
        logger.error(f"Error clicking element: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Error clicking element: {str(e)}"


@mcp.tool()
async def read_chromedriver_log(session_id: str, lines: int = 50) -> str:
    """
    Fetch the first N lines of the Chromedriver log for debugging.

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


@mcp.tool()
async def fill_text(session_id: str, selector: str, text: str, selector_type: str = "css", clear_first: bool = True, timeout: int = 10) -> str:
    """Input text into an element.

    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the input field
        text: Text to enter into the field
        selector_type: Type of selector (css, xpath, id)
        clear_first: Whether to clear the field before entering text
        timeout: Maximum time to wait for the element in seconds
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        by_selector = get_by_selector(selector_type)
        wait = WebDriverWait(driver, timeout)

        element = wait.until(
            EC.element_to_be_clickable((by_selector, selector))
        )

        # Scroll element into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)

        if clear_first:
            # Clear using multiple methods to be thorough
            element.click()  # Focus the element
            element.clear()
            # For stubborn fields, use CTRL+A and Delete
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.DELETE)

        # Type the text character by character with a small delay
        for char in text:
            element.send_keys(char)
            time.sleep(0.01)  # Small delay between characters

        # Trigger change event to ensure field updates properly
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", element)

        return f"Entered text '{text}' into element matching '{selector}'\nCurrent URL: {driver.current_url}\nTitle: {driver.title}"
    except TimeoutException:
        return f"Timeout waiting for element matching '{selector}' to be clickable"
    except Exception as e:
        return f"Error entering text: {traceback.format_exc()}"


@mcp.tool()
async def send_keys(session_id: str, key: str, selector: str = None, selector_type: str = "css") -> str:
    """Send keyboard keys to the browser.

    Args:
        session_id: Session ID of the browser
        key: Key to send (e.g., ENTER, TAB, etc.)
        selector: CSS selector, XPath, or ID of the element to send keys to (optional)
        selector_type: Type of selector (css, xpath, id)
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        key_to_send = getattr(Keys, key.upper(), None)
        if key_to_send is None:
            return f"Invalid key: {key}"

        if selector:
            element = find_element(driver, selector, selector_type)
            element.send_keys(key_to_send)
        else:
            # Send to active element if no selector provided
            webdriver.ActionChains(driver).send_keys(key_to_send).perform()

        time.sleep(1)  # Allow time for action to complete

        clean_html = get_cleaned_html(driver)

        return f"Sent key '{key}' to {'element matching ' + selector if selector else 'active element'}\nCurrent URL: {driver.current_url}\nTitle: {driver.title}\nHTML: {clean_html}"
    except Exception as e:
        return f"Error sending key: {traceback.format_exc()}"


@mcp.tool()
async def scroll(session_id: str, x: int = 0, y: int = 500) -> str:
    """Scroll the page.

    Args:
        session_id: Session ID of the browser
        x: Horizontal scroll amount in pixels
        y: Vertical scroll amount in pixels
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        driver.execute_script(f"window.scrollBy({x}, {y});")

        time.sleep(1)  # Allow time for scroll action to complete
        clean_html = get_cleaned_html(driver)

        return f"Scrolled by x={x}, y={y}\nCurrent URL: {driver.current_url}\nTitle: {driver.title}\nHTML: {clean_html}"
    except Exception as e:
        return f"Error scrolling: {traceback.format_exc()}"


@mcp.tool()
async def take_screenshot(session_id: str, screenshot_path: str = None) -> str:
    """Take a screenshot of the current page.

    Args:
        session_id: Session ID of the browser
        screenshot_path: Optional path to save screenshot file
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        screenshot = driver.get_screenshot_as_base64()

        # Save screenshot to file if path is provided
        if screenshot_path:
            with open(screenshot_path, "wb") as f:
                f.write(driver.get_screenshot_as_png())

        # Truncate to maximum 10 characters
        try:
            screenshot = screenshot[:10] + "..."
        except Exception as e:
            screenshot = "Error truncating screenshot: " + str(e)

        return f"Screenshot taken successfully. Base64 data: {screenshot}"
    except Exception as e:
        return f"Error taking screenshot: {traceback.format_exc()}"


@mcp.tool()
async def close_browser(session_id: str) -> str:
    """Close a browser session.

    Args:
        session_id: Session ID of the browser to close
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found."

    try:
        driver = browser_sessions[session_id]
        driver.quit()

        # Clean up the temporary user data directory
        if session_id in browser_temp_dirs:
            user_data_dir = browser_temp_dirs[session_id]
            if os.path.exists(user_data_dir):
                shutil.rmtree(user_data_dir)
                del browser_temp_dirs[session_id]

        # Clean up log path reference
        if session_id in browser_log_paths:
            del browser_log_paths[session_id]

        del browser_sessions[session_id]

        return f"Session {session_id} closed successfully"
    except Exception as e:
        return f"Error closing session: {traceback.format_exc()}"


@mcp.tool()
async def wait_for_element(session_id: str, selector: str, selector_type: str = "css", timeout: int = 10, condition: str = "visible") -> str:
    """Wait for an element to be present, visible, or clickable.

    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait in seconds
        condition: What to wait for - 'present', 'visible', or 'clickable'
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        by_selector = get_by_selector(selector_type)
        wait = WebDriverWait(driver, timeout)

        if condition == "present":
            element = wait.until(EC.presence_of_element_located((by_selector, selector)))
        elif condition == "visible":
            element = wait.until(EC.visibility_of_element_located((by_selector, selector)))
        elif condition == "clickable":
            element = wait.until(EC.element_to_be_clickable((by_selector, selector)))
        else:
            return f"Invalid condition: {condition}. Use 'present', 'visible', or 'clickable'."

        return f"Element matching '{selector}' is now {condition}"
    except TimeoutException:
        return f"Timeout waiting for element matching '{selector}' to be {condition}"
    except Exception as e:
        return f"Error waiting for element: {traceback.format_exc()}"


@mcp.tool()
async def get_cookies(session_id: str) -> dict:
    """Get all cookies for the current session."""
    if session_id not in browser_sessions:
        return f"Session {session_id} not found."
    driver = browser_sessions[session_id]
    return driver.get_cookies()


@mcp.tool()
async def add_cookie(session_id: str, cookie: dict) -> str:
    """Add a cookie to the current session."""
    if session_id not in browser_sessions:
        return f"Session {session_id} not found."
    driver = browser_sessions[session_id]
    driver.add_cookie(cookie)
    return "Cookie added successfully."


@mcp.tool()
async def delete_cookie(session_id: str, name: str) -> str:
    """Delete a cookie by name."""
    if session_id not in browser_sessions:
        return f"Session {session_id} not found."
    driver = browser_sessions[session_id]
    driver.delete_cookie(name)
    return f"Cookie '{name}' deleted successfully."


@mcp.tool()
async def debug_element(session_id: str, selector: str, selector_type: str = "css") -> str:
    """Debug why an element might not be clickable or visible.

    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        by_selector = get_by_selector(selector_type)

        # First check if element exists
        try:
            element = driver.find_element(by_selector, selector)
        except Exception as e:
            return f"Element not found: {traceback.format_exc()}"

        # Get element properties
        is_displayed = element.is_displayed()
        is_enabled = element.is_enabled()
        tag_name = element.tag_name

        # Get CSS properties that might affect visibility
        css_properties = {}
        for prop in ['display', 'visibility', 'opacity', 'height', 'width', 'position', 'z-index']:
            css_properties[prop] = driver.execute_script(f"return window.getComputedStyle(arguments[0]).getPropertyValue('{prop}')", element)

        # Check if element is in viewport
        in_viewport = driver.execute_script("""
            var elem = arguments[0];
            var rect = elem.getBoundingClientRect();
            return (
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
            );
        """, element)

        # Check for overlapping elements
        is_covered = driver.execute_script("""
            var elem = arguments[0];
            var rect = elem.getBoundingClientRect();
            var centerX = rect.left + rect.width / 2;
            var centerY = rect.top + rect.height / 2;
            var element = document.elementFromPoint(centerX, centerY);
            return element !== elem;
        """, element)

        return f"""Debug info for element matching '{selector}':
- Tag name: {tag_name}
- Displayed: {is_displayed}
- Enabled: {is_enabled}
- In viewport: {in_viewport}
- Covered by another element: {is_covered}
- CSS properties: {css_properties}
"""
    except Exception as e:
        return f"Error debugging element: {traceback.format_exc()}"


if __name__ == "__main__":
    try:
        logger.info("Starting Selenium MCP server...")
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"MCP Server Error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
