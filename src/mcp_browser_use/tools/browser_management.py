"""Browser lifecycle management tool implementations."""

import json
import psutil
from pathlib import Path
import mcp_browser_use.helpers as helpers
from mcp_browser_use.utils.diagnostics import collect_diagnostics


async def start_browser():
    owner = helpers.ensure_process_tag()
    try:
        helpers._ensure_driver_and_window()

        if helpers.DRIVER is None:
            diag = collect_diagnostics(None, None, helpers.get_env_config())
            if isinstance(diag, str):
                    diag = {"summary": diag}
            return json.dumps({
                "ok": False,
                "error": "driver_not_initialized",
                "driver_initialized": False,
                "debugger": (
                    f"{helpers.DEBUGGER_HOST}:{helpers.DEBUGGER_PORT}"
                    if (helpers.DEBUGGER_HOST and helpers.DEBUGGER_PORT) else None
                ),
                "diagnostics": diag,
                "message": "Failed to attach/launch a debuggable Chrome session."
            })

        handle = getattr(helpers.DRIVER, "current_window_handle", None)
        try:
            helpers._close_extra_blank_windows_safe(helpers.DRIVER, exclude_handles={handle} if handle else None)
        except Exception:
            pass

        # Wait until the page is ready. Get a snapshot.
        helpers._wait_document_ready(timeout=5.0)
        try:
            snapshot = helpers._make_page_snapshot()
        except Exception:
            snapshot = None
        snapshot = snapshot or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }

        msg = ( # Human-friendly message
            f"Browser session created successfully. "
            f"Session ID: {owner}. "
            f"Current URL: {snapshot.get('url') or 'about:blank'}"
        )

        payload = {
            "ok": True,
            "session_id": owner,
            "debugger": f"{helpers.DEBUGGER_HOST}:{helpers.DEBUGGER_PORT}" if (helpers.DEBUGGER_HOST and helpers.DEBUGGER_PORT) else None,
            "lock_ttl_seconds": helpers.ACTION_LOCK_TTL_SECS,
            "snapshot": snapshot,
            "message": msg,
        }

        return json.dumps(payload)
    except Exception as e:
        diag = collect_diagnostics(helpers.DRIVER, e, helpers.get_env_config())
        snapshot = helpers._make_page_snapshot() or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})


async def unlock_browser():
    owner = helpers.ensure_process_tag()
    released = helpers._release_action_lock(owner)
    return json.dumps({"ok": True, "released": bool(released)})

async def close_browser() -> str:
    try:
        closed = helpers.close_singleton_window()
        msg = "Browser window closed successfully" if closed else "No window to close"
        return json.dumps({"ok": True, "closed": bool(closed), "message": msg})
    except Exception as e:
        diag = collect_diagnostics(helpers.DRIVER, e, helpers.get_env_config())
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag})

async def force_close_all_chrome() -> str:
    """
    Force close all Chrome processes, quit driver, and clean up all state.
    Use this to recover from stuck Chrome instances or when normal close_browser fails.
    """
    # Note: Cannot use global statement with module attributes, so we access helpers.DRIVER directly

    killed_processes = []
    errors = []

    try:
        # 1. Try to quit the Selenium driver gracefully
        if helpers.DRIVER is not None:
            try:
                helpers.DRIVER.quit()
            except Exception as e:
                errors.append(f"Driver quit failed: {e}")
            helpers.DRIVER = None

        # 2. Get config to find which Chrome processes to kill
        try:
            cfg = helpers.get_env_config()
            user_data_dir = cfg.get("user_data_dir", "")
        except Exception as e:
            user_data_dir = ""
            errors.append(f"Could not get config: {e}")

        # 3. Kill all Chrome processes using the MCP profile
        # First, try targeted kill based on user_data_dir
        chrome_processes_found = []
        for p in psutil.process_iter(["name", "cmdline", "pid"]):
            try:
                if not p.info.get("name"):
                    continue
                if "chrome" not in p.info["name"].lower():
                    continue
                chrome_processes_found.append(p)

                # If we have a user_data_dir, check if this process matches
                if user_data_dir:
                    cmd = p.info.get("cmdline")
                    if cmd:
                        # Check if any argument contains our user_data_dir path
                        # Use 'in' check because paths might have different separators or be normalized differently
                        user_data_normalized = user_data_dir.replace("\\", "/").lower()
                        for arg in cmd:
                            if arg and "--user-data-dir" in arg:
                                arg_normalized = arg.replace("\\", "/").lower()
                                if user_data_normalized in arg_normalized:
                                    p.kill()
                                    killed_processes.append(p.info["pid"])
                                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                errors.append(f"Could not access process: {e}")

        # 4. Fallback: If no Chrome processes were killed but some were found, kill them all
        # This ensures we don't leave zombie Chrome processes
        if not killed_processes and chrome_processes_found:
            for p in chrome_processes_found:
                try:
                    p.kill()
                    killed_processes.append(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    errors.append(f"Could not kill process in fallback: {e}")

        # 5. Clean up global state
        helpers.DEBUGGER_HOST = None
        helpers.DEBUGGER_PORT = None
        helpers.TARGET_ID = None
        helpers.WINDOW_ID = None

        # 6. Release locks
        try:
            if helpers.MY_TAG:
                helpers._release_action_lock(helpers.MY_TAG)
        except Exception as e:
            errors.append(f"Lock release failed: {e}")

        # 7. Clean up lock files
        try:
            if user_data_dir:
                lock_dir = Path(helpers.LOCK_DIR)
                # lock_dir = Path(tempfile.gettempdir()) / "mcp_browser_locks"
                if lock_dir.exists():
                    profile_key_val = helpers.profile_key(cfg) if cfg else ""
                    for lock_file in lock_dir.glob(f"*{profile_key_val}*"):
                        try:
                            lock_file.unlink()
                        except Exception:
                            pass
        except Exception as e:
            errors.append(f"Lock file cleanup failed: {e}")

        msg = f"Force closed Chrome. Killed {len(killed_processes)} processes."
        if errors:
            msg += f" Errors: {'; '.join(errors)}"

        return json.dumps({
            "ok": True,
            "killed_processes": killed_processes,
            "errors": errors,
            "message": msg
        })

    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": str(e),
            "killed_processes": killed_processes,
            "errors": errors
        })


__all__ = ['start_browser', 'unlock_browser', 'close_browser', 'force_close_all_chrome']
