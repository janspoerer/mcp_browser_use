# Testing Guide for MCP Browser Use

This document describes the testing infrastructure for the MCP Browser Use project.

## Test Structure

### Unit Tests (`test_mcp_browser_use.py`)
Comprehensive unit tests for all MCP tools including:
- Browser session management
- Navigation and page interaction
- Element clicking, text filling, and keyboard input
- Screenshot functionality
- Cookie management
- Error handling scenarios
- Helper functions

### End-to-End Tests (`test_e2e_mcp_browser_use.py`)
End-to-end tests using the fast-agent library that:
- Start actual MCP agents
- Connect to the browser automation MCP
- Test real browser automation workflows
- Verify complete user scenarios

## Setup and Installation

### 1. Install Test Dependencies

```bash
# Install test requirements
pip install -r requirements-test.txt

# Or install individually:
pip install pytest pytest-asyncio pytest-mock
pip install fast-agent
```

### 2. Install Chrome/Chromium
Ensure you have Chrome or Chromium browser installed:

```bash
# Ubuntu/Debian
sudo apt-get install google-chrome-stable

# Or Chromium
sudo apt-get install chromium-browser
```

### 3. Install ChromeDriver
ChromeDriver should be installed and available in your PATH.

## Running Tests

### Run Unit Tests

```bash
# Run all unit tests
pytest test_mcp_browser_use.py -v

# Run specific test class
pytest test_mcp_browser_use.py::TestMCPBrowserUse -v

# Run with coverage
pytest test_mcp_browser_use.py --cov=mcp_browser_use --cov-report=html
```

### Run End-to-End Tests

```bash
# Run all e2e tests
pytest test_e2e_mcp_browser_use.py -v

# Run specific e2e test
pytest test_e2e_mcp_browser_use.py::TestE2EMCPBrowserUse::test_browser_lifecycle -v

# Run with slower tests (if marked)
pytest test_e2e_mcp_browser_use.py -v -m "not slow"
```

### Run All Tests

```bash
# Run everything
pytest -v

# Run with coverage
pytest --cov=mcp_browser_use --cov-report=html --cov-report=term
```

## Test Configuration

The tests use a pytest configuration file (`pytest.ini`) with the following settings:
- Async test support enabled
- Verbose output by default
- Custom markers for test organization

## Fast-Agent Configuration

E2E tests use a temporary fast-agent configuration that:
- Uses a lightweight model (gpt-4o-mini)
- Minimizes console output during testing
- Points to the local MCP browser use server

## Test Categories

### Unit Test Categories:
1. **Browser Lifecycle**: start_browser, close_browser
2. **Navigation**: navigate, get_browser_versions
3. **Element Interaction**: click_element, fill_text, send_keys
4. **Page Actions**: scroll, take_screenshot, wait_for_element
5. **Cookie Management**: get_cookies, add_cookie, delete_cookie
6. **Debugging**: debug_element, read_chromedriver_log
7. **Helper Functions**: get_by_selector, find_element, HTML cleaning

### E2E Test Scenarios:
1. **Complete Browser Workflow**: Start → Navigate → Interact → Close
2. **Form Interaction**: Fill forms and submit data
3. **Multi-Session Management**: Handle multiple browser sessions
4. **Element Interaction**: Various element interactions and selectors
5. **Cookie Operations**: Cookie management workflows
6. **Error Handling**: Test error scenarios and recovery
7. **JavaScript Interactions**: Force JS clicks and debugging

## Mocking Strategy

Unit tests use extensive mocking to:
- Avoid requiring actual browser installation for CI/CD
- Test error conditions reliably
- Speed up test execution
- Isolate functionality being tested

Key mocked components:
- Selenium WebDriver and Chrome
- WebDriverWait and expected conditions
- File system operations
- Network requests

## Continuous Integration

The test suite is designed to work in CI environments:
- Uses headless browser mode by default in e2e tests
- Includes timeout handling for flaky tests
- Provides detailed error reporting
- Supports parallel test execution

## Debugging Failed Tests

### For Unit Tests:
1. Check mock configurations
2. Verify expected vs actual function calls
3. Review assertion error messages

### For E2E Tests:
1. Check if Chrome/ChromeDriver is properly installed
2. Review fast-agent configuration
3. Check MCP server connection
4. Look at browser session logs
5. Verify test data and expectations

### Common Issues:
- **Chrome not found**: Install Chrome/Chromium browser
- **ChromeDriver issues**: Ensure ChromeDriver is in PATH and compatible with Chrome version
- **MCP connection fails**: Verify MCP server is configured correctly in fast-agent config
- **Timeout errors**: Increase timeout values or check element selectors

## Test Data

Tests use public endpoints like httpbin.org for reliable test data:
- `https://httpbin.org/html` - HTML content testing
- `https://httpbin.org/forms/post` - Form testing
- `https://httpbin.org/json` - JSON response testing
- `https://httpbin.org/cookies/set` - Cookie testing

## Coverage Goals

Target test coverage:
- **Unit Tests**: >90% line coverage
- **E2E Tests**: All major user workflows
- **Error Paths**: Common error scenarios covered

## Contributing Tests

When adding new MCP tools or functionality:

1. **Add Unit Tests**: Test all functions with various inputs and edge cases
2. **Add E2E Tests**: Create realistic user scenarios
3. **Update Mocks**: Ensure mocks match real behavior
4. **Document Test Cases**: Add comments explaining complex test scenarios
5. **Test Error Handling**: Include error condition testing

## Performance Considerations

- Unit tests should complete in < 30 seconds
- E2E tests may take 2-5 minutes depending on browser startup
- Use `pytest-xdist` for parallel execution if needed
- Consider marking slow tests with `@pytest.mark.slow`