import logging
import sys
import traceback
import uuid
import os
import tempfile
import time

from selenium import webdriver
from selenium.common.exceptions import (
    WebDriverException,
    ElementNotInteractableException,
    TimeoutException,
    StaleElementReferenceException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from mcp.server.fastmcp import FastMCP

log_filename = os.path.join(tempfile.gettempdir(), "mcp_browser_use.log") # change to temp dir
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(sys.stderr),  # Also log to stderr
    ],
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("selenium")

# Store browser sessions
browser_sessions = {}


@mcp.tool()
async def start_browser(headless: bool = False) -> str:
    """
    Starts a new browser session.

    This function initializes a new Chrome browser instance using Selenium WebDriver.

    Args:
        headless (bool, optional): If True, the browser will run in headless mode (without a visible window). Defaults to False.

    Returns:
        str: A message indicating the session was created successfully, along with the session ID.
             Returns an error message if the browser fails to start.
    """
    try:
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=chrome_options)
        session_id = str(uuid.uuid4())
        browser_sessions[session_id] = driver

        logger.info(f"Browser session created successfully. Session ID: {session_id}")
        return f"Browser session created successfully. Session ID: {session_id}"
    except Exception as e:
        logger.error(f"Error starting browser: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Error starting browser: {str(e)}"
@mcp.tool()
async def navigate(session_id: str, url: str) -> str:
    """
    Navigates the browser to a specified URL.

    This function loads a web page in the browser session.

    Args:
        session_id (str): The ID of the browser session.
        url (str): The URL to navigate to.

    Returns:
        str: A message indicating successful navigation, along with the page title and HTML.
             Returns an error message if navigation fails or if the session ID is invalid.
    """
    if session_id not in browser_sessions:
        logger.error(f"Session {session_id} not found.")
        return f"Session {session_id} not found. Please start a new browser session."

    driver = browser_sessions[session_id]

    try:
        driver.get(url)
        time.sleep(2)  # Allow page to load

        logger.info(f"Navigated to {url}. Title: {driver.title}")
        return f"Navigated to {url}\nTitle: {driver.title}\nHTML: {driver.page_source}"
    except Exception as e:
        logger.error(f"Error navigating to {url}: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Error navigating to {url}: {str(e)}"

def find_element(driver, selector, selector_type, timeout=10, visible_only=False, iframe_selector=None, iframe_selector_type="css", shadow_root_selector = None, shadow_root_selector_type="css"):
    """Helper function to find an element, handling iframes and shadow roots."""
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
          original_driver.switch_to.default_content() #switch back to the main document.

      return element

    except TimeoutException:
      if iframe_selector:
        original_driver.switch_to.default_content()
      raise
    except Exception as e:
      if iframe_selector:
        original_driver.switch_to.default_content()
      raise e

@mcp.tool()
async def click_element(session_id: str, selector: str, selector_type: str = "css", timeout: int = 10, force_js: bool = False, iframe_selector: str = None, iframe_selector_type: str = "css", shadow_root_selector: str = None, shadow_root_selector_type: str = "css") -> str:
    """
    Clicks an element on the web page, with iframe and shadow root support.

    This function locates and clicks a specified element.

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
             Returns an error message if the element is not found, not clickable, or if the session ID is invalid.
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
        # This can help with elements that have event listeners that depend on typing
        for char in text:
            element.send_keys(char)
            time.sleep(0.01)  # Small delay between characters
        
        # Trigger change event to ensure field updates properly
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", element)
        
        return f"Entered text '{text}' into element matching '{selector}'\nCurrent URL: {driver.current_url}\nTitle: {driver.title}"
    except TimeoutException:
        return f"Timeout waiting for element matching '{selector}' to be clickable"
    except Exception as e:
        return f"Error entering text: {str(e)}"

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
        
        return f"Sent key '{key}' to {'element matching ' + selector if selector else 'active element'}\nCurrent URL: {driver.current_url}\nTitle: {driver.title}\nHTML: {driver.page_source}"
    except Exception as e:
        return f"Error sending key: {str(e)}"

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
        
        return f"Scrolled by x={x}, y={y}\nCurrent URL: {driver.current_url}\nTitle: {driver.title}\nHTML: {driver.page_source}"
    except Exception as e:
        return f"Error scrolling: {str(e)}"

import tempfile
import os

@mcp.tool()
async def take_screenshot(
        session_id: str,
        screenshot_path: str = None,
    ) -> str:
    """Take a screenshot of the current page.

    Passing the screenshot as base64 to the client is not yet supported
    by MCP, so this function cannot do that.
    
    Args:
        session_id: Session ID of the browser
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."
    
    driver = browser_sessions[session_id]
    
    try:
        # Create a default path if none is provided
        if not screenshot_path:
            temp_dir = tempfile.gettempdir()
            screenshot_path = os.path.join(temp_dir, f"screenshot_{session_id}.png")
        
        # Save the screenshot
        driver.save_screenshot(screenshot_path)
        
        return f"Screenshot saved to {screenshot_path}"
    except Exception as e:
        return f"Error taking screenshot: {str(e)}"

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
        del browser_sessions[session_id]
        
        return f"Session {session_id} closed successfully"
    except Exception as e:
        return f"Error closing session: {str(e)}"

def find_element(driver, selector, selector_type, timeout=10, visible_only=False, iframe_selector=None, iframe_selector_type="css", shadow_root_selector = None, shadow_root_selector_type="css"):
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
            original_driver.switch_to.default_content() #switch back to the main document.

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
        return f"Error waiting for element: {str(e)}"

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
            return f"Element not found: {str(e)}"
            
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
        return f"Error debugging element: {str(e)}"


if __name__ == "__main__":
    try:
        logger.info("Starting Selenium MCP server...")
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"MCP Server Error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)