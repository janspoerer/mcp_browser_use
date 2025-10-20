# mcp_browser_use/tools/__init__.py
"""
MCP tool implementations - async wrappers that return JSON responses.

This package contains high-level tool implementations that:
- Wrap lower-level helpers/actions
- Return JSON-serialized responses
- Include error handling and diagnostics
- Provide page snapshots
"""

from .browser_management import (
    start_browser,
    unlock_browser,
    close_browser,
    force_close_all_chrome,
)

from .navigation import (
    navigate_to_url,
    scroll,
)

from .interaction import (
    fill_text,
    click_element,
    send_keys,
    wait_for_element,
)

from .debugging import (
    get_debug_diagnostics_info,
    debug_element,
)

from .screenshots import (
    take_screenshot,
)

__all__ = [
    # Browser management
    'start_browser',
    'unlock_browser',
    'close_browser',
    'force_close_all_chrome',
    # Navigation
    'navigate_to_url',
    'scroll',
    # Interaction
    'fill_text',
    'click_element',
    'send_keys',
    'wait_for_element',
    # Debugging
    'get_debug_diagnostics_info',
    'debug_element',
    # Screenshots
    'take_screenshot',
]
