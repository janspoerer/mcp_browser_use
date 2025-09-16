# mcp_browser_use/decorators/ensure.py
import json
import inspect
import functools

def ensure_driver_ready(_func=None, *, include_snapshot=False, include_diagnostics=False):
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                import mcp_browser_use.helpers as helpers  # module import, not from-import

                # Check if driver is already initialized, but don't auto-initialize
                if helpers.DRIVER is None:
                    payload = {
                        "ok": False, 
                        "error": "browser_not_started",
                        "message": "Browser session not started. Please call 'start_browser' first before using browser actions."
                    }
                    if include_snapshot:
                        payload["snapshot"] = {"url": None, "title": None, "html": "", "truncated": False}
                    if include_diagnostics:
                        try:
                            payload["diagnostics"] = helpers.collect_diagnostics(None, None, helpers.get_env_config())
                        except Exception:
                            pass
                    return json.dumps(payload)
                
                # Ensure we have a valid window for this driver
                try:
                    helpers._ensure_singleton_window(helpers.DRIVER)
                except Exception:
                    payload = {
                        "ok": False,
                        "error": "browser_window_lost", 
                        "message": "Browser window was lost. Please call 'start_browser' to create a new session."
                    }
                    if include_snapshot:
                        payload["snapshot"] = {"url": None, "title": None, "html": "", "truncated": False}
                    return json.dumps(payload)
                
                return await fn(*args, **kwargs)
            return wrapper
        else:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                import mcp_browser_use.helpers as helpers  # module import, not from-import

                # Check if driver is already initialized, but don't auto-initialize
                if helpers.DRIVER is None:
                    payload = {
                        "ok": False, 
                        "error": "browser_not_started",
                        "message": "Browser session not started. Please call 'start_browser' first before using browser actions."
                    }
                    if include_snapshot:
                        payload["snapshot"] = {"url": None, "title": None, "html": "", "truncated": False}
                    if include_diagnostics:
                        try:
                            payload["diagnostics"] = helpers.collect_diagnostics(None, None, helpers.get_env_config())
                        except Exception:
                            pass
                    return json.dumps(payload)
                
                # Ensure we have a valid window for this driver
                try:
                    helpers._ensure_singleton_window(helpers.DRIVER)
                except Exception:
                    payload = {
                        "ok": False,
                        "error": "browser_window_lost", 
                        "message": "Browser window was lost. Please call 'start_browser' to create a new session."
                    }
                    if include_snapshot:
                        payload["snapshot"] = {"url": None, "title": None, "html": "", "truncated": False}
                    return json.dumps(payload)
                
                return fn(*args, **kwargs)
            return wrapper
    return decorator if _func is None else decorator(_func)