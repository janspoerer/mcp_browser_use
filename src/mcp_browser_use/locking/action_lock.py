"""Action lock management for coordinating browser actions across processes."""

import os
import json
import time
import asyncio
from typing import Dict, Any, Optional

# Global intra-process lock
MCP_INTRA_PROCESS_LOCK: Optional[asyncio.Lock] = None


def get_intra_process_lock() -> asyncio.Lock:
    """Get or create the intra-process asyncio lock."""
    global MCP_INTRA_PROCESS_LOCK
    if MCP_INTRA_PROCESS_LOCK is None:
        MCP_INTRA_PROCESS_LOCK = asyncio.Lock()
    return MCP_INTRA_PROCESS_LOCK


def _read_softlock(path: str) -> Dict[str, Any]:
    """Read softlock JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_softlock(path: str, state: Dict[str, Any]):
    """Write softlock JSON file atomically."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def _acquire_softlock(owner: str, ttl: int, wait: bool = True, wait_timeout: float = None) -> Dict[str, Any]:
    """
    Acquire a softlock for the given owner.

    Args:
        owner: Identifier of the lock owner
        ttl: Time to live in seconds
        wait: Whether to wait for the lock
        wait_timeout: Maximum time to wait (defaults to ACTION_LOCK_WAIT_SECS)

    Returns:
        Dictionary with lock acquisition status
    """
    from .file_mutex import _lock_paths, _file_mutex, _now
    from ..helpers import FILE_MUTEX_STALE_SECS, ACTION_LOCK_WAIT_SECS

    if wait_timeout is None:
        wait_timeout = ACTION_LOCK_WAIT_SECS

    softlock_json, softlock_mutex, _ = _lock_paths()
    deadline = _now() + max(0.0, wait_timeout)

    while True:
        try:
            with _file_mutex(softlock_mutex, stale_secs=FILE_MUTEX_STALE_SECS, wait_timeout=min(5.0, max(0.1, deadline - _now()))):
                state = _read_softlock(softlock_json)
                cur_owner = state.get("owner")
                expires_at = float(state.get("expires_at", 0.0))

                if not cur_owner or expires_at <= _now() or cur_owner == owner:
                    new_exp = _now() + ttl
                    _write_softlock(softlock_json, {"owner": owner, "expires_at": new_exp})
                    return {"acquired": True, "owner": owner, "expires_at": new_exp}

                result = {
                    "acquired": False,
                    "owner": cur_owner,
                    "expires_at": float(expires_at),
                    "message": "busy",
                }
        except TimeoutError:
            if not wait or _now() >= deadline:
                # Best-effort read without mutex for context
                state = _read_softlock(softlock_json)
                return {
                    "acquired": False,
                    "owner": state.get("owner"),
                    "expires_at": float(state.get("expires_at", 0.0)) if state.get("expires_at") else None,
                    "message": "mutex_timeout",
                }

        if not wait or _now() >= deadline:
            return result
        time.sleep(0.05)


def _release_action_lock(owner: str) -> bool:
    """
    Release the action lock if owned by the given owner.

    Args:
        owner: Identifier of the lock owner

    Returns:
        True if lock was released, False otherwise
    """
    from .file_mutex import _lock_paths, _file_mutex
    from ..helpers import FILE_MUTEX_STALE_SECS

    softlock_json, softlock_mutex, _ = _lock_paths()
    with _file_mutex(softlock_mutex, stale_secs=FILE_MUTEX_STALE_SECS, wait_timeout=5.0):
        state = _read_softlock(softlock_json)
        if state.get("owner") == owner:
            _write_softlock(softlock_json, {})
            return True
        return False


def _renew_action_lock(owner: str, ttl: int) -> bool:
    """
    Extend the action lock if owned by `owner`, or if stale. No-op if owned by someone else and not stale.
    Also updates the window registry heartbeat as a piggyback optimization.

    Args:
        owner: Identifier of the lock owner
        ttl: Time to live in seconds

    Returns:
        True if we wrote a new expiry, False otherwise
    """
    from .file_mutex import _lock_paths, _file_mutex, _now
    from .window_registry import _update_window_heartbeat
    from ..helpers import FILE_MUTEX_STALE_SECS

    softlock_json, softlock_mutex, _ = _lock_paths()
    try:
        with _file_mutex(softlock_mutex, stale_secs=FILE_MUTEX_STALE_SECS, wait_timeout=1.0):
            state = _read_softlock(softlock_json)
            cur_owner = state.get("owner")
            expires_at = float(state.get("expires_at", 0.0) or 0.0)

            if cur_owner == owner or expires_at <= _now():
                new_exp = _now() + int(ttl)
                _write_softlock(softlock_json, {"owner": owner, "expires_at": new_exp})

                # Piggyback: update window heartbeat while we're renewing the lock
                try:
                    _update_window_heartbeat(owner)
                except Exception:
                    pass  # Non-critical

                return True
            return False
    except Exception:
        return False


def _acquire_action_lock_or_error(owner: str) -> Optional[str]:
    """
    Acquire action lock or return error message.

    Args:
        owner: Identifier of the lock owner

    Returns:
        None if lock acquired, error JSON string otherwise
    """
    from ..helpers import ACTION_LOCK_TTL_SECS, ACTION_LOCK_WAIT_SECS

    res = _acquire_softlock(owner=owner, ttl=ACTION_LOCK_TTL_SECS, wait=True, wait_timeout=ACTION_LOCK_WAIT_SECS)
    if res.get("acquired"):
        return None

    return json.dumps({
        "ok": False,
        "error": "locked",
        "owner": res.get("owner"),
        "expires_at": res.get("expires_at"),
        "lock_ttl_seconds": ACTION_LOCK_TTL_SECS,
    })


__all__ = [
    'get_intra_process_lock',
    '_read_softlock',
    '_write_softlock',
    '_acquire_softlock',
    '_release_action_lock',
    '_renew_action_lock',
    '_acquire_action_lock_or_error',
]
