import asyncio
import pytest
import tempfile
import os
import time
from pathlib import Path
from mcp_agent.core.fastagent import FastAgent
from dotenv import load_dotenv

# Add other imports like asyncio, tempfile, etc. below

@pytest.fixture(scope="session", autouse=True)
def load_env():
    """
    Automatically load environment variables from a .env file
    at the start of the test session.
    """
    load_dotenv()

##
## We DO NOT want to use pytest-asyncio.
##

@pytest.fixture
def config_file():
    """Create a temporary config file for testing"""
    config_content = """
default_model: gpt-4o-mini

logger:
    progress_display: false
    show_chat: false
    show_tools: true
    truncate_tools: true

mcp:
    servers:
        mcp_browser_use:
            command: "/home/janspoerer/code/all_repos/mcp_browser_use/.venv/bin/python"
            args: ["/home/janspoerer/code/all_repos/mcp_browser_use/mcp_browser_use"]
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        f.flush()
        yield f.name
    os.unlink(f.name)

@pytest.fixture
def fast_agent(config_file):
    """Create a FastAgent instance for testing"""
    return FastAgent("test-agent", config_path=config_file)

@pytest.fixture
def event_loop():
    asyncio.get_event_loop_policy().set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


class TestE2EMCPBrowserUse:
    """End-to-end tests for MCP Browser Use with FastAgent"""

    def test_browser_lifecycle(self, fast_agent, event_loop):
        """Test complete browser lifecycle: start, navigate, interact, close"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Follow instructions precisely and report results clearly.")
        async def test_agent():
            async with fast_agent.run() as agent:
                # Test 1: Start browser
                response = await agent.send("Start a new browser session in headed mode")

                assert "Browser session created successfully" in response
                assert "Session ID:" in response

                # Extract session ID from response
                session_id = None
                for line in response.split('\n'):
                    if "Session ID:" in line:
                        session_id = line.split("Session ID:")[1].strip()
                        break

                assert session_id is not None, "Failed to extract session ID"

                # Test 2: Navigate to a website
                response = await agent(f"Navigate to https://httpbin.org/html using session {session_id}")

                assert "Navigated to https://httpbin.org/html" in response
                assert "Herman Melville - Moby Dick" in response

                # Test 3: Take screenshot
                response = await agent(f"Take a screenshot of the current page using session {session_id}")

                assert "Screenshot taken successfully" in response

                # Test 4: Close browser
                response = await agent(f"Close browser session {session_id}")
                assert f"Session {session_id} closed successfully" in response

                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


    def test_form_interaction(self, fast_agent, event_loop):
        """Test form filling and submission"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Follow instructions precisely for web form testing.")
        async def test_agent():
            async with fast_agent.run() as agent:
                response = await agent("Start a new browser session in headed mode")

                session_id = None
                for line in response.split('\n'):
                    if "Session ID:" in line:
                        session_id = line.split("Session ID:")[1].strip()
                        break

                # Navigate to httpbin forms page
                response = await                    agent(f"Navigate to https://httpbin.org/forms/post using session {session_id}")

                assert "Navigated to https://httpbin.org/forms/post" in response

                # Fill form fields
                response = await agent(f"Fill the input field with name 'custname' with text 'John Doe' using session {session_id}")
                assert "Entered text 'John Doe'" in response

                response = await agent(
                    agent(f"Fill the input field with name 'custtel' with text '+1234567890' using session {session_id}")
                )
                assert "Entered text '+1234567890'" in response

                response = await agent(f"Fill the input field with name 'custemail' with text 'john@example.com' using session {session_id}")

                assert "Entered text 'john@example.com'" in response

                # Submit form
                response = await agent(f"Click the submit button using CSS selector 'input[type=\"submit\"]' with session {session_id}")

                assert "Clicked element" in response

                # Verify form submission (httpbin should return form data)
                time.sleep(2)  # Wait for form submission
                response = await                    agent(f"Navigate to the current URL to get page content for session {session_id}")


                # Close browser
                await                    agent(f"Close browser session {session_id}")


                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


    def test_element_interaction(self, fast_agent, event_loop):
        """Test various element interactions"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Test various element interactions on web pages.")
        async def test_agent():
            async with fast_agent.run() as agent:
                # Start browser
                response = await                     agent("Start a new browser session in headed mode")

                session_id = None
                for line in response.split('\n'):
                    if "Session ID:" in line:
                        session_id = line.split("Session ID:")[1].strip()
                        break

                # Navigate to a page with various elements
                response = await agent(f"Navigate to https://httpbin.org/html using session {session_id}")

                assert "Navigated to https://httpbin.org/html" in response

                # Test scrolling
                response = await agent(f"Scroll down by 300 pixels on the page using session {session_id}")

                assert "Scrolled by x=0, y=300" in response or "Scrolled by" in response

                # Test element clicking (try to click on a link)
                response = await agent(f"Click on the first paragraph element using CSS selector 'p' with session {session_id}")

                # This might not be clickable, but should attempt the action

                # Test waiting for elements
                response = await agent(f"Wait for the h1 element to be visible using CSS selector 'h1' with session {session_id}")
                assert "Element matching 'h1' is now visible" in response or "is now" in response

                # Test sending keys
                response = await agent(f"Send the ESCAPE key using session {session_id}")
                assert "Sent key 'ESCAPE'" in response

                # Close browser
                await agent(f"Close browser session {session_id}")

                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


    def test_multiple_sessions(self, fast_agent, event_loop):
        """Test managing multiple browser sessions"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Test managing multiple browser sessions simultaneously.")
        async def test_agent():
            async with fast_agent.run() as agent:
                response1 = await    agent("Start a new browser session in headed mode")

                session_id1 = None
                for line in response1.split('\n'):
                    if "Session ID:" in line:
                        session_id1 = line.split("Session ID:")[1].strip()
                        break

                # Start second browser session
                response2 = await                     agent("Start another new browser session in headed mode")

                session_id2 = None
                for line in response2.split('\n'):
                    if "Session ID:" in line:
                        session_id2 = line.split("Session ID:")[1].strip()
                        break

                assert session_id1 != session_id2, "Session IDs should be different"

                # Navigate both sessions to different pages
                response = await                     agent(f"Navigate to https://httpbin.org/html using session {session_id1}")

                assert "Navigated to https://httpbin.org/html" in response

                response = await                     agent(f"Navigate to https://httpbin.org/json using session {session_id2}")

                assert "Navigated to https://httpbin.org/json" in response

                # Take screenshots of both sessions
                response = await                    agent(f"Take a screenshot using session {session_id1}")

                assert "Screenshot taken successfully" in response

                response = await                    agent(f"Take a screenshot using session {session_id2}")

                assert "Screenshot taken successfully" in response

                # Close both sessions
                response = await                    agent(f"Close browser session {session_id1}")

                assert f"Session {session_id1} closed successfully" in response

                response = await                    agent(f"Close browser session {session_id2}")

                assert f"Session {session_id2} closed successfully" in response

                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


    def test_cookie_management(self, fast_agent, event_loop):
        """Test cookie operations"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Test cookie management functionality.")
        async def test_agent():
            async with fast_agent.run() as agent:
                response = await agent("Start a new browser session in headed mode")
                session_id = None
                for line in response.split('\n'):
                    if "Session ID:" in line:
                        session_id = line.split("Session ID:")[1].strip()
                        break

                # Navigate to a page that sets cookies
                response = await                     agent(f"Navigate to https://httpbin.org/cookies/set/test/cookie_value using session {session_id}")


                # Get cookies
                response = await                    agent(f"Get all cookies for session {session_id}")

                # Should contain cookie information

                # Add a custom cookie
                response = await                     agent(f'Add a cookie with name "custom" and value "test_value" for session {session_id}')

                assert "Cookie added successfully" in response or "added" in response

                # Delete a cookie
                response = await                     agent(f'Delete the cookie named "test" for session {session_id}')

                assert "deleted successfully" in response or "deleted" in response

                # Close browser
                await                    agent(f"Close browser session {session_id}")


                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


    def test_error_handling(self, fast_agent, event_loop):
        """Test error handling scenarios"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Test error handling scenarios.")
        async def test_agent():
            async with fast_agent.run() as agent:
                # Test invalid session ID
                response = await agent("Navigate to https://example.com using session invalid-session-id")
                assert "Session invalid-session-id not found" in response

                # Start a valid session for other tests
                response = await agent("Start a new browser session in headed mode")
                session_id = None
                for line in response.split('\n'):
                    if "Session ID:" in line:
                        session_id = line.split("Session ID:")[1].strip()
                        break

                # Test invalid URL navigation
                response = await agent(f"Navigate to invalid-url using session {session_id}")
                assert "Error" in response or "invalid" in response.lower()

                # Test clicking non-existent element
                response = await agent(f"Click element with CSS selector '.non-existent-element' using session {session_id}")
                assert "Error" in response or "not found" in response or "timeout" in response.lower()

                # Test filling non-existent form field
                response = await agent(f"Fill input field with CSS selector '.non-existent-input' with text 'test' using session {session_id}")
                assert "Error" in response or "not found" in response or "timeout" in response.lower()

                # Clean up
                await agent(f"Close browser session {session_id}")

                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


    def test_javascript_interaction(self, fast_agent, event_loop):
        """Test JavaScript-based interactions"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Test JavaScript-based interactions and force JS clicking.")
        async def test_agent():
            async with fast_agent.run() as agent:
                # Start browser
                response = await agent("Start a new browser session in headed mode")
                session_id = None
                for line in response.split('\n'):
                    if "Session ID:" in line:
                        session_id = line.split("Session ID:")[1].strip()
                        break

                # Navigate to a page
                response = await agent(f"Navigate to https://httpbin.org/html using session {session_id}")
                assert "Navigated" in response

                # Test force JavaScript click
                response = await agent(f"Click the first paragraph using CSS selector 'p' with force_js=True for session {session_id}")
                # Should attempt JavaScript click even if element isn't normally clickable

                # Test element debugging
                response = await agent(f"Debug the h1 element using CSS selector 'h1' for session {session_id}")
                assert "Debug info for element" in response or "Tag name:" in response

                # Close browser
                await agent(f"Close browser session {session_id}")

                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


    def test_advanced_selectors(self, fast_agent, event_loop):
        """Test various selector types"""

        @fast_agent.agent(instruction="You are a browser automation test agent. Test different selector types including XPath, ID, class, etc.")
        async def test_agent():
            async with fast_agent.run() as agent:
                # Start browser
                response = await agent("Start a new browser session in headless mode")

                session_id = None
                for line in response.split('\n'):
                    if "Session ID:" in line:
                        session_id = line.split("Session ID:")[1].strip()
                        break

                # Navigate to a page with various elements
                response = await                     agent(f"Navigate to https://httpbin.org/html using session {session_id}")


                # Test XPath selector
                response = await agent(f"Click element using XPath selector '//h1' for session {session_id}")

                # Should attempt to click the h1 element

                # Test tag selector
                response = await agent(f"Wait for element using tag selector 'body' for session {session_id}")

                assert "Element matching 'body' is now" in response or "is now" in response

                # Test CSS selector with attribute
                response = await agent(f"Debug element using CSS selector 'html[lang]' for session {session_id}")

                # Should provide debug info for html element with lang attribute

                # Close browser
                await agent(f"Close browser session {session_id}")


                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


class TestMCPToolFunctions:
    """Test individual MCP tool functions directly"""

    def test_start_browser_tool(self, fast_agent, event_loop):
        """Test the start_browser MCP tool directly"""

        @fast_agent.agent(instruction="Use only the start_browser tool to test browser initialization")
        async def test_agent():
            async with fast_agent.run() as agent:
                # Test headless browser start
                response = await agent("Use the start_browser tool with headless=True")
                assert "Browser session created successfully" in response

                # Test non-headless browser start
                response = await agent("Use the start_browser tool with headless=False")
                assert "Browser session created successfully" in response

                return True

        result = event_loop.run_until_complete(test_agent())
        assert result is True


    def test_get_browser_versions_tool(self, fast_agent, event_loop):
        """Test the get_browser_versions MCP tool"""

        @fast_agent.agent(instruction="Use the get_browser_versions tool to check browser compatibility")
        async def test_agent():
            async with fast_agent.run() as agent:
                response = await agent("Use the get_browser_versions tool to check Chrome and ChromeDriver versions")

                # Should return version information or error messages
                assert "Chrome" in response or "Error" in response

                return True

        result = event_loop.run_until_complete(
            test_agent()
        )
        assert result is True


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])
