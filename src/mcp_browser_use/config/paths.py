"""Path utilities and management for browser configuration."""

import os
import tempfile
from pathlib import Path

from .environment import profile_key


_DEFAULT_LOCK_DIR = None


def get_lock_dir() -> str:
    """
    Get the lock directory path.

    Uses MCP_BROWSER_LOCK_DIR env var if set, otherwise uses:
        <repo_root>/tmp/mcp_locks

    The directory is created if it doesn't exist.

    Returns:
        Absolute path to lock directory
    """
    global _DEFAULT_LOCK_DIR

    if _DEFAULT_LOCK_DIR is None:
        # Calculate default: <repo_root>/tmp/mcp_locks
        repo_root = Path(__file__).parent.parent.parent.parent
        _DEFAULT_LOCK_DIR = str(repo_root / "tmp" / "mcp_locks")

    lock_dir = os.getenv("MCP_BROWSER_LOCK_DIR") or _DEFAULT_LOCK_DIR

    # Ensure directory exists
    Path(lock_dir).mkdir(parents=True, exist_ok=True)

    return lock_dir


def rendezvous_path(config: dict) -> str:
    """Get the path to the rendezvous file for inter-process communication."""
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_rendezvous_{profile_key(config)}.json")


def start_lock_dir(config: dict) -> str:
    """Get the directory path for the startup lock."""
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_start_lock_{profile_key(config)}")


def chromedriver_log_path(config: dict) -> str:
    """Get the path to the ChromeDriver log file."""
    return os.path.join(tempfile.gettempdir(), f"chromedriver_shared_{profile_key(config)}_{os.getpid()}.log")


def _lock_paths():
    """
    Return paths for the action lock files (softlock JSON, mutex, and startup mutex).
    These paths are based on the profile key and LOCK_DIR environment variable.
    """
    from ..config.environment import get_env_config

    # Get LOCK_DIR from global state
    _DEFAULT_LOCK_DIR = str(Path(__file__).parent.parent.parent.parent / "tmp" / "mcp_locks")
    LOCK_DIR = os.getenv("MCP_BROWSER_LOCK_DIR") or _DEFAULT_LOCK_DIR
    Path(LOCK_DIR).mkdir(parents=True, exist_ok=True)

    key = profile_key(get_env_config())  # stable across processes; independent of port
    base = Path(LOCK_DIR)
    base.mkdir(parents=True, exist_ok=True)
    softlock_json = base / f"{key}.softlock.json"
    softlock_mutex = base / f"{key}.softlock.mutex"
    startup_mutex = base / f"{key}.startup.mutex"
    return str(softlock_json), str(softlock_mutex), str(startup_mutex)


def _window_registry_path() -> str:
    """
    Return the path to the window registry file for tracking window ownership.
    """
    from ..config.environment import get_env_config

    # Get LOCK_DIR from global state
    _DEFAULT_LOCK_DIR = str(Path(__file__).parent.parent.parent.parent / "tmp" / "mcp_locks")
    LOCK_DIR = os.getenv("MCP_BROWSER_LOCK_DIR") or _DEFAULT_LOCK_DIR

    key = profile_key(get_env_config())
    return os.path.join(LOCK_DIR, f"{key}.window_registry.json")


def _same_dir(a: str, b: str) -> bool:
    """Compare two directory paths for equality, normalizing for platform differences."""
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except Exception:
        return a == b
