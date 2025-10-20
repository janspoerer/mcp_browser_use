"""Chrome process discovery and management."""

import time
import subprocess
from typing import Optional
import psutil

import logging
logger = logging.getLogger(__name__)


def is_chrome_running_with_userdata(user_data_dir: str) -> bool:
    """
    Check if any Chrome process is running with the specified user-data-dir.

    Args:
        user_data_dir: Path to Chrome user data directory

    Returns:
        bool: True if a Chrome process is found with this user-data-dir
    """
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if not p.info["name"] or "chrome" not in p.info["name"].lower():
                continue
            cmd = p.info.get("cmdline") or []
            if any((arg or "").startswith("--user-data-dir=") and (arg.split("=", 1)[1].strip('"') == user_data_dir)
                   for arg in cmd):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def find_chrome_by_port(port: int) -> Optional[psutil.Process]:
    """
    Find Chrome process listening on the specified debug port.

    Args:
        port: Remote debugging port number

    Returns:
        Optional[psutil.Process]: Chrome process if found, None otherwise
    """
    target = f"--remote-debugging-port={port}"
    for p in psutil.process_iter(["name", "cmdline", "exe"]):
        try:
            if not p.info["name"]:
                continue
            if "chrome" not in p.info["name"].lower():
                continue
            cmd = p.info.get("cmdline") or []
            if any(target in (arg or "") for arg in cmd):
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def find_chrome_by_userdata(user_data_dir: str) -> Optional[psutil.Process]:
    """
    Find the first Chrome process using the specified user-data-dir.

    Args:
        user_data_dir: Path to Chrome user data directory

    Returns:
        Optional[psutil.Process]: Chrome process if found, None otherwise
    """
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if not p.info["name"] or "chrome" not in p.info["name"].lower():
                continue
            cmd = p.info.get("cmdline") or []
            if any((arg or "").startswith("--user-data-dir=") and
                   (arg.split("=", 1)[1].strip('"') == user_data_dir)
                   for arg in cmd):
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def wait_for_process_stable(proc: subprocess.Popen, timeout: float = 2.0) -> bool:
    """
    Wait for process to stabilize and check if it's still running.

    Args:
        proc: Subprocess to check
        timeout: Time to wait in seconds

    Returns:
        bool: True if process is running, False if it exited
    """
    time.sleep(timeout)
    return proc.poll() is None


__all__ = [
    'is_chrome_running_with_userdata',
    'find_chrome_by_port',
    'find_chrome_by_userdata',
    'wait_for_process_stable',
]
