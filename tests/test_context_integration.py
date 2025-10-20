"""Integration tests for BrowserContext refactoring.

Tests to ensure context-based state management works correctly and
backwards compatibility is maintained.
"""

import pytest
from mcp_browser_use.context import get_context, reset_context, BrowserContext
from mcp_browser_use import helpers


class TestContextIntegration:
    """Test BrowserContext integration."""

    def setup_method(self):
        """Reset context before each test."""
        reset_context()

    def test_context_singleton(self):
        """Test that get_context returns same instance."""
        ctx1 = get_context()
        ctx2 = get_context()
        assert ctx1 is ctx2

    def test_context_has_required_attributes(self):
        """Test that context has all required attributes."""
        ctx = get_context()
        assert hasattr(ctx, 'driver')
        assert hasattr(ctx, 'debugger_host')
        assert hasattr(ctx, 'debugger_port')
        assert hasattr(ctx, 'target_id')
        assert hasattr(ctx, 'window_id')
        assert hasattr(ctx, 'process_tag')
        assert hasattr(ctx, 'config')
        assert hasattr(ctx, 'lock_dir')

    def test_context_methods(self):
        """Test context utility methods."""
        ctx = get_context()

        # Test is_driver_initialized
        assert ctx.is_driver_initialized() == False  # No driver yet

        # Test get_debugger_address (should return None when not initialized)
        assert ctx.get_debugger_address() is None

        # Test is_window_ready
        assert ctx.is_window_ready() == False  # No window yet

        # Test reset_window_state
        ctx.target_id = "test-id"
        ctx.window_id = 123
        ctx.reset_window_state()
        assert ctx.target_id is None
        assert ctx.window_id is None

    def test_backwards_compat_globals(self):
        """Test that old global variables still work via helpers."""
        # These should not raise AttributeError
        assert helpers.DRIVER is None
        assert helpers.DEBUGGER_HOST is None
        assert helpers.DEBUGGER_PORT is None
        assert helpers.TARGET_ID is None
        assert helpers.WINDOW_ID is None
        assert helpers.MY_TAG is None

    def test_backwards_compat_sync(self):
        """Test that context changes sync to helpers globals."""
        ctx = get_context()

        # Manually set something in context
        ctx.process_tag = "test-tag"

        # Force sync
        helpers._sync_from_context()

        # Check that helpers global is updated
        assert helpers.MY_TAG == "test-tag"

    def test_essential_functions_available(self):
        """Test that essential functions are still exported from helpers."""
        # Context
        assert hasattr(helpers, 'get_context')
        assert hasattr(helpers, 'reset_context')
        assert hasattr(helpers, 'BrowserContext')

        # Config
        assert hasattr(helpers, 'get_env_config')
        assert hasattr(helpers, 'profile_key')
        assert hasattr(helpers, 'get_lock_dir')

        # Core functions
        assert hasattr(helpers, 'ensure_process_tag')
        assert hasattr(helpers, '_ensure_driver_and_window')
        assert hasattr(helpers, 'close_singleton_window')
        assert hasattr(helpers, '_wait_document_ready')
        assert hasattr(helpers, '_make_page_snapshot')

    def test_removed_functions_not_exported(self):
        """Test that non-essential functions are no longer in helpers.__all__."""
        # These should NOT be in __all__ anymore
        removed_functions = [
            'navigate_to_url',
            'click_element',
            'fill_text',
            'start_or_attach_chrome_from_env',
            '_resolve_chrome_executable',
            'collect_diagnostics',
        ]

        for func_name in removed_functions:
            assert func_name not in helpers.__all__, \
                f"{func_name} should not be in helpers.__all__ (import from source module instead)"

    def test_reduced_all_list(self):
        """Test that __all__ has been significantly reduced."""
        # Should be ~40 items, definitely less than 90
        assert len(helpers.__all__) <= 50, \
            f"helpers.__all__ has {len(helpers.__all__)} items, should be <=50"

        # At minimum should have these categories
        assert 'get_context' in helpers.__all__
        assert 'DRIVER' in helpers.__all__  # Backwards compat
        assert 'ensure_process_tag' in helpers.__all__  # Core function


class TestDirectImports:
    """Test that direct imports from modules work correctly."""

    def test_actions_navigation_imports(self):
        """Test importing from actions.navigation."""
        from mcp_browser_use.actions.navigation import (
            navigate_to_url,
            wait_for_element,
            get_current_page_meta,
        )
        assert callable(navigate_to_url)
        assert callable(wait_for_element)
        assert callable(get_current_page_meta)

    def test_actions_elements_imports(self):
        """Test importing from actions.elements."""
        from mcp_browser_use.actions.elements import (
            click_element,
            fill_text,
            debug_element,
        )
        assert callable(click_element)
        assert callable(fill_text)
        assert callable(debug_element)

    def test_browser_chrome_imports(self):
        """Test importing from browser.chrome."""
        from mcp_browser_use.browser.chrome import (
            start_or_attach_chrome_from_env,
            _launch_chrome_with_debug,
        )
        assert callable(start_or_attach_chrome_from_env)
        assert callable(_launch_chrome_with_debug)

    def test_browser_driver_imports(self):
        """Test importing from browser.driver."""
        from mcp_browser_use.browser.driver import (
            _ensure_driver,
            _ensure_driver_and_window,
            close_singleton_window,
        )
        assert callable(_ensure_driver)
        assert callable(_ensure_driver_and_window)
        assert callable(close_singleton_window)

    def test_utils_diagnostics_imports(self):
        """Test importing from utils.diagnostics."""
        from mcp_browser_use.utils.diagnostics import collect_diagnostics
        assert callable(collect_diagnostics)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
