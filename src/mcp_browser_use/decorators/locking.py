# mcp_browser_use/decorators/locking.py
#
# Known Limitation: Iframe Context
# Multi-step iframe interactions require specifying iframe_selector for each action.
# This is intentional design to prevent context state bugs.


"""
If multiple agents are working at the same time, there will be some natural
concurrency because the agents anyway need to produce tokens (think) before
calling the next action. This makes issues arising from sequential locking a
bit less pronounced.


"""

import os
import json
import asyncio
import inspect
import warnings
import functools
import contextlib
import threading
import time as _time
from typing import Callable


__all__ = [
    "exclusive_browser_access",
    "serialize_only",
    "deprecated",
]


def deprecated(reason: str):
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kwargs):
            warnings.warn(f"{func.__name__} is deprecated: {reason}", DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        return _wrapper
    return _decorator


def _validate_config_or_error():
    """
    Validate browser configuration early to provide clear error messages.

    Returns None if valid, or JSON error string if invalid.
    """
    try:
        from mcp_browser_use.config.environment import get_env_config
        get_env_config()  # Just validate - don't store since config never changes
        return None  # Valid config
    except Exception as e:
        error_payload = {
            "ok": False,
            "error": "invalid_configuration",
            "message": f"Browser configuration error: {str(e)}. Please check your environment variables.",
            "details": {
                "required": ["CHROME_PROFILE_USER_DATA_DIR or BETA_PROFILE_USER_DATA_DIR or CANARY_PROFILE_USER_DATA_DIR"],
                "optional": ["CHROME_EXECUTABLE_PATH", "CHROME_REMOTE_DEBUG_PORT"]
            }
        }
        return json.dumps(error_payload)


def exclusive_browser_access(_func=None):
    """
    Acquire the action lock, keep it alive with a heartbeat while the function runs,
    and renew once on exit. Also serializes calls within this process.
    Use on tools that mutate or depend on exclusive browser access.
    """

    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Early config validation to prevent race condition
                config_error = _validate_config_or_error()
                if config_error:
                    return config_error

                # Import lazily to avoid cycles at module import time
                from mcp_browser_use.constants import ACTION_LOCK_TTL_SECS
                from mcp_browser_use.locking.action_lock import (
                    get_intra_process_lock,
                    _acquire_action_lock_or_error,
                    _renew_action_lock,
                )
                from mcp_browser_use.browser.process import ensure_process_tag

                # Ensure process tag exists
                owner = ensure_process_tag()

                # In-process serialization across tools
                lock = get_intra_process_lock()
                async with lock:
                    # Acquire cross-process action lock (waits up to ACTION_LOCK_WAIT_SECS)
                    err = _acquire_action_lock_or_error(owner)
                    if err:
                        # err is already a JSON string; let your tool_envelope pass it through
                        return err

                    stop = asyncio.Event()

                    async def _beater():
                        try:
                            while not stop.is_set():
                                try:
                                    await asyncio.wait_for(stop.wait(), timeout=1.0)
                                    break
                                except asyncio.TimeoutError:
                                    pass
                                try:
                                    _renew_action_lock(owner, ttl=ACTION_LOCK_TTL_SECS)
                                except Exception:
                                    pass
                        except asyncio.CancelledError:
                            pass

                    task = asyncio.create_task(_beater())
                    try:
                        return await func(*args, **kwargs)
                    finally:
                        stop.set()
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task
                        with contextlib.suppress(Exception):
                            _renew_action_lock(owner, ttl=ACTION_LOCK_TTL_SECS)
            return wrapper

        # Optional sync path (rare in your code); no asyncio.Lock here.
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Early config validation to prevent race condition
            config_error = _validate_config_or_error()
            if config_error:
                return config_error

            from mcp_browser_use.constants import ACTION_LOCK_TTL_SECS
            from mcp_browser_use.locking.action_lock import (
                _acquire_action_lock_or_error,
                _renew_action_lock,
            )
            from mcp_browser_use.browser.process import ensure_process_tag

            # Ensure process tag exists
            owner = ensure_process_tag()



            err = _acquire_action_lock_or_error(owner)
            if err:
                return err

            stop = False
            def _beater():
                nonlocal stop
                while not stop:
                    _time.sleep(1.0)
                    try:
                        _renew_action_lock(owner, ttl=ACTION_LOCK_TTL_SECS)
                    except Exception:
                        pass

            t = threading.Thread(target=_beater, daemon=True)
            t.start()
            try:
                return func(*args, **kwargs)
            finally:
                stop = True
                with contextlib.suppress(Exception):
                    t.join(timeout=0.5)
                with contextlib.suppress(Exception):
                    _renew_action_lock(owner, ttl=ACTION_LOCK_TTL_SECS)

        return wrapper

    return decorator if _func is None else decorator(_func)


@deprecated("Use exclusive_browser_access instead")
def serialize_only(fn):
    """
    This decorator is used to prevent race conditions when multiple async
    operations try to access shared browser resources simultaneously. For
    example, if two MCP tools try to interact with the same browser window
    at the same time, this decorator ensures they execute sequentially
    rather than potentially interfering with each other.

    It's particularly important for browser automation where:
    - DOM operations need to be atomic
    - Window/tab switching must be coordinated
    - Screenshot capture shouldn't happen during navigation
    - Form filling should complete before other actions

    The get_intra_process_lock() returns a shared asyncio.Lock instance
    that all decorated functions use, ensuring serialization across
    different MCP tool functions.

    """
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        # Lazy import to avoid import-time cycles
        from ..helpers import get_intra_process_lock
        lock = get_intra_process_lock()
        async with lock:
            return await fn(*args, **kwargs)
    return wrapper
