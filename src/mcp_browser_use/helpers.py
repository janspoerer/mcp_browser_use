"""
Helpers module - Compatibility layer.

This module now serves as a compatibility layer that re-exports functions
from the refactored modules. All actual implementations have been moved to:
- locking/ (file_mutex, action_lock, window_registry)
- browser/ (process, devtools, chrome, driver)
- actions/ (navigation, elements, screenshots, keyboard)
- utils/ (html_utils, retry, diagnostics)

The functions are re-exported here to maintain backward compatibility with
existing code that imports from helpers.
"""

#region Imports
import os
import sys
import json
import time
import psutil
import socket
import shutil
import asyncio
import hashlib
import tempfile
import platform
import traceback
import subprocess
import contextlib
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Callable, Optional, Tuple, Dict, Any
import io
import base64

import logging
logger = logging.getLogger(__name__)
#endregion Imports

#region Browser
import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchWindowException,
    StaleElementReferenceException,
    WebDriverException,
    ElementClickInterceptedException,
)

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
#endregion

#region Imports Dotenv
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(filename=".env", usecwd=True), override=True)
#endregion

#region Context Integration (Phase 2)
# Import new modules
from .context import get_context, reset_context, BrowserContext
from .constants import (
    ACTION_LOCK_TTL_SECS as _ACTION_LOCK_TTL_SECS,
    ACTION_LOCK_WAIT_SECS as _ACTION_LOCK_WAIT_SECS,
    FILE_MUTEX_STALE_SECS as _FILE_MUTEX_STALE_SECS,
    WINDOW_REGISTRY_STALE_THRESHOLD as _WINDOW_REGISTRY_STALE_THRESHOLD,
    MAX_SNAPSHOT_CHARS as _MAX_SNAPSHOT_CHARS,
    START_LOCK_WAIT_SEC as _START_LOCK_WAIT_SEC,
    RENDEZVOUS_TTL_SEC as _RENDEZVOUS_TTL_SEC,
    ALLOW_ATTACH_ANY as _ALLOW_ATTACH_ANY,
)
from .config.environment import get_env_config as _get_env_config, profile_key as _profile_key
from .config.paths import get_lock_dir as _get_lock_dir
#endregion

#region Constants / policy parameters (Backwards Compatible - delegates to constants.py)
# These now delegate to constants.py but maintain the old API
ACTION_LOCK_TTL_SECS = _ACTION_LOCK_TTL_SECS
ACTION_LOCK_WAIT_SECS = _ACTION_LOCK_WAIT_SECS
FILE_MUTEX_STALE_SECS = _FILE_MUTEX_STALE_SECS
WINDOW_REGISTRY_STALE_THRESHOLD = _WINDOW_REGISTRY_STALE_THRESHOLD
MAX_SNAPSHOT_CHARS = _MAX_SNAPSHOT_CHARS
START_LOCK_WAIT_SEC = _START_LOCK_WAIT_SEC
RENDEZVOUS_TTL_SEC = _RENDEZVOUS_TTL_SEC
ALLOW_ATTACH_ANY = _ALLOW_ATTACH_ANY
#endregion

#region Configuration and keys (Backwards Compatible - delegates to config module)
def get_env_config() -> dict:
    """
    Read environment variables and validate required ones.

    DEPRECATED: Use mcp_browser_use.config.environment.get_env_config() directly.
    This function now delegates to the config module for backwards compatibility.

    Prioritizes Chrome Beta over Chrome Canary over Chrome. This is to free the Chrome instance. Chrome is likely
    used by the user already. It is easier to separate the executables. If a user already has the Chrome executable open,
    the MCP will not work properly as the Chrome DevTool Debug mode will not open when Chrome is already open in normal mode.
    We prioritize Chrome Beta because it is more stable than Canary.

    Required:   Either CHROME_PROFILE_USER_DATA_DIR, BETA_PROFILE_USER_DATA_DIR, or CANARY_PROFILE_USER_DATA_DIR
    Optional:   CHROME_PROFILE_NAME (default 'Default')
                CHROME_EXECUTABLE_PATH
                BETA_EXECUTABLE_PATH (overrides CHROME_EXECUTABLE_PATH)
                CANARY_EXECUTABLE_PATH (overrides BETA and CHROME)
                CHROME_REMOTE_DEBUG_PORT

    If BETA_EXECUTABLE_PATH is set, expects:
                BETA_PROFILE_USER_DATA_DIR
                BETA_PROFILE_NAME
    If CANARY_EXECUTABLE_PATH is set, expects:
                CANARY_PROFILE_USER_DATA_DIR
                CANARY_PROFILE_NAME
    """
    return _get_env_config()


def profile_key(config: Optional[dict] = None) -> str:
    """
    Stable key used by cross-process locks, based on absolute user_data_dir + profile_name.

    DEPRECATED: Use mcp_browser_use.config.environment.profile_key() directly.
    This function now delegates to the config module for backwards compatibility.

    - Hard-fails if CHROME_PROFILE_USER_DATA_DIR is missing/blank.
    - If CHROME_PROFILE_STRICT=1 and the directory doesn't exist, hard-fail.
      Otherwise we allow Chrome to create it and we normalize the path for stability.
    """
    return _profile_key(config)
#endregion

#region Globals (Backwards Compatible - delegates to context)
# These maintain the old global variable API but delegate to context
# DEPRECATED: Use get_context() instead

def _sync_from_context():
    """Sync module globals from context (for backwards compatibility)."""
    ctx = get_context()
    global DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, MY_TAG, TARGET_ID, WINDOW_ID, LOCK_DIR
    DRIVER = ctx.driver
    DEBUGGER_HOST = ctx.debugger_host
    DEBUGGER_PORT = ctx.debugger_port
    MY_TAG = ctx.process_tag
    TARGET_ID = ctx.target_id
    WINDOW_ID = ctx.window_id
    LOCK_DIR = ctx.lock_dir

def _sync_to_context():
    """Sync context from module globals (for backwards compatibility)."""
    ctx = get_context()
    global DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, MY_TAG, TARGET_ID, WINDOW_ID
    ctx.driver = DRIVER
    ctx.debugger_host = DEBUGGER_HOST
    ctx.debugger_port = DEBUGGER_PORT
    ctx.process_tag = MY_TAG
    ctx.target_id = TARGET_ID
    ctx.window_id = WINDOW_ID

# Initialize globals from context
DRIVER = None
DEBUGGER_HOST = None
DEBUGGER_PORT = None
MY_TAG = None
TARGET_ID = None
WINDOW_ID = None
LOCK_DIR = _get_lock_dir()
MCP_INTRA_PROCESS_LOCK = None

# Sync from context
_sync_from_context()
#endregion

#region Backwards Compatibility Re-exports
"""
DEPRECATED: These re-exports are for backwards compatibility only.
New code should import directly from the respective modules.

Example:
    # OLD (deprecated):
    from mcp_browser_use.helpers import navigate_to_url

    # NEW:
    from mcp_browser_use.actions.navigation import navigate_to_url
"""

# Core functions needed by decorators (internal but exported)
from .locking.action_lock import (
    get_intra_process_lock,         # Used by decorators
    _acquire_action_lock_or_error,  # Used by decorators
    _renew_action_lock,              # Used by decorators
    _release_action_lock,            # Used by tools
)

from .browser.process import (
    ensure_process_tag,              # Used by decorators/tools
    make_process_tag,                # Used internally
)

from .browser.driver import (
    _ensure_driver_and_window,       # Used by tools
    _ensure_singleton_window,        # Used by decorators
    close_singleton_window,          # Used by tools
    _cleanup_own_blank_tabs,         # Used by tools
    _close_extra_blank_windows_safe, # Used by tools
)

from .actions.navigation import (
    _wait_document_ready,            # Used by tools
)

from .actions.screenshots import (
    _make_page_snapshot,             # Used by tools
)

# DO NOT re-export everything else - force migration
# If someone needs it, they import directly from the module
#endregion

# Reduced export list - Only essentials for backwards compatibility
__all__ = [
    # ===== Public API (NEW - Recommended) =====
    # Context
    'get_context',
    'reset_context',
    'BrowserContext',

    # Config
    'get_env_config',
    'profile_key',
    'get_lock_dir',

    # Constants
    'ACTION_LOCK_TTL_SECS',
    'ACTION_LOCK_WAIT_SECS',
    'FILE_MUTEX_STALE_SECS',
    'WINDOW_REGISTRY_STALE_THRESHOLD',
    'MAX_SNAPSHOT_CHARS',
    'START_LOCK_WAIT_SEC',
    'RENDEZVOUS_TTL_SEC',
    'ALLOW_ATTACH_ANY',
    'LOCK_DIR',
    'MCP_INTRA_PROCESS_LOCK',

    # ===== Core Functions (Internal but needed by decorators/tools) =====
    # Locking
    'get_intra_process_lock',
    '_acquire_action_lock_or_error',
    '_renew_action_lock',
    '_release_action_lock',

    # Process
    'ensure_process_tag',
    'make_process_tag',

    # Driver
    '_ensure_driver_and_window',
    '_ensure_singleton_window',
    'close_singleton_window',
    '_cleanup_own_blank_tabs',
    '_close_extra_blank_windows_safe',

    # Actions
    '_wait_document_ready',
    '_make_page_snapshot',

    # ===== Backwards Compatibility (DEPRECATED) =====
    # Old globals - use get_context() instead
    'DRIVER',              # DEPRECATED: use get_context().driver
    'DEBUGGER_HOST',       # DEPRECATED: use get_context().debugger_host
    'DEBUGGER_PORT',       # DEPRECATED: use get_context().debugger_port
    'TARGET_ID',           # DEPRECATED: use get_context().target_id
    'WINDOW_ID',           # DEPRECATED: use get_context().window_id
    'MY_TAG',              # DEPRECATED: use get_context().process_tag
]

# NOTE: For all other functions, import directly from the source module:
#   from mcp_browser_use.actions.navigation import navigate_to_url
#   from mcp_browser_use.actions.elements import click_element
#   from mcp_browser_use.browser.chrome import start_or_attach_chrome_from_env
#   etc.
