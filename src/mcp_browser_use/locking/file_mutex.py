"""File-based mutex and startup lock implementation."""

import os
import time
import shutil
import tempfile
import contextlib
import psutil
from pathlib import Path


def _now() -> float:
    """Return current time as float timestamp."""
    return time.time()


def _lock_paths():
    """
    Get paths for lock files based on profile key.

    Returns:
        Tuple of (softlock_json, softlock_mutex, startup_mutex) paths
    """
    # Import here to avoid circular dependency
    from ..helpers import profile_key, get_env_config, LOCK_DIR

    key = profile_key(get_env_config())  # stable across processes; independent of port
    base = Path(LOCK_DIR)
    base.mkdir(parents=True, exist_ok=True)
    softlock_json = base / f"{key}.softlock.json"
    softlock_mutex = base / f"{key}.softlock.mutex"
    startup_mutex = base / f"{key}.startup.mutex"
    return str(softlock_json), str(softlock_mutex), str(startup_mutex)


@contextlib.contextmanager
def _file_mutex(path: str, stale_secs: int, wait_timeout: float):
    """
    Simple cross-process mutex via an exclusive file create.
    Removes stale mutex if older than stale_secs.
    """
    start = _now()
    p = Path(path)
    while True:
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            try:
                st = p.stat()
                if _now() - st.st_mtime > stale_secs:
                    p.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if _now() - start > wait_timeout:
                raise TimeoutError(f"Timed out waiting for mutex {p}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


def start_lock_dir(config: dict) -> str:
    """Get path to startup lock directory for the given profile."""
    from ..helpers import profile_key
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_start_lock_{profile_key(config)}")


def acquire_start_lock(config: dict, timeout_sec: float = None) -> bool:
    """
    Acquire startup lock to ensure only one process starts Chrome.

    Args:
        config: Configuration dictionary
        timeout_sec: Timeout in seconds (defaults to START_LOCK_WAIT_SEC from helpers)

    Returns:
        True if lock acquired, False on timeout
    """
    if timeout_sec is None:
        from ..helpers import START_LOCK_WAIT_SEC
        timeout_sec = START_LOCK_WAIT_SEC

    lock_dir = start_lock_dir(config)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            os.mkdir(lock_dir)
            with open(os.path.join(lock_dir, "pid"), "w") as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            # If owner died, break it
            pid_file = os.path.join(lock_dir, "pid")
            try:
                if os.path.exists(pid_file):
                    with open(pid_file, "r") as f:
                        pid_txt = f.read().strip()
                    pid = int(pid_txt) if pid_txt.isdigit() else None
                else:
                    pid = None
            except Exception:
                pid = None
            if pid and not psutil.pid_exists(pid):
                try:
                    shutil.rmtree(lock_dir, ignore_errors=True)
                    continue
                except Exception:
                    pass
            time.sleep(0.05)
    return False


def release_start_lock(config: dict) -> None:
    """Release startup lock."""
    try:
        shutil.rmtree(start_lock_dir(config), ignore_errors=True)
    except Exception:
        pass


__all__ = [
    '_now',
    '_lock_paths',
    '_file_mutex',
    'start_lock_dir',
    'acquire_start_lock',
    'release_start_lock',
]
