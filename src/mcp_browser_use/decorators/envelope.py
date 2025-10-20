# mcp_browser_use/decorators/envelope.py

import os
import json
import asyncio
import inspect
import datetime
import functools
import traceback
from typing import Any, Callable


__all__ = [
    "tool_envelope",
]


def tool_envelope(func: Callable):
    """
    Minimal decorator for MCP tool functions:
      - Works with both async and sync callables.
      - On success: ensures the return value is a string (json.dumps for non-strings).
      - On error: returns a uniform JSON string with a summary and optional traceback.
    Environment:
      - Set MBU_TOOL_ERRORS_TRACEBACK=0 to suppress traceback in error payloads.
    """
    include_tb = os.getenv("MBU_TOOL_ERRORS_TRACEBACK", "1") not in ("0", "false", "False")

    def _normalize(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return value.decode("utf-8", "replace")
        try:
            return json.dumps(value, ensure_ascii=False, default=lambda o: getattr(o, "__dict__", repr(o)))
        except Exception:
            # Fallback to a best-effort string
            try:
                return str(value)
            except Exception:
                return ""

    def _error_payload(err: Exception) -> str:
        tb = traceback.format_exc() if include_tb else None
        payload = {
            "ok": False,
            "summary": f"{err.__class__.__name__}: {err}",
            "error": {
                "type": err.__class__.__name__,
                "message": str(err),
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if tb:
            payload["error"]["traceback"] = tb
        return json.dumps(payload, ensure_ascii=False)

    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
            except asyncio.CancelledError:
                # Preserve cooperative cancellation semantics
                raise
            except Exception as e:
                return _error_payload(e)
            return _normalize(result)
        return wrapper
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                return _error_payload(e)
            return _normalize(result)
        return wrapper
