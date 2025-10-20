"""Browser lifecycle management tool implementations."""

import json
import psutil
from pathlib import Path
from ..context import get_context, reset_context
from ..config import get_env_config, profile_key
from ..constants import ACTION_LOCK_TTL_SECS
from ..utils.diagnostics import collect_diagnostics

# Import specific functions we need
from ..browser.driver import (
    _ensure_driver_and_window,
    close_singleton_window,
    _close_extra_blank_windows_safe,
    ensure_process_tag,
)
from ..actions.navigation import _wait_document_ready
from ..actions.screenshots import _make_page_snapshot
from ..locking.action_lock import _release_action_lock


async def start_browser():
    """
    Start browser session or open new window in existing session.

    Returns:
        JSON string with session info and snapshot
    """
    ctx = get_context()

    # Ensure process tag
    if ctx.process_tag is None:
        ctx.process_tag = ensure_process_tag()

    owner = ctx.process_tag

    try:
        # Initialize driver and window
        _ensure_driver_and_window()

        # Check if initialization succeeded
        if not ctx.is_driver_initialized():
            diag = collect_diagnostics(None, None, ctx.config)
            if isinstance(diag, str):
                diag = {"summary": diag}

            return json.dumps({
                "ok": False,
                "error": "driver_not_initialized",
                "driver_initialized": False,
                "debugger": ctx.get_debugger_address(),
                "diagnostics": diag,
                "message": "Failed to attach/launch a debuggable Chrome session."
            })

        # Clean up extra blank windows
        handle = getattr(ctx.driver, "current_window_handle", None)
        try:
            _close_extra_blank_windows_safe(
                ctx.driver,
                exclude_handles={handle} if handle else None
            )
        except Exception:
            pass

        # Wait for page ready and get snapshot
        _wait_document_ready(timeout=5.0)
        try:
            snapshot = _make_page_snapshot()
        except Exception:
            snapshot = None

        snapshot = snapshot or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }

        msg = (
            f"Browser session created successfully. "
            f"Session ID: {owner}. "
            f"Current URL: {snapshot.get('url') or 'about:blank'}"
        )

        payload = {
            "ok": True,
            "session_id": owner,
            "debugger": ctx.get_debugger_address(),
            "lock_ttl_seconds": ACTION_LOCK_TTL_SECS,
            "snapshot": snapshot,
            "message": msg,
        }

        return json.dumps(payload)

    except Exception as e:
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        snapshot = _make_page_snapshot() or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }
        return json.dumps({
            "ok": False,
            "error": str(e),
            "diagnostics": diag,
            "snapshot": snapshot
        })


async def unlock_browser():
    """Release the action lock for this process."""
    ctx = get_context()

    if ctx.process_tag is None:
        ctx.process_tag = ensure_process_tag()

    owner = ctx.process_tag
    released = _release_action_lock(owner)

    return json.dumps({
        "ok": True,
        "released": bool(released)
    })

async def close_browser() -> str:
    """Close the browser window for this session."""
    ctx = get_context()

    try:
        closed = close_singleton_window()
        msg = "Browser window closed successfully" if closed else "No window to close"

        return json.dumps({
            "ok": True,
            "closed": bool(closed),
            "message": msg
        })

    except Exception as e:
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        return json.dumps({
            "ok": False,
            "error": str(e),
            "diagnostics": diag
        })

async def force_close_all_chrome() -> str:
    """
    Force close all Chrome processes, quit driver, and clean up all state.
    Use this to recover from stuck Chrome instances.
    """
    ctx = get_context()
    killed_processes = []
    errors = []

    try:
        # 1. Try to quit the Selenium driver gracefully
        if ctx.driver is not None:
            try:
                ctx.driver.quit()
            except Exception as e:
                errors.append(f"Driver quit failed: {e}")

            ctx.driver = None

        # 2. Get config to find which Chrome processes to kill
        user_data_dir = ctx.config.get("user_data_dir", "")
        if not user_data_dir:
            try:
                cfg = get_env_config()
                user_data_dir = cfg.get("user_data_dir", "")
            except Exception as e:
                errors.append(f"Could not get config: {e}")

        # 3. Kill all Chrome processes using the MCP profile
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

        # 4. Fallback: If no processes killed but some found, kill them all
        if not killed_processes and chrome_processes_found:
            for p in chrome_processes_found:
                try:
                    p.kill()
                    killed_processes.append(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    errors.append(f"Could not kill process in fallback: {e}")

        # 5. Clean up context state
        ctx.debugger_host = None
        ctx.debugger_port = None
        ctx.reset_window_state()

        # 6. Release locks
        try:
            if ctx.process_tag:
                _release_action_lock(ctx.process_tag)
        except Exception as e:
            errors.append(f"Lock release failed: {e}")

        # 7. Clean up lock files
        try:
            if user_data_dir:
                lock_dir = Path(ctx.lock_dir)
                if lock_dir.exists():
                    profile_key_val = profile_key(ctx.config) if ctx.config else ""
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
