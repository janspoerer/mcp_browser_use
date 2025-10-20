"""Chrome launch orchestration and command building."""

import os
import time
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Optional

from .chrome_executable import get_chrome_binary_for_platform
from .chrome_process import find_chrome_by_port, is_chrome_running_with_userdata

# Import from sibling modules
from .devtools import devtools_active_port_from_file, is_debugger_listening
from .process import write_rendezvous, get_free_port

import logging
logger = logging.getLogger(__name__)


def build_chrome_command(
    binary: str,
    port: int,
    user_data_dir: str,
    profile_name: str,
) -> list[str]:
    """
    Build Chrome command-line arguments for debugging.

    Consolidates duplicated command building from 2 locations in start_or_attach_chrome_from_env.

    Args:
        binary: Path to Chrome executable
        port: Remote debugging port
        user_data_dir: Chrome user data directory
        profile_name: Chrome profile name

    Returns:
        list[str]: Command-line arguments for Chrome
    """
    headless = os.getenv("MCP_HEADLESS", "0").strip()
    is_headless = headless in ("1", "true", "True", "yes", "Yes")

    cmd = [
        binary,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={profile_name}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "--disable-features=ProcessPerSite",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-software-rasterizer",
        "about:blank",
    ]

    if is_headless:
        cmd.append("--headless=new")

    return cmd


def launch_chrome_process(
    cmd: list[str],
    port: int,
) -> subprocess.Popen:
    """
    Launch Chrome process and verify it started.

    Consolidates duplicated launch logic from 2 locations in start_or_attach_chrome_from_env.

    Args:
        cmd: Command-line arguments for Chrome
        port: Remote debugging port (used for logging)

    Returns:
        subprocess.Popen: Chrome process

    Note:
        Does not raise if process exits immediately; caller should check proc.poll()
    """
    # Create error log file
    log_dir = Path(tempfile.gettempdir()) / "mcp_browser_logs"
    log_dir.mkdir(exist_ok=True)
    error_log = log_dir / f"chrome_debug_{port}.log"

    # Launch process
    if platform.system() == "Windows":
        proc = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL
        )

    # Verify Chrome started
    time.sleep(2.0)
    if proc.poll() is not None:
        try:
            with open(error_log, "r") as log:
                error_content = log.read()
                logger.error(f"Chrome failed to start. Exit code: {proc.returncode}. Log: {error_content}")
        except Exception:
            pass

    return proc


def wait_for_devtools_ready(
    host: str,
    port: int,
    user_data_dir: str,
    timeout_iterations: int = 100,
) -> bool:
    """
    Wait for DevTools endpoint to become available.

    Consolidates duplicated waiting logic from 2 locations in start_or_attach_chrome_from_env.

    Args:
        host: Debugger host (typically "127.0.0.1")
        port: Remote debugging port
        user_data_dir: Chrome user data directory (for error messages)
        timeout_iterations: Number of 0.1s iterations to wait

    Returns:
        bool: True if endpoint is ready

    Raises:
        RuntimeError: If endpoint never appears with helpful diagnostic message
    """
    for _ in range(timeout_iterations):
        if is_debugger_listening(host, port):
            return True
        time.sleep(0.1)

    # If endpoint never appeared, provide helpful error
    if is_chrome_running_with_userdata(user_data_dir):
        raise RuntimeError(
            "DevTools endpoint did not appear. Likely causes:\n"
            " - Chrome refused remote debugging because the user-data-dir is a default channel directory.\n"
            " - Another Chrome instance (started without --remote-debugging-port) is holding this user-data-dir.\n"
            "Actions:\n"
            f" - Use a separate automation dir (e.g., '{Path(user_data_dir).parent}/Chrome Beta MCP'), "
            "optionally seeded from your profile, and try again.\n"
            " - Or ensure all Chrome/Chrome Beta processes are fully quit before starting."
        )

    raise RuntimeError(f"Failed to start Chrome with remote debugging on {port}.")


def try_attach_existing_chrome(
    config: dict,
    host: str,
) -> Optional[Tuple[str, int, None]]:
    """
    Try to attach to existing Chrome instance via DevToolsActivePort.

    Args:
        config: Configuration dict with user_data_dir
        host: Debugger host (typically "127.0.0.1")

    Returns:
        Optional[Tuple[str, int, None]]: (host, port, None) if successful, None otherwise
    """
    user_data_dir = config["user_data_dir"]

    existing_port = devtools_active_port_from_file(user_data_dir)
    if existing_port and is_debugger_listening(host, existing_port):
        chrome_proc = find_chrome_by_port(existing_port)
        write_rendezvous(config, existing_port, chrome_proc.pid if chrome_proc else os.getpid())
        return host, existing_port, None

    return None


def launch_on_fixed_port(
    config: dict,
    host: str,
    port: int,
) -> Tuple[str, int, Optional[subprocess.Popen]]:
    """
    Launch Chrome on a fixed port or attach to existing instance.

    Args:
        config: Configuration dict with user_data_dir, profile_name
        host: Debugger host (typically "127.0.0.1")
        port: Fixed port to use

    Returns:
        Tuple[str, int, Optional[subprocess.Popen]]: (host, port, proc) where proc is None if attached to existing

    Raises:
        RuntimeError: If Chrome fails to start or DevTools endpoint doesn't appear
    """
    user_data_dir = config["user_data_dir"]
    profile_name = config["profile_name"]

    # Check if profile is already debuggable on a different port
    existing_port = devtools_active_port_from_file(user_data_dir)
    if existing_port and existing_port != port and is_debugger_listening(host, existing_port):
        chrome_proc = find_chrome_by_port(existing_port)
        write_rendezvous(config, existing_port, chrome_proc.pid if chrome_proc else os.getpid())
        return host, existing_port, None

    # Check if already listening on target port
    if is_debugger_listening(host, port):
        chrome_proc = find_chrome_by_port(port)
        write_rendezvous(config, port, chrome_proc.pid if chrome_proc else os.getpid())
        return host, port, None

    # Launch Chrome on fixed port
    binary = get_chrome_binary_for_platform(config)
    cmd = build_chrome_command(binary, port, user_data_dir, profile_name)
    proc = launch_chrome_process(cmd, port)

    # Wait for DevTools
    if wait_for_devtools_ready(host, port, user_data_dir):
        chrome_proc = find_chrome_by_port(port)
        write_rendezvous(config, port, chrome_proc.pid if chrome_proc else proc.pid)
        return host, port, proc

    raise RuntimeError(f"Failed to start Chrome with remote debugging on {port}.")


def launch_on_dynamic_port(
    config: dict,
    host: str,
) -> Tuple[str, int, subprocess.Popen]:
    """
    Launch Chrome on a dynamically assigned port.

    Args:
        config: Configuration dict with user_data_dir, profile_name
        host: Debugger host (typically "127.0.0.1")

    Returns:
        Tuple[str, int, subprocess.Popen]: (host, port, proc)

    Raises:
        RuntimeError: If Chrome fails to start or DevTools endpoint doesn't appear
    """
    user_data_dir = config["user_data_dir"]
    profile_name = config["profile_name"]

    port = get_free_port()
    binary = get_chrome_binary_for_platform(config)
    cmd = build_chrome_command(binary, port, user_data_dir, profile_name)
    proc = launch_chrome_process(cmd, port)

    # Wait for DevTools
    if wait_for_devtools_ready(host, port, user_data_dir):
        chrome_proc = find_chrome_by_port(port)
        if chrome_proc:
            write_rendezvous(config, port, chrome_proc.pid)
        else:
            write_rendezvous(config, port, proc.pid)
        return host, port, proc

    raise RuntimeError("Failed to start Chrome with remote debugging; endpoint never came up.")


__all__ = [
    'build_chrome_command',
    'launch_chrome_process',
    'wait_for_devtools_ready',
    'try_attach_existing_chrome',
    'launch_on_fixed_port',
    'launch_on_dynamic_port',
]
