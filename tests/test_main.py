"""Tests for mcp_browser_use MCP server tools.

Uses unittest.mock to mock Selenium WebDriver so tests run without a real browser.
"""

import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# We need to patch imports before importing __main__
# Patch ChromeCustomProfileLoader since it may not exist on Linux
sys.modules.setdefault("ChromeCustomProfileLoader", MagicMock())

# Patch heavy imports to avoid side effects during import
with patch.dict(os.environ, {"TESTING": "1"}):
    from mcp_browser_use.__main__ import (
        browser_sessions,
        browser_log_paths,
        browser_temp_dirs,
        remove_unwanted_tags,
        get_cleaned_html,
        get_by_selector,
        find_element,
        navigate,
        execute_js,
        click_element,
        scroll,
        take_screenshot,
        close_browser,
        fill_text,
        send_keys,
        wait_for_element,
        debug_element,
        read_chromedriver_log,
    )


def run_async(coro):
    """Helper to run async functions in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure browser_sessions is clean before/after each test."""
    browser_sessions.clear()
    browser_log_paths.clear()
    browser_temp_dirs.clear()
    yield
    browser_sessions.clear()
    browser_log_paths.clear()
    browser_temp_dirs.clear()


@pytest.fixture
def mock_driver():
    """Create a mock Selenium WebDriver."""
    driver = MagicMock()
    driver.title = "Test Page"
    driver.current_url = "https://example.com"
    driver.page_source = "<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
    driver.get_screenshot_as_base64.return_value = "AAAAAABBBBBB"
    driver.get_screenshot_as_png.return_value = b"\x89PNG"
    return driver


@pytest.fixture
def session_with_driver(mock_driver):
    """Register a mock driver in browser_sessions and return session_id."""
    sid = "test-session-123"
    browser_sessions[sid] = {'engine': 'undetected-chromedriver', 'driver': mock_driver}
    return sid


# --- Unit tests for helper functions ---


class TestRemoveUnwantedTags:
    def test_removes_script_tags(self):
        html = "<html><body><script>alert('x')</script><p>Hello</p></body></html>"
        result = remove_unwanted_tags(html)
        assert "<script>" not in result
        assert "alert" not in result
        assert "Hello" in result

    def test_removes_style_tags(self):
        html = "<html><body><style>.x{color:red}</style><p>Hello</p></body></html>"
        result = remove_unwanted_tags(html)
        assert "<style>" not in result
        assert "color:red" not in result

    def test_removes_meta_link_noscript(self):
        html = '<html><head><meta charset="utf-8"><link rel="stylesheet" href="x.css"></head><body><noscript>No JS</noscript><p>Content</p></body></html>'
        result = remove_unwanted_tags(html)
        assert "<meta" not in result
        assert "<link" not in result
        assert "<noscript>" not in result
        assert "Content" in result

    def test_preserves_normal_tags(self):
        html = "<html><body><div><p>Keep this</p><a href='#'>Link</a></div></body></html>"
        result = remove_unwanted_tags(html)
        assert "Keep this" in result
        assert "Link" in result


class TestGetCleanedHtml:
    def test_calls_remove_unwanted_tags(self, mock_driver):
        mock_driver.page_source = "<html><body><script>x</script><p>Clean</p></body></html>"
        result = get_cleaned_html(mock_driver)
        assert "<script>" not in result
        assert "Clean" in result


class TestGetBySelector:
    def test_css_selector(self):
        from selenium.webdriver.common.by import By
        assert get_by_selector("css") == By.CSS_SELECTOR

    def test_xpath_selector(self):
        from selenium.webdriver.common.by import By
        assert get_by_selector("xpath") == By.XPATH

    def test_id_selector(self):
        from selenium.webdriver.common.by import By
        assert get_by_selector("id") == By.ID

    def test_unknown_selector_returns_none(self):
        assert get_by_selector("nonexistent") is None

    def test_case_insensitive(self):
        from selenium.webdriver.common.by import By
        assert get_by_selector("CSS") == By.CSS_SELECTOR
        assert get_by_selector("Xpath") == By.XPATH


# --- Tests for MCP tool functions ---


class TestNavigate:
    def test_navigate_success(self, session_with_driver, mock_driver):
        result = run_async(navigate(session_with_driver, "https://example.com"))
        mock_driver.get.assert_called_once_with("https://example.com")
        assert "Navigated to https://example.com" in result
        assert "Title: Test Page" in result

    def test_navigate_does_not_return_html(self, session_with_driver, mock_driver):
        result = run_async(navigate(session_with_driver, "https://example.com"))
        assert "HTML:" not in result

    def test_navigate_invalid_session(self):
        result = run_async(navigate("nonexistent", "https://example.com"))
        assert "not found" in result

    def test_navigate_driver_error(self, session_with_driver, mock_driver):
        mock_driver.get.side_effect = Exception("Connection refused")
        result = run_async(navigate(session_with_driver, "https://example.com"))
        assert "Error" in result


class TestExecuteJs:
    def test_returns_json_for_list(self, session_with_driver, mock_driver):
        mock_driver.execute_script.return_value = ["a", "b", "c"]
        result = run_async(execute_js(session_with_driver, "return [1,2,3]"))
        parsed = json.loads(result)
        assert parsed == ["a", "b", "c"]

    def test_returns_json_for_dict(self, session_with_driver, mock_driver):
        mock_driver.execute_script.return_value = {"name": "Test", "price": 42.5}
        result = run_async(execute_js(session_with_driver, "return {}"))
        parsed = json.loads(result)
        assert parsed["name"] == "Test"
        assert parsed["price"] == 42.5

    def test_returns_json_for_string(self, session_with_driver, mock_driver):
        mock_driver.execute_script.return_value = "hello"
        result = run_async(execute_js(session_with_driver, "return 'hello'"))
        assert json.loads(result) == "hello"

    def test_returns_json_for_number(self, session_with_driver, mock_driver):
        mock_driver.execute_script.return_value = 42
        result = run_async(execute_js(session_with_driver, "return 42"))
        assert json.loads(result) == 42

    def test_returns_message_for_null(self, session_with_driver, mock_driver):
        mock_driver.execute_script.return_value = None
        result = run_async(execute_js(session_with_driver, "return null"))
        assert "null/undefined" in result

    def test_returns_str_for_non_serializable(self, session_with_driver, mock_driver):
        # Simulate a non-JSON-serializable return (e.g. a WebElement)
        obj = MagicMock()
        obj.__str__ = lambda self: "MockElement"
        mock_driver.execute_script.return_value = obj
        result = run_async(execute_js(session_with_driver, "return document.body"))
        assert "MockElement" in result

    def test_invalid_session(self):
        result = run_async(execute_js("nonexistent", "return 1"))
        assert "not found" in result

    def test_script_error(self, session_with_driver, mock_driver):
        mock_driver.execute_script.side_effect = Exception("ReferenceError")
        result = run_async(execute_js(session_with_driver, "return undefinedVar"))
        assert "Error executing script" in result

    def test_unicode_result(self, session_with_driver, mock_driver):
        mock_driver.execute_script.return_value = {"name": "Wärmepumpe", "price": "1.699,00 €"}
        result = run_async(execute_js(session_with_driver, "return {}"))
        parsed = json.loads(result)
        assert parsed["name"] == "Wärmepumpe"
        assert "€" in parsed["price"]


class TestClickElement:
    def test_invalid_session(self):
        result = run_async(click_element("nonexistent", ".btn"))
        assert "not found" in result


class TestScroll:
    def test_invalid_session(self):
        result = run_async(scroll("nonexistent"))
        assert "not found" in result

    def test_scroll_executes_js(self, session_with_driver, mock_driver):
        mock_driver.execute_script.return_value = None
        result = run_async(scroll(session_with_driver, x=0, y=500))
        mock_driver.execute_script.assert_called()
        assert "Scrolled by x=0, y=500" in result


class TestTakeScreenshot:
    def test_invalid_session(self):
        result = run_async(take_screenshot("nonexistent"))
        assert "not found" in result

    def test_takes_screenshot(self, session_with_driver, mock_driver):
        result = run_async(take_screenshot(session_with_driver))
        assert "Screenshot taken successfully" in result
        mock_driver.get_screenshot_as_base64.assert_called_once()

    def test_saves_to_file(self, session_with_driver, mock_driver):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            result = run_async(take_screenshot(session_with_driver, screenshot_path=path))
            assert "Screenshot taken successfully" in result
            mock_driver.get_screenshot_as_png.assert_called_once()
        finally:
            os.unlink(path)


class TestCloseBrowser:
    def test_invalid_session(self):
        result = run_async(close_browser("nonexistent"))
        assert "not found" in result

    def test_close_success(self, session_with_driver, mock_driver):
        result = run_async(close_browser(session_with_driver))
        assert "closed successfully" in result
        mock_driver.quit.assert_called_once()
        assert session_with_driver not in browser_sessions

    def test_cleans_up_temp_dir(self, session_with_driver, mock_driver):
        temp_dir = tempfile.mkdtemp(prefix="selenium_test_")
        browser_temp_dirs[session_with_driver] = temp_dir
        result = run_async(close_browser(session_with_driver))
        assert "closed successfully" in result
        assert not os.path.exists(temp_dir)


class TestFillText:
    def test_invalid_session(self):
        result = run_async(fill_text("nonexistent", "#input", "hello"))
        assert "not found" in result


class TestSendKeys:
    def test_invalid_session(self):
        result = run_async(send_keys("nonexistent", "ENTER"))
        assert "not found" in result


class TestWaitForElement:
    def test_invalid_session(self):
        result = run_async(wait_for_element("nonexistent", ".loading"))
        assert "not found" in result

    def test_invalid_condition(self, session_with_driver, mock_driver):
        result = run_async(wait_for_element(session_with_driver, ".x", condition="flying"))
        assert "Invalid condition" in result


class TestDebugElement:
    def test_invalid_session(self):
        result = run_async(debug_element("nonexistent", ".btn"))
        assert "not found" in result


class TestReadChromedriverLog:
    def test_no_log_found(self):
        result = run_async(read_chromedriver_log("nonexistent"))
        assert "No log found" in result

    def test_reads_log(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            path = f.name
        sid = "log-test"
        browser_log_paths[sid] = path
        try:
            result = run_async(read_chromedriver_log(sid, lines=2))
            assert "line1" in result
            assert "line2" in result
            assert "line3" not in result
        finally:
            os.unlink(path)

    def test_empty_log(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            path = f.name
        sid = "empty-log"
        browser_log_paths[sid] = path
        try:
            result = run_async(read_chromedriver_log(sid))
            assert "empty" in result
        finally:
            os.unlink(path)
