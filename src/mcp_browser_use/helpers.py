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

#region Re-exports from refactored modules
# Import and re-export from locking modules
from .locking.file_mutex import (
    _now,
    _lock_paths,
    _file_mutex,
    start_lock_dir,
    acquire_start_lock,
    release_start_lock,
)

from .locking.action_lock import (
    get_intra_process_lock,
    _renew_action_lock,
    _read_softlock,
    _write_softlock,
    _acquire_softlock,
    _release_action_lock,
    _acquire_action_lock_or_error,
)

from .locking.window_registry import (
    _window_registry_path,
    _read_window_registry,
    _write_window_registry,
    _register_window,
    _update_window_heartbeat,
    _unregister_window,
    cleanup_orphaned_windows,
)

# Import and re-export from browser modules
from .browser.process import (
    _is_port_open,
    get_free_port,
    make_process_tag,
    _read_json,
    read_rendezvous,
    write_rendezvous,
    clear_rendezvous,
    rendezvous_path,
    chromedriver_log_path,
)

from .browser.devtools import (
    _read_devtools_active_port,
    devtools_active_port_from_file,
    _devtools_user_data_dir,
    _verify_port_matches_profile,
    _same_dir,
    is_debugger_listening,
    _ensure_debugger_ready,
    _handle_for_target,
)

from .browser.chrome import (
    _resolve_chrome_executable,
    _chrome_binary_for_platform,
    chrome_running_with_userdata,
    find_chrome_process_by_port,
    get_chrome_version,
    start_or_attach_chrome_from_env,
    is_default_user_data_dir,
)

from .browser.driver import (
    create_webdriver,
    _ensure_driver,
    _ensure_driver_and_window,
    _ensure_singleton_window,
    close_singleton_window,
    _cleanup_own_blank_tabs,
    _close_extra_blank_windows_safe,
    get_chromedriver_capability_version,
    _validate_window_context,
    ensure_process_tag,
)

# Import and re-export from actions modules
from .actions.navigation import (
    _wait_document_ready,
    navigate_to_url,
    wait_for_element,
    get_current_page_meta,
)

from .actions.elements import (
    find_element,
    _wait_clickable_element,
    get_by_selector,
    click_element,
    fill_text,
    debug_element,
)

from .actions.screenshots import (
    _make_page_snapshot,
    take_screenshot,
)

from .actions.keyboard import (
    send_keys,
    scroll,
)

# Import and re-export from utils modules
from .utils.retry import (
    retry_op,
)

from .utils.html_utils import (
    remove_unwanted_tags,
    get_cleaned_html,
)

from .utils.diagnostics import (
    collect_diagnostics,
)

from .tools.browser_management import (
    start_browser,
    unlock_browser,
    close_browser,
    force_close_all_chrome,
)

from .tools.navigation import (
    navigate_to_url,
    scroll,
)

from .tools.interaction import (
    fill_text,
    click_element,
    send_keys,
    wait_for_element,
)

from .tools.debugging import (
    get_debug_diagnostics_info,
    debug_element,
)

from .tools.screenshots import (
    take_screenshot,
)

# get_current_page_meta already imported from .actions.navigation
#endregion

# Maintain backward compatibility - export all  symbols
__all__ = [
    # Config and keys
    'get_env_config',
    'profile_key',
    
    # Globals
    'DRIVER',
    'DEBUGGER_HOST',
    'DEBUGGER_PORT',
    'MY_TAG',
    'ALLOW_ATTACH_ANY',
    'TARGET_ID',
    'WINDOW_ID',
    'LOCK_DIR',
    'ACTION_LOCK_TTL_SECS',
    'ACTION_LOCK_WAIT_SECS',
    'FILE_MUTEX_STALE_SECS',
    'WINDOW_REGISTRY_STALE_THRESHOLD',
    'MAX_SNAPSHOT_CHARS',
    'MCP_INTRA_PROCESS_LOCK',
    'START_LOCK_WAIT_SEC',
    'RENDEZVOUS_TTL_SEC',
    
    # Locking
    '_now',
    '_lock_paths',
    '_file_mutex',
    'start_lock_dir',
    'acquire_start_lock',
    'release_start_lock',
    'get_intra_process_lock',
    '_renew_action_lock',
    '_read_softlock',
    '_write_softlock',
    '_acquire_softlock',
    '_release_action_lock',
    '_acquire_action_lock_or_error',
    '_window_registry_path',
    '_read_window_registry',
    '_write_window_registry',
    '_register_window',
    '_update_window_heartbeat',
    '_unregister_window',
    'cleanup_orphaned_windows',
    
    # Browser/Process
    '_is_port_open',
    'get_free_port',
    'ensure_process_tag',
    'make_process_tag',
    '_read_json',
    'read_rendezvous',
    'write_rendezvous',
    'clear_rendezvous',
    'rendezvous_path',
    'chromedriver_log_path',
    
    # Browser/DevTools
    '_read_devtools_active_port',
    'devtools_active_port_from_file',
    '_devtools_user_data_dir',
    '_verify_port_matches_profile',
    '_same_dir',
    'is_debugger_listening',
    '_ensure_debugger_ready',
    '_handle_for_target',
    
    # Browser/Chrome
    '_resolve_chrome_executable',
    '_chrome_binary_for_platform',
    'chrome_running_with_userdata',
    'find_chrome_process_by_port',
    'get_chrome_version',
    'start_or_attach_chrome_from_env',
    'is_default_user_data_dir',
    
    # Browser/Driver
    'create_webdriver',
    '_ensure_driver',
    '_ensure_driver_and_window',
    '_ensure_singleton_window',
    'close_singleton_window',
    '_cleanup_own_blank_tabs',
    '_close_extra_blank_windows_safe',
    'get_chromedriver_capability_version',
    '_validate_window_context',
    
    # Actions
    '_wait_document_ready',
    'navigate_to_url',
    'wait_for_element',
    'get_current_page_meta',
    'find_element',
    '_wait_clickable_element',
    'get_by_selector',
    'click_element',
    'fill_text',
    'debug_element',
    '_make_page_snapshot',
    'take_screenshot',
    'send_keys',
    'scroll',
    
    # Utils
    'retry_op',
    'remove_unwanted_tags',
    'get_cleaned_html',
    'collect_diagnostics',
    'get_debug_diagnostics_info',

    # Async tool implementations
    'start_browser',
    'navigate_to_url',
    'fill_text',
    'click_element',
    'take_screenshot',
    'debug_element',
    'unlock_browser',
    'close_browser',
    'force_close_all_chrome',
    'scroll',
    'send_keys',
    'wait_for_element',
    'get_current_page_meta',
]
