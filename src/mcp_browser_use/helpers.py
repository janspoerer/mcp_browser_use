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



#region Re-exports

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

# Export list - Only essentials
__all__ = [
    # ===== Public API =====
    # Context
    'get_context',
    'reset_context',
    'BrowserContext',

    # Constants
    'ACTION_LOCK_TTL_SECS',
    'ACTION_LOCK_WAIT_SECS',
    'FILE_MUTEX_STALE_SECS',
    'WINDOW_REGISTRY_STALE_THRESHOLD',
    'MAX_SNAPSHOT_CHARS',
    'START_LOCK_WAIT_SEC',
    'RENDEZVOUS_TTL_SEC',
    'ALLOW_ATTACH_ANY',

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
]

# NOTE: For all other functions, import directly from the source module:
#   from mcp_browser_use.actions.navigation import navigate_to_url
#   from mcp_browser_use.actions.elements import click_element
#   from mcp_browser_use.browser.chrome import start_or_attach_chrome_from_env
#   etc.
