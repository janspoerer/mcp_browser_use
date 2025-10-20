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

#region Constants / policy parameters
START_LOCK_WAIT_SEC = 8.0                  # How long to wait to acquire the startup lock
RENDEZVOUS_TTL_SEC = 24 * 3600             # How long a rendezvous file is considered valid
#endregion

#region Configuration and keys
def get_env_config() -> dict:
    """
    Read environment variables and validate required ones.

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
    # Base (generic) config
    user_data_dir = (os.getenv("CHROME_PROFILE_USER_DATA_DIR") or "").strip()
    if not user_data_dir and not os.getenv("BETA_PROFILE_USER_DATA_DIR") and not os.getenv("CANARY_PROFILE_USER_DATA_DIR"):
        raise EnvironmentError("CHROME_PROFILE_USER_DATA_DIR is required.")

    profile_name = (os.getenv("CHROME_PROFILE_NAME") or "Default").strip() or "Default"
    chrome_path = (os.getenv("CHROME_EXECUTABLE_PATH") or "").strip() or None

    # Prefer Beta > Canary > Generic Chrome
    canary_path = (os.getenv("CANARY_EXECUTABLE_PATH") or "").strip()
    if canary_path:
        chrome_path = canary_path
        user_data_dir = (os.getenv("CANARY_PROFILE_USER_DATA_DIR") or "").strip()
        profile_name = (os.getenv("CANARY_PROFILE_NAME") or "").strip() or "Default"
        if not user_data_dir:
            raise EnvironmentError("CANARY_PROFILE_USER_DATA_DIR is required when CANARY_EXECUTABLE_PATH is set.")

    beta_path = (os.getenv("BETA_EXECUTABLE_PATH") or "").strip()
    if beta_path:
        chrome_path = beta_path
        user_data_dir = (os.getenv("BETA_PROFILE_USER_DATA_DIR") or "").strip()
        profile_name = (os.getenv("BETA_PROFILE_NAME") or "").strip() or "Default"
        if not user_data_dir:
            raise EnvironmentError("BETA_PROFILE_USER_DATA_DIR is required when BETA_EXECUTABLE_PATH is set.")

    fixed_port_env = (os.getenv("CHROME_REMOTE_DEBUG_PORT") or "").strip()
    fixed_port = int(fixed_port_env) if fixed_port_env.isdigit() else None

    if not user_data_dir:
            raise EnvironmentError(
                "No user_data_dir selected. Set CHROME_PROFILE_USER_DATA_DIR, or provide "
                "BETA_EXECUTABLE_PATH + BETA_PROFILE_USER_DATA_DIR (or CANARY_* equivalents)."
            )

    return {
        "user_data_dir": user_data_dir,
        "profile_name": profile_name,
        "chrome_path": chrome_path,
        "fixed_port": fixed_port,
    }


def profile_key(config: Optional[dict] = None) -> str:
    """
    Stable key used by cross-process locks, based on absolute user_data_dir + profile_name.
    - Hard-fails if CHROME_PROFILE_USER_DATA_DIR is missing/blank.
    - If CHROME_PROFILE_STRICT=1 and the directory doesn't exist, hard-fail.
      Otherwise we allow Chrome to create it and we normalize the path for stability.
    """
    if config is None:
        config = get_env_config()

    user_data_dir = (config.get("user_data_dir") or "").strip()
    profile_name = (config.get("profile_name") or "Default").strip() or "Default"

    if not user_data_dir:
        raise EnvironmentError("CHROME_PROFILE_USER_DATA_DIR is required and cannot be empty.")

    strict = os.getenv("CHROME_PROFILE_STRICT", "0") == "1"
    p = Path(user_data_dir)
    if strict and not p.exists():
        raise FileNotFoundError(f"user_data_dir does not exist: {p}")

    # Normalize to a stable absolute string
    try:
        user_data_dir = str(p.resolve())
    except Exception:
        user_data_dir = str(p.absolute())

    raw = f"{user_data_dir}|{profile_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
#endregion

#region Globals
DRIVER = None
DEBUGGER_HOST: Optional[str] = None
DEBUGGER_PORT: Optional[int] = None
MY_TAG: Optional[str] = None
ALLOW_ATTACH_ANY = os.getenv("MCP_ATTACH_ANY_PROFILE", "0") == "1"

# Single-window identity for this process
TARGET_ID: Optional[str] = None
WINDOW_ID: Optional[int] = None

# Lock directory
_DEFAULT_LOCK_DIR = str(Path(__file__).parent.parent.parent / "tmp" / "mcp_locks")
LOCK_DIR = os.getenv("MCP_BROWSER_LOCK_DIR") or _DEFAULT_LOCK_DIR
Path(LOCK_DIR).mkdir(parents=True, exist_ok=True)

# Action lock TTL and wait time
ACTION_LOCK_TTL_SECS = int(os.getenv("MCP_ACTION_LOCK_TTL", "30"))
ACTION_LOCK_WAIT_SECS = int(os.getenv("MCP_ACTION_LOCK_WAIT", "60"))
FILE_MUTEX_STALE_SECS = int(os.getenv("MCP_FILE_MUTEX_STALE_SECS", "60"))

# Window registry
WINDOW_REGISTRY_STALE_THRESHOLD = int(os.getenv("MCP_WINDOW_REGISTRY_STALE_SECS", "300"))

# Truncation
MAX_SNAPSHOT_CHARS = int(os.getenv("MCP_MAX_SNAPSHOT_CHARS", "10000"))

# Intra-process lock
MCP_INTRA_PROCESS_LOCK: Optional[asyncio.Lock] = None
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
    ensure_process_tag,
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
