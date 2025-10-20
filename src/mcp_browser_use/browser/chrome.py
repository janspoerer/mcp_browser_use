"""Chrome browser management - Main orchestration."""

import os
import time
from pathlib import Path
from typing import Tuple, Optional
import psutil

# Import from refactored modules
from .chrome_executable import validate_user_data_dir
from .chrome_launcher import (
    try_attach_existing_chrome,
    launch_on_fixed_port,
    launch_on_dynamic_port,
)
from .chrome_process import find_chrome_by_port
from .devtools import devtools_active_port_from_file, is_debugger_listening
from .process import read_rendezvous, write_rendezvous
from ..locking.file_mutex import acquire_start_lock, release_start_lock
from ..constants import START_LOCK_WAIT_SEC

# Re-export for backward compatibility
from .chrome_executable import (
    resolve_chrome_executable as _resolve_chrome_executable,
    get_chrome_binary_for_platform as _chrome_binary_for_platform,
    get_chrome_version,
    is_default_user_data_dir,
)
from .chrome_process import (
    is_chrome_running_with_userdata as chrome_running_with_userdata,
    find_chrome_by_port as find_chrome_process_by_port,
)

import logging
logger = logging.getLogger(__name__)


def start_or_attach_chrome_from_env(config: dict) -> Tuple[str, int, Optional[psutil.Process]]:
    """
    Start or attach to Chrome with remote debugging enabled.

    This is the main orchestration function that coordinates:
    1. Directory validation
    2. Attempting to attach to existing Chrome
    3. Launching on fixed or dynamic port
    4. Rendezvous file management

    Args:
        config: Configuration dict with user_data_dir, profile_name, fixed_port (optional)

    Returns:
        Tuple of (host, port, proc) where proc is None if attached to existing Chrome

    Raises:
        RuntimeError: If Chrome fails to start or validation fails
    """
    user_data_dir = config["user_data_dir"]
    fixed_port = config.get("fixed_port")
    host = "127.0.0.1"

    # Ensure directory exists
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    # Validate directory
    validate_user_data_dir(user_data_dir)

    # Try to attach to existing Chrome first (if no fixed port specified)
    if not fixed_port:
        result = try_attach_existing_chrome(config, host)
        if result:
            return result

    # Fixed port path
    if fixed_port:
        return launch_on_fixed_port(config, host, fixed_port)

    # Rendezvous path (multi-process coordination)
    port, pid = read_rendezvous(config)
    if port:
        return host, port, None

    got_lock = acquire_start_lock(config, timeout_sec=START_LOCK_WAIT_SEC)
    try:
        if not got_lock:
            # Wait for rendezvous by the process that got the lock
            for _ in range(50):
                port, pid = read_rendezvous(config)
                if port:
                    return host, port, None

                # Also try attaching via DevToolsActivePort if it appears
                p2 = devtools_active_port_from_file(user_data_dir)
                if p2 and is_debugger_listening(host, p2):
                    chrome_proc = find_chrome_by_port(p2)
                    write_rendezvous(config, p2, chrome_proc.pid if chrome_proc else os.getpid())
                    return host, p2, None

                time.sleep(0.1)

            raise RuntimeError("Timeout acquiring start lock for Chrome rendezvous.")

        # Inside lock: recheck rendezvous
        port, pid = read_rendezvous(config)
        if port:
            return host, port, None

        # Launch Chrome on dynamic port
        return launch_on_dynamic_port(config, host)

    finally:
        if got_lock:
            release_start_lock(config)


__all__ = [
    'start_or_attach_chrome_from_env',
    # Backward compatibility exports
    '_resolve_chrome_executable',
    '_chrome_binary_for_platform',
    'chrome_running_with_userdata',
    'find_chrome_process_by_port',
    'get_chrome_version',
    'is_default_user_data_dir',
]
