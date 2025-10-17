import pytest
import asyncio
import json
from unittest.mock import Mock, patch
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException
)


import mcp_browser_use.helpers as helpers
from mcp_browser_use.helpers import (
    get_by_selector,
    find_element,
    remove_unwanted_tags,
    get_cleaned_html,
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
        # Reset global driver state
        helpers.DRIVER = None
        helpers.TARGET_ID = None
        helpers.WINDOW_ID = None

    def teardown_method(self):
        """Clean up after each test method."""
        # Reset global driver state
        helpers.DRIVER = None
        helpers.TARGET_ID = None
        helpers.WINDOW_ID = None


    @patch('mcp_browser_use.helpers.create_webdriver')
    @patch('mcp_browser_use.helpers._ensure_debugger_ready')
    def test_start_browser_success(self, mock_ensure_debugger, mock_create_driver, event_loop):
        """Test successful browser startup"""
        mock_driver = Mock()
        mock_driver.current_window_handle = "handle1"
        mock_driver.window_handles = ["handle1"]
        mock_create_driver.return_value = mock_driver
        helpers.DEBUGGER_HOST = "127.0.0.1"
        helpers.DEBUGGER_PORT = 9225
        
        mock_driver.execute_cdp_cmd.return_value = {"windowId": 1, "targetId": "target1"}
        mock_driver.current_url = "about:blank"
        mock_driver.title = ""
        mock_driver.page_source = "<html><body></body></html>"

        result = event_loop.run_until_complete(
            helpers.start_browser()
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert "session_id" in result_data


    @patch('mcp_browser_use.helpers.create_webdriver')
    @patch('mcp_browser_use.helpers._ensure_debugger_ready')
    def test_start_browser_driver_not_initialized(self, mock_ensure_debugger, mock_create_driver, event_loop):
        """Test browser startup when driver fails to initialize"""
        mock_create_driver.return_value = None
        helpers.DEBUGGER_HOST = None
        helpers.DEBUGGER_PORT = None

        result = event_loop.run_until_complete(
            helpers.start_browser()
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == False
        assert result_data["error"] == "driver_not_initialized"


    def test_start_browser_exception(self, event_loop):
        """Test browser startup with exception"""
        with patch('mcp_browser_use.helpers._ensure_driver_and_window') as mock_ensure:
            mock_ensure.side_effect = Exception("Test error")
            
            result = event_loop.run_until_complete(
                helpers.start_browser()
            )
            
            result_data = json.loads(result)
            assert result_data["ok"] == False
            assert "Test error" in result_data["error"]

    def test_navigate_no_driver(self, event_loop):
        """Test navigation when driver is not initialized"""
        helpers.DRIVER = None
        
        result = event_loop.run_until_complete(
            helpers.navigate_to_url("https://example.com", 30.0)
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == False
        assert result_data["error"] == "driver_not_initialized"

    @patch('mcp_browser_use.helpers.get_cleaned_html')
    @patch('mcp_browser_use.helpers._wait_document_ready')
    def test_navigate_success(self, mock_wait, mock_get_cleaned_html, event_loop):
        """Test successful navigation"""
        # Set up mock driver
        mock_driver = Mock()
        mock_driver.get.return_value = None
        mock_driver.current_url = "https://example.com"
        mock_driver.title = "Test Page"
        mock_driver.switch_to.default_content.return_value = None
        mock_get_cleaned_html.return_value = "<html>Test</html>"
        helpers.DRIVER = mock_driver

        result = event_loop.run_until_complete(
            helpers.navigate_to_url("https://example.com", 30.0)
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert result_data["url"] == "https://example.com"
        mock_driver.get.assert_called_once_with("https://example.com")

    @patch('mcp_browser_use.helpers._make_page_snapshot')
    @patch('mcp_browser_use.helpers.collect_diagnostics')
    def test_navigate_exception(self, mock_diagnostics, mock_snapshot, event_loop):
        """Test navigation with exception"""
        mock_driver = Mock()
        mock_driver.get.side_effect = Exception("Navigation failed")
        mock_snapshot.return_value = {"url": None, "title": None, "html": "", "truncated": False}
        mock_diagnostics.return_value = "Mock diagnostics"
        helpers.DRIVER = mock_driver

        result = event_loop.run_until_complete(
            helpers.navigate_to_url("https://example.com", 30.0)
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == False
        assert "Navigation failed" in result_data["error"]

    def test_click_element_no_driver(self, event_loop):
        """Test clicking element when driver is not initialized"""
        helpers.DRIVER = None
        
        result = event_loop.run_until_complete(
            helpers.click_element(".test-button", "css", 10.0, False, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == False
        # The function will likely throw an exception before checking driver

    @patch('mcp_browser_use.helpers.find_element')
    @patch('mcp_browser_use.helpers._wait_clickable_element')
    @patch('mcp_browser_use.helpers._make_page_snapshot')
    @patch('mcp_browser_use.helpers._wait_document_ready')
    def test_click_element_success(self, mock_wait_doc, mock_snapshot, mock_wait_clickable, mock_find_element, event_loop):
        """Test successful element click"""
        # Set up mocks
        mock_driver = Mock()
        mock_driver.switch_to.default_content.return_value = None
        helpers.DRIVER = mock_driver

        mock_element = Mock()
        mock_element.click.return_value = None
        mock_element.is_displayed.return_value = True
        mock_element.is_enabled.return_value = True
        mock_find_element.return_value = mock_element
        mock_wait_clickable.return_value = mock_element
        mock_snapshot.return_value = {"url": "https://example.com", "title": "Test", "html": "", "truncated": False}

        result = event_loop.run_until_complete(
            helpers.click_element(".test-button", "css", 10.0, False, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert result_data["action"] == "click"
        assert result_data["selector"] == ".test-button"
        mock_element.click.assert_called_once()

    @patch('mcp_browser_use.helpers.find_element')
    @patch('mcp_browser_use.helpers._wait_clickable_element')
    @patch('mcp_browser_use.helpers._make_page_snapshot')
    @patch('mcp_browser_use.helpers._wait_document_ready')
    def test_click_element_js_fallback(self, mock_wait_doc, mock_snapshot, mock_wait_clickable, mock_find_element, event_loop):
        """Test element click with JavaScript fallback"""
        mock_driver = Mock()
        mock_driver.switch_to.default_content.return_value = None
        mock_driver.execute_script.return_value = None
        helpers.DRIVER = mock_driver

        mock_element = Mock()
        mock_element.click.side_effect = ElementClickInterceptedException("Element not clickable")
        mock_element.is_displayed.return_value = True
        mock_element.is_enabled.return_value = True
        mock_find_element.return_value = mock_element
        mock_wait_clickable.return_value = mock_element
        mock_snapshot.return_value = {"url": "https://example.com", "title": "Test", "html": "", "truncated": False}

        result = event_loop.run_until_complete(
            helpers.click_element(".test-button", "css", 10.0, False, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        # Check that JavaScript click was called
        mock_driver.execute_script.assert_called()

    def test_fill_text_no_driver(self, event_loop):
        """Test filling text when driver is not initialized"""
        helpers.DRIVER = None
        
        result = event_loop.run_until_complete(
            helpers.fill_text(".input-field", "test text", "css", True, 10.0, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == False

    @patch('mcp_browser_use.helpers.find_element')
    @patch('mcp_browser_use.helpers._make_page_snapshot')
    @patch('mcp_browser_use.helpers._wait_document_ready')
    def test_fill_text_success(self, mock_wait_doc, mock_snapshot, mock_find_element, event_loop):
        """Test successful text filling"""
        mock_driver = Mock()
        mock_driver.switch_to.default_content.return_value = None
        helpers.DRIVER = mock_driver

        mock_element = Mock()
        mock_element.clear.return_value = None
        mock_element.send_keys.return_value = None
        mock_find_element.return_value = mock_element
        mock_snapshot.return_value = {"url": "https://example.com", "title": "Test", "html": "", "truncated": False}

        result = event_loop.run_until_complete(
            helpers.fill_text(".input-field", "test text", "css", True, 10.0, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert result_data["action"] == "fill_text"
        assert result_data["selector"] == ".input-field"
        mock_element.clear.assert_called_once()
        mock_element.send_keys.assert_called_once_with("test text")

    @patch('mcp_browser_use.helpers.find_element')
    @patch('mcp_browser_use.helpers._make_page_snapshot')
    @patch('mcp_browser_use.helpers.collect_diagnostics')
    def test_fill_text_timeout(self, mock_diagnostics, mock_snapshot, mock_find_element, event_loop):
        """Test text filling with timeout"""
        mock_driver = Mock()
        mock_driver.switch_to.default_content.return_value = None
        mock_snapshot.return_value = {"url": None, "title": None, "html": "", "truncated": False}
        mock_diagnostics.return_value = "Mock diagnostics"
        helpers.DRIVER = mock_driver
        mock_find_element.side_effect = TimeoutException("Element not found")

        result = event_loop.run_until_complete(
            helpers.fill_text(".input-field", "test text", "css", True, 10.0, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == False
        assert "Element not found" in result_data["error"]

    # send_keys and scroll functions are not implemented in the current codebase

    def test_take_screenshot_no_driver(self, event_loop):
        """Test taking screenshot when driver is not initialized"""
        helpers.DRIVER = None
        
        result = event_loop.run_until_complete(
            helpers.take_screenshot(None, False, False)
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == False

    def test_take_screenshot_success(self, event_loop):
        """Test successful screenshot"""
        mock_driver = Mock()
        mock_driver.get_screenshot_as_base64.return_value = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        mock_driver.get_screenshot_as_png.return_value = b"fake_png_data"
        helpers.DRIVER = mock_driver

        result = event_loop.run_until_complete(
            helpers.take_screenshot(None, True, False)
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert "base64" in result_data

    @patch('mcp_browser_use.helpers.close_singleton_window')
    def test_close_browser_success(self, mock_close_window, event_loop):
        """Test successful browser closure"""
        mock_close_window.return_value = True

        result = event_loop.run_until_complete(
            helpers.close_browser()
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert result_data["closed"] == True
        mock_close_window.assert_called_once()

    @patch('mcp_browser_use.helpers.close_singleton_window')
    def test_close_browser_no_window(self, mock_close_window, event_loop):
        """Test closing browser when no window exists"""
        mock_close_window.return_value = False

        result = event_loop.run_until_complete(
            helpers.close_browser()
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert result_data["closed"] == False

    # wait_for_element is not directly exposed in the current helpers module

    # Cookie management functions are not implemented in the current codebase

    @patch('mcp_browser_use.helpers.find_element')
    @patch('mcp_browser_use.helpers._make_page_snapshot')
    @patch('mcp_browser_use.helpers.collect_diagnostics')
    def test_debug_element_not_found(self, mock_diagnostics, mock_snapshot, mock_find_element, event_loop):
        """Test debugging element that doesn't exist"""
        mock_driver = Mock()
        mock_driver.switch_to.default_content.return_value = None
        mock_snapshot.return_value = {"url": None, "title": None, "html": "", "truncated": False}
        mock_diagnostics.return_value = "Mock diagnostics"
        helpers.DRIVER = mock_driver
        mock_find_element.side_effect = TimeoutException("Element not found")

        result = event_loop.run_until_complete(
            helpers.debug_element(".non-existent", "css", 10.0, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert result_data["debug"]["exists"] == False

    @patch('mcp_browser_use.helpers.find_element')
    @patch('mcp_browser_use.helpers._wait_clickable_element')
    @patch('mcp_browser_use.helpers._make_page_snapshot')
    def test_debug_element_success(self, mock_snapshot, mock_wait_clickable, mock_find_element, event_loop):
        """Test successful element debugging"""
        mock_driver = Mock()
        mock_driver.switch_to.default_content.return_value = None
        mock_driver.execute_script.return_value = "<button>Test</button>"
        helpers.DRIVER = mock_driver
        
        mock_element = Mock()
        mock_element.is_displayed.return_value = True
        mock_element.is_enabled.return_value = True
        mock_element.rect = {"x": 10, "y": 20, "width": 100, "height": 30}
        mock_find_element.return_value = mock_element
        mock_wait_clickable.return_value = mock_element
        mock_snapshot.return_value = {"url": "test", "title": "test", "html": "", "truncated": False}

        result = event_loop.run_until_complete(
            helpers.debug_element(".test-button", "css", 10.0, None, "css", None, "css")
        )
        
        result_data = json.loads(result)
        assert result_data["ok"] == True
        assert result_data["debug"]["exists"] == True
        assert result_data["debug"]["displayed"] == True
        assert result_data["debug"]["clickable"] == True

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

    @patch('mcp_browser_use.helpers.remove_unwanted_tags')
    def test_get_cleaned_html(self, mock_remove_tags):
        """Test HTML cleaning function"""
        mock_driver = Mock()
        mock_driver.page_source = "<html>Test</html>"
        mock_remove_tags.return_value = "cleaned html"

        result = get_cleaned_html(mock_driver)

        assert result == "cleaned html"
        mock_remove_tags.assert_called_once_with("<html>Test</html>")

    @patch('mcp_browser_use.helpers.WebDriverWait')
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

    @patch('mcp_browser_use.helpers.WebDriverWait')
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
