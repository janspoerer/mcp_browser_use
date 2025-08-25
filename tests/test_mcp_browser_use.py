import pytest
import asyncio
import uuid
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException,
    ElementNotInteractableException,
    StaleElementReferenceException
)


from mcp_browser_use.__main__ import (
    start_browser,
    navigate,
    click_element,
    fill_text,
    send_keys,
    scroll,
    take_screenshot,
    close_browser,
    wait_for_element,
    debug_element,
    get_cookies,
    add_cookie,
    delete_cookie,
    get_by_selector,
    find_element,
    remove_unwanted_tags,
    get_cleaned_html,
    browser_sessions,
    browser_temp_dirs,
    browser_log_paths
)

##
## We DO NOT want to use pytest-asyncio.
##

@pytest.fixture
def event_loop():
    asyncio.get_event_loop_policy().set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()

class TestMCPBrowserUse:
    """Test class for MCP Browser Use functionality"""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Clear browser sessions before each test
        browser_sessions.clear()
        browser_temp_dirs.clear()
        browser_log_paths.clear()

    def teardown_method(self):
        """Clean up after each test method."""
        # Clean up any remaining browser sessions
        browser_sessions.clear()
        browser_temp_dirs.clear()
        browser_log_paths.clear()


    @patch('mcp_browser_use.__main__.webdriver.Chrome')
    @patch('mcp_browser_use.__main__.ChromeService')
    def test_start_browser_success(self, mock_service, mock_chrome, event_loop):
        """Test successful browser startup"""
        mock_driver = Mock()
        mock_chrome.return_value = mock_driver

        result = event_loop.run_until_complete(
            start_browser(headless=False)
        )

        assert "Browser session created" in result
        assert "Session ID:" in result
        mock_chrome.assert_called_once()


    @patch('mcp_browser_use.__main__.webdriver.Chrome')
    def test_start_browser_headless(self, mock_chrome, event_loop):
        """Test browser startup in headless mode"""
        mock_driver = Mock()
        mock_chrome.return_value = mock_driver

        result = event_loop.run_until_complete(
            start_browser(headless=True)
        )

        assert "Browser session created" in result
        mock_chrome.assert_called_once()
        # Check if headless option was added
        args = mock_chrome.call_args[1]['options']
        assert "--headless=new" in str(args.arguments)


    @patch('mcp_browser_use.__main__.webdriver.Chrome')
    def test_start_browser_failure(self, mock_chrome, event_loop):
        """Test browser startup failure"""
        mock_chrome.side_effect = Exception("Chrome failed to start")

        result = event_loop.run_until_complete(
            start_browser()
        )

        assert "CHROME LAUNCH ERROR" in result

    def test_navigate_invalid_session(self, event_loop):
        """Test navigation with invalid session ID"""
        result = event_loop.run_until_complete(
            navigate("invalid-session", "https://example.com")
        )

        assert "Session invalid-session not found" in result

    @patch('mcp_browser_use.__main__.get_cleaned_html')
    def test_navigate_success(self, mock_get_cleaned_html, event_loop):
        """Test successful navigation"""
        # Set up mock driver
        mock_driver = Mock()
        mock_driver.get.return_value = None
        mock_driver.title = "Test Page"
        mock_get_cleaned_html.return_value = "<html>Test</html>"

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            navigate(session_id, "https://example.com")
        )

        assert "Navigated to https://example.com" in result
        assert "Title: Test Page" in result
        mock_driver.get.assert_called_once_with("https://example.com")

    def test_navigate_exception(self, event_loop):
        """Test navigation with exception"""
        mock_driver = Mock()
        mock_driver.get.side_effect = Exception("Navigation failed")

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            navigate(session_id, "https://example.com")
        )

        assert "Error navigating to https://example.com" in result

    def test_click_element_invalid_session(self, event_loop):
        """Test clicking element with invalid session ID"""
        result = event_loop.run_until_complete(
            click_element("invalid-session", ".test-button")
        )

        assert "Session invalid-session not found" in result

    @patch('mcp_browser_use.__main__.find_element')
    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_click_element_success(self, mock_wait, mock_find_element, event_loop):
        """Test successful element click"""
        # Set up mocks
        mock_driver = Mock()
        mock_driver.current_url = "https://example.com"
        mock_driver.title = "Test Page"
        mock_driver.execute_script.return_value = None

        mock_element = Mock()
        mock_element.click.return_value = None
        mock_find_element.return_value = mock_element

        mock_wait_instance = Mock()
        mock_wait_instance.until.return_value = mock_element
        mock_wait.return_value = mock_wait_instance

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            click_element(session_id, ".test-button")
        )

        assert "Clicked element matching '.test-button'" in result
        assert "Current URL: https://example.com" in result
        mock_element.click.assert_called_once()

    @patch('mcp_browser_use.__main__.find_element')
    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_click_element_js_fallback(self, mock_wait, mock_find_element, event_loop):
        """Test element click with JavaScript fallback"""
        mock_driver = Mock()
        mock_driver.current_url = "https://example.com"
        mock_driver.title = "Test Page"
        mock_driver.execute_script.return_value = None

        mock_element = Mock()
        mock_element.click.side_effect = ElementNotInteractableException("Element not clickable")
        mock_find_element.return_value = mock_element

        mock_wait_instance = Mock()
        mock_wait_instance.until.return_value = mock_element
        mock_wait.return_value = mock_wait_instance

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            click_element(session_id, ".test-button")
        )

        assert "Clicked element matching '.test-button'" in result
        # Check that JavaScript click was called
        mock_driver.execute_script.assert_called()

    def test_fill_text_invalid_session(self, event_loop):
        """Test filling text with invalid session ID"""
        result = event_loop.run_until_complete(
            fill_text("invalid-session", ".input-field", "test text")
        )

        assert "Session invalid-session not found" in result

    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_fill_text_success(self, mock_wait, event_loop):
        """Test successful text filling"""
        mock_driver = Mock()
        mock_driver.current_url = "https://example.com"
        mock_driver.title = "Test Page"
        mock_driver.execute_script.return_value = None

        mock_element = Mock()
        mock_element.clear.return_value = None
        mock_element.send_keys.return_value = None
        mock_element.click.return_value = None

        mock_wait_instance = Mock()
        mock_wait_instance.until.return_value = mock_element
        mock_wait.return_value = mock_wait_instance

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            fill_text(session_id, ".input-field", "test text")
        )

        assert "Entered text 'test text'" in result
        assert "Current URL: https://example.com" in result
        mock_element.click.assert_called_once()
        mock_element.clear.assert_called_once()

    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_fill_text_timeout(self, mock_wait, event_loop):
        """Test text filling with timeout"""
        mock_wait_instance = Mock()
        mock_wait_instance.until.side_effect = TimeoutException("Element not found")
        mock_wait.return_value = mock_wait_instance

        mock_driver = Mock()
        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            fill_text(session_id, ".input-field", "test text")
        )

        assert "Timeout waiting for element" in result

    def test_send_keys_invalid_session(self, event_loop):
        """Test sending keys with invalid session ID"""
        result = event_loop.run_until_complete(
            send_keys("invalid-session", "ENTER")
        )

        assert "Session invalid-session not found" in result

    @patch('mcp_browser_use.__main__.webdriver.ActionChains')
    @patch('mcp_browser_use.__main__.get_cleaned_html')
    def test_send_keys_without_selector(
        self,
        mock_get_cleaned_html,
        mock_action_chains,
        event_loop
    ):
        """Test sending keys without specific element selector"""
        mock_driver = Mock()
        mock_driver.current_url = "https://example.com"
        mock_driver.title = "Test Page"

        mock_chains = Mock()
        mock_chains.send_keys.return_value = mock_chains
        mock_chains.perform.return_value = None
        mock_action_chains.return_value = mock_chains

        mock_get_cleaned_html.return_value = "<html>Test</html>"

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            send_keys(session_id, "ENTER")
        )

        assert "Sent key 'ENTER' to active element" in result
        mock_chains.send_keys.assert_called_once_with(Keys.ENTER)
        mock_chains.perform.assert_called_once()

    def test_send_keys_invalid_key(self, event_loop):
        """Test sending invalid key"""
        mock_driver = Mock()
        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            send_keys(session_id, "INVALID_KEY")
        )

        assert "Invalid key: INVALID_KEY" in result

    def test_scroll_invalid_session(self, event_loop):
        """Test scrolling with invalid session ID"""
        result = event_loop.run_until_complete(
            scroll("invalid-session")
        )

        assert "Session invalid-session not found" in result

    @patch('mcp_browser_use.__main__.get_cleaned_html')
    def test_scroll_success(self, mock_get_cleaned_html, event_loop):
        """Test successful scrolling"""
        mock_driver = Mock()
        mock_driver.current_url = "https://example.com"
        mock_driver.title = "Test Page"
        mock_driver.execute_script.return_value = None
        mock_get_cleaned_html.return_value = "<html>Test</html>"

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            scroll(session_id, x=100, y=200)
        )

        assert "Scrolled by x=100, y=200" in result
        mock_driver.execute_script.assert_called_with("window.scrollBy(100, 200);")

    def test_take_screenshot_invalid_session(self, event_loop):
        """Test taking screenshot with invalid session ID"""
        result = event_loop.run_until_complete(
            take_screenshot("invalid-session")
        )

        assert "Session invalid-session not found" in result

    def test_take_screenshot_success(self, event_loop):
        """Test successful screenshot"""
        mock_driver = Mock()
        mock_driver.get_screenshot_as_base64.return_value = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            take_screenshot(session_id)
        )

        assert "Screenshot taken successfully" in result
        assert "Base64 data: iVBORw0KGg..." in result

    def test_close_browser_invalid_session(self, event_loop):
        """Test closing browser with invalid session ID"""
        result = event_loop.run_until_complete(
            close_browser("invalid-session")
        )

        assert "Session invalid-session not found" in result

    def test_close_browser_success(self, event_loop):
        """Test successful browser closure"""
        mock_driver = Mock()
        mock_driver.quit.return_value = None

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            close_browser(session_id)
        )

        assert f"Session {session_id} closed successfully" in result
        mock_driver.quit.assert_called_once()
        assert session_id not in browser_sessions

    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_wait_for_element_present(self, mock_wait, event_loop):
        """Test waiting for element to be present"""
        mock_driver = Mock()
        mock_element = Mock()
        mock_wait_instance = Mock()
        mock_wait_instance.until.return_value = mock_element
        mock_wait.return_value = mock_wait_instance

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            wait_for_element(session_id, ".test-element", condition="present")
        )

        assert "Element matching '.test-element' is now present" in result

    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_wait_for_element_timeout(self, mock_wait, event_loop):
        """Test waiting for element with timeout"""
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait_instance.until.side_effect = TimeoutException("Timeout")
        mock_wait.return_value = mock_wait_instance

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            wait_for_element(session_id, ".test-element")
        )

        assert "Timeout waiting for element" in result

    def test_get_cookies_invalid_session(self, event_loop):
        """Test getting cookies with invalid session ID"""
        result = event_loop.run_until_complete(
            get_cookies("invalid-session")
        )

        assert "Session invalid-session not found" in result

    def test_get_cookies_success(self, event_loop):
        """Test successful cookie retrieval"""
        mock_driver = Mock()
        mock_cookies = [{"name": "test", "value": "cookie"}]
        mock_driver.get_cookies.return_value = mock_cookies

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            get_cookies(session_id)
        )

        assert result == mock_cookies

    def test_add_cookie_success(self, event_loop):
        """Test successful cookie addition"""
        mock_driver = Mock()
        mock_driver.add_cookie.return_value = None

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        cookie = {"name": "test", "value": "cookie"}
        result = event_loop.run_until_complete(
            add_cookie(session_id, cookie)
        )

        assert "Cookie added successfully" in result
        mock_driver.add_cookie.assert_called_once_with(cookie)

    def test_delete_cookie_success(self, event_loop):
        """Test successful cookie deletion"""
        mock_driver = Mock()
        mock_driver.delete_cookie.return_value = None

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            delete_cookie(session_id, "test_cookie")
        )

        assert "Cookie 'test_cookie' deleted successfully" in result
        mock_driver.delete_cookie.assert_called_once_with("test_cookie")

    def test_debug_element_not_found(self, event_loop):
        """Test debugging element that doesn't exist"""
        mock_driver = Mock()
        mock_driver.find_element.side_effect = Exception("Element not found")

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            debug_element(session_id, ".non-existent")
        )

        assert "Element not found" in result

    def test_debug_element_success(self, event_loop):
        """Test successful element debugging"""
        mock_driver = Mock()
        mock_element = Mock()
        mock_element.is_displayed.return_value = True
        mock_element.is_enabled.return_value = True
        mock_element.tag_name = "button"

        mock_driver.find_element.return_value = mock_element
        mock_driver.execute_script.side_effect = [
            "block",  # display
            "visible",  # visibility
            "1",  # opacity
            "100px",  # height
            "200px",  # width
            "static",  # position
            "auto",  # z-index
            True,  # in_viewport
            False  # is_covered
        ]

        session_id = "test-session"
        browser_sessions[session_id] = mock_driver

        result = event_loop.run_until_complete(
            debug_element(session_id, ".test-button")
        )

        assert "Debug info for element" in result
        assert "Tag name: button" in result
        assert "Displayed: True" in result

    def test_get_by_selector(self):
        """Test selector type conversion"""
        assert get_by_selector('css') == By.CSS_SELECTOR
        assert get_by_selector('xpath') == By.XPATH
        assert get_by_selector('id') == By.ID
        assert get_by_selector('name') == By.NAME
        assert get_by_selector('tag') == By.TAG_NAME
        assert get_by_selector('class') == By.CLASS_NAME
        assert get_by_selector('link_text') == By.LINK_TEXT
        assert get_by_selector('partial_link_text') == By.PARTIAL_LINK_TEXT
        assert get_by_selector('invalid') is None

    def test_remove_unwanted_tags(self):
        """Test HTML tag removal"""
        html_input = """
        <html>
            <head>
                <script>alert('test');</script>
                <style>body { color: red; }</style>
                <meta charset="utf-8">
                <link rel="stylesheet" href="style.css">
            </head>
            <body>
                <h1>Title</h1>
                <p>Content</p>
                <noscript>No JavaScript</noscript>
            </body>
        </html>
        """

        result = remove_unwanted_tags(html_input)

        assert "alert('test')" not in result
        assert "color: red" not in result
        assert "charset" not in result
        assert "stylesheet" not in result
        assert "No JavaScript" not in result
        assert "<h1>Title</h1>" in result
        assert "<p>Content</p>" in result

    @patch('mcp_browser_use.__main__.remove_unwanted_tags')
    def test_get_cleaned_html(self, mock_remove_tags):
        """Test HTML cleaning function"""
        mock_driver = Mock()
        mock_driver.page_source = "<html>Test</html>"
        mock_remove_tags.return_value = "cleaned html"

        result = get_cleaned_html(mock_driver)

        assert result == "cleaned html"
        mock_remove_tags.assert_called_once_with("<html>Test</html>")

    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_find_element_with_iframe(self, mock_wait):
        """Test finding element within iframe"""
        mock_driver = Mock()
        mock_iframe = Mock()
        mock_element = Mock()

        mock_wait_instance = Mock()
        mock_wait_instance.until.side_effect = [mock_iframe, mock_element]
        mock_wait.return_value = mock_wait_instance

        mock_driver.switch_to.frame.return_value = None
        mock_driver.switch_to.default_content.return_value = None

        result = find_element(
            mock_driver,
            ".test-element",
            "css",
            iframe_selector=".test-iframe"
        )

        assert result == mock_element
        mock_driver.switch_to.frame.assert_called_once_with(mock_iframe)
        mock_driver.switch_to.default_content.assert_called_once()

    @patch('mcp_browser_use.__main__.WebDriverWait')
    def test_find_element_timeout(self, mock_wait):
        """Test finding element with timeout exception"""
        mock_driver = Mock()
        mock_wait_instance = Mock()
        mock_wait_instance.until.side_effect = TimeoutException("Timeout")
        mock_wait.return_value = mock_wait_instance

        with pytest.raises(TimeoutException):
            find_element(mock_driver, ".test-element", "css")

    def test_find_element_invalid_selector_type(self):
        """Test finding element with invalid selector type"""
        mock_driver = Mock()

        with pytest.raises(ValueError, match="Unsupported selector type"):
            find_element(mock_driver, ".test-element", "invalid_selector")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
