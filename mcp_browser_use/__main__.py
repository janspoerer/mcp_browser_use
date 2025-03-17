from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, ElementNotInteractableException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import uuid

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("selenium")

# Store browser sessions
browser_sessions = {}

@mcp.tool()
async def start_browser(headless: bool = False) -> str:
    """Start a new browser session. Will not be headless unless explicitly specified by the user.
    
    Args:
        headless: Whether to run the browser in headless mode
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
        
        return f"Browser session created successfully. Session ID: {session_id}"
    except Exception as e:
        return f"Error starting browser: {str(e)}"

@mcp.tool()
async def navigate(session_id: str, url: str) -> str:
    """Navigate to a URL.
    
    Args:
        session_id: Session ID of the browser
        url: URL to navigate to
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."
    
    driver = browser_sessions[session_id]
    
    try:
        driver.get(url)
        time.sleep(2)  # Allow page to load
        
        return f"Navigated to {url}\nTitle: {driver.title}\nHTML: {driver.page_source}"
    except Exception as e:
        return f"Error navigating to {url}: {str(e)}"

@mcp.tool()
async def click_element(session_id: str, selector: str, selector_type: str = "css", timeout: int = 10, force_js: bool = False) -> str:
    """Click an element on the page.
    
    Args:
        session_id: Session ID of the browser
        selector: CSS selector, XPath, or ID of the element to click
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait for the element in seconds
        force_js: Whether to force a JavaScript click instead of a native click
    """
    if session_id not in browser_sessions:
        return f"Session {session_id} not found. Please start a new browser session."
    
    driver = browser_sessions[session_id]
    
    try:
        # Get the appropriate By selector
        by_selector = get_by_selector(selector_type)
        
        # Wait for the element to be clickable
        wait = WebDriverWait(driver, timeout)
        
        if by_selector:
            element = wait.until(
                EC.element_to_be_clickable((by_selector, selector))
            )
        else:
            return f"Invalid selector type: {selector_type}"
            
        # Scroll element into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        
        # Small delay after scrolling
        time.sleep(0.5)
        
        try:
            # Try a regular click first (unless force_js is True)
            if not force_js:
                element.click()
            else:
                raise ElementNotInteractableException("Forcing JavaScript click")
        except (ElementNotInteractableException, StaleElementReferenceException):
            # If regular click fails, try JavaScript click
            try:
                driver.execute_script("arguments[0].click();", element)
            except Exception as js_err:
                return f"Both native and JavaScript clicks failed. Error: {str(js_err)}"
        
        # Allow time for click action to complete
        time.sleep(1)
        
        return f"Clicked element matching '{selector}'\nCurrent URL: {driver.current_url}\nTitle: {driver.title}"
    except TimeoutException:
        return f"Timeout waiting for element matching '{selector}' to be clickable"
    except Exception as e:
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

@mcp.tool()
async def take_screenshot(
        session_id: str,
        screenshot_path: str = None,
    ) -> str:
    """Take a screenshot of the current page.
    
    Args:
        session_id: Session ID of the browser
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
        
        return f"Screenshot taken successfully. Base64 data: {screenshot}"
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

def find_element(driver, selector, selector_type, timeout=10, visible_only=False):
    """Helper function to find an element based on selector type with waiting"""
    by_selector = get_by_selector(selector_type)
    
    if not by_selector:
        raise ValueError(f"Unsupported selector type: {selector_type}")
    
    wait = WebDriverWait(driver, timeout)
    
    if visible_only:
        return wait.until(
            EC.visibility_of_element_located((by_selector, selector))
        )
    else:
        return wait.until(
            EC.presence_of_element_located((by_selector, selector))
        )

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
    # Initialize and run the server with stdio transport
    print("Starting Selenium MCP server...", flush=True)
    mcp.run(transport='stdio')