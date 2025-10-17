"""Process and port management."""

import os
import json
import time
import socket
import tempfile
import psutil
from typing import Optional, Tuple

# Global process tag
MY_TAG: Optional[str] = None


def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    """Check if a port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_free_port() -> int:
    """Get a free port by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ensure_process_tag() -> str:
    """Get or create the global process tag."""
    global MY_TAG
    if MY_TAG is None:
        MY_TAG = make_process_tag()
    return MY_TAG


def make_process_tag() -> str:
    """Create a unique process tag."""
    import uuid
    return f"agent:{uuid.uuid4().hex}"


def _read_json(path: str) -> Optional[dict]:
    """Read JSON file, return None on error."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def rendezvous_path(config: dict) -> str:
    """Get path to rendezvous file for this profile."""
    from ..helpers import profile_key
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_rendezvous_{profile_key(config)}.json")


def chromedriver_log_path(config: dict) -> str:
    """Get path to chromedriver log file for this profile and process."""
    from ..helpers import profile_key
    return os.path.join(tempfile.gettempdir(), f"chromedriver_shared_{profile_key(config)}_{os.getpid()}.log")


def read_rendezvous(config: dict) -> Tuple[Optional[int], Optional[int]]:
    """
    Read rendezvous file to find existing Chrome debug port and PID.

    Returns:
        Tuple of (port, pid) or (None, None) if not found/invalid
    """
    from ..helpers import RENDEZVOUS_TTL_SEC
    from .devtools import is_debugger_listening

    path = rendezvous_path(config)
    try:
        if not os.path.exists(path):
            return None, None
        if (time.time() - os.path.getmtime(path)) > RENDEZVOUS_TTL_SEC:
            return None, None
        data = _read_json(path) or {}
        port = int(data.get("port", 0)) or None
        pid = int(data.get("pid", 0)) or None
        if not port or not pid:
            return None, None
        if not psutil.pid_exists(pid):
            return None, None
        if not is_debugger_listening("127.0.0.1", port):
            return None, None
        return port, pid
    except Exception:
        return None, None


def write_rendezvous(config: dict, port: int, pid: int) -> None:
    """Write rendezvous file with Chrome debug port and PID."""
    path = rendezvous_path(config)
    tmp = path + ".tmp"
    data = {"port": port, "pid": pid, "ts": time.time()}
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        pass


def clear_rendezvous(config: dict) -> None:
    """Remove rendezvous file."""
    try:
        os.remove(rendezvous_path(config))
    except Exception:
        pass


__all__ = [
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
]
