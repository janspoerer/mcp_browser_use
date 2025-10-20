"""DevTools protocol operations."""

import os
import json
import time
import urllib.request
from pathlib import Path
from typing import Optional

import logging
logger = logging.getLogger(__name__)


def _read_devtools_active_port(user_data_dir: str) -> int | None:
    """Read debug port from DevToolsActivePort file."""
    p = Path(user_data_dir) / "DevToolsActivePort"
    if not p.exists():
        return None
    try:
        first = p.read_text().splitlines()[0].strip()
        return int(first)
    except Exception:
        return None


def _same_dir(a: str, b: str) -> bool:
    """Check if two paths refer to the same directory."""
    if not a or not b:
        return False
    try:
        return Path(a).resolve() == Path(b).resolve()
    except Exception:
        return False


def _devtools_user_data_dir(host: str, port: int, timeout: float = 1.5) -> str | None:
    """Get user data directory from DevTools protocol."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/json/version", timeout=timeout) as resp:
            meta = json.load(resp)
            return meta.get("userDataDir")
    except Exception:
        return None


def _verify_port_matches_profile(host: str, port: int, expected_dir: str) -> bool:
    """Verify that a debug port belongs to the expected profile."""
    actual = _devtools_user_data_dir(host, port)
    return _same_dir(actual, expected_dir)


def is_debugger_listening(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if Chrome DevTools debugger is listening on a port."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/json/version", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def devtools_active_port_from_file(user_data_dir: str) -> Optional[int]:
    """
    If Chrome is running this profile with remote debugging enabled,
    it writes 'DevToolsActivePort' in the user-data-dir. Return that port if valid.
    """
    try:
        p = Path(user_data_dir) / "DevToolsActivePort"
        if not p.exists():
            return None
        lines = p.read_text().splitlines()
        if not lines:
            return None
        first = lines[0].strip()
        return int(first) if first.isdigit() else None
    except Exception:
        return None


def _ensure_debugger_ready(cfg: dict, max_wait_secs: float | None = None) -> None:
    """
    Ensure a debuggable Chrome is running for the configured user-data-dir,
    set DEBUGGER_HOST/DEBUGGER_PORT accordingly.
    """
    from ..helpers import ALLOW_ATTACH_ANY
    from .process import _is_port_open
    from .chrome import start_or_attach_chrome_from_env, _launch_chrome_with_debug
    
    # Import global variables
    import mcp_browser_use.helpers as helpers_module
    
    try:
        host, port, _ = start_or_attach_chrome_from_env(cfg)
        if not (ALLOW_ATTACH_ANY or _verify_port_matches_profile(host, port, cfg["user_data_dir"])):
            raise RuntimeError("DevTools port does not belong to the configured profile")
        helpers_module.DEBUGGER_HOST, helpers_module.DEBUGGER_PORT = host, port
        return
    except Exception:
        helpers_module.DEBUGGER_HOST = None
        helpers_module.DEBUGGER_PORT = None

    # Allow override by env; default to 10 seconds
    try:
        max_wait_secs = float(os.getenv("MCP_DEVTOOLS_MAX_WAIT_SECS", "10")) if max_wait_secs is None else float(max_wait_secs)
    except Exception:
        max_wait_secs = 10.0

    udir = cfg["user_data_dir"]
    env_port = os.getenv("CHROME_REMOTE_DEBUG_PORT")
    try:
        env_port = int(env_port) if env_port else None
    except Exception:
        env_port = None

    # 1) If the profile already wrote DevToolsActivePort, try to attach to that.
    file_port = _read_devtools_active_port(udir)
    if file_port and _is_port_open("127.0.0.1", file_port):
        helpers_module.DEBUGGER_HOST, helpers_module.DEBUGGER_PORT = "127.0.0.1", file_port
        return

    # 2) If allowed, attach to a known open port
    if ALLOW_ATTACH_ANY:
        for p in filter(None, [env_port, 9223]):
            if _is_port_open("127.0.0.1", p):
                helpers_module.DEBUGGER_HOST, helpers_module.DEBUGGER_PORT = "127.0.0.1", p
                return

    # 3) Launch our own debuggable Chrome
    port = env_port or 9225
    _launch_chrome_with_debug(cfg, port)

    # Wait until Chrome writes the file OR the TCP port answers
    t0 = time.time()
    while time.time() - t0 < max_wait_secs:
        p = _read_devtools_active_port(udir)
        if (p and _is_port_open("127.0.0.1", p)) or _is_port_open("127.0.0.1", port):
            helpers_module.DEBUGGER_HOST, helpers_module.DEBUGGER_PORT = "127.0.0.1", p or port
            return
        time.sleep(0.1)

    helpers_module.DEBUGGER_HOST = helpers_module.DEBUGGER_PORT = None


def _handle_for_target(driver, target_id: Optional[str]) -> Optional[str]:
    """Get window handle for a Chrome DevTools target ID."""
    import time
    
    if not target_id:
        return None

    # Fast path: Selenium handle suffix matches CDP targetId
    for h in driver.window_handles:
        try:
            if h.endswith(target_id):
                return h
        except Exception:
            pass

    # Nudge Chrome to foreground that target, then retry
    try:
        driver.execute_cdp_cmd("Target.activateTarget", {"targetId": target_id})
    except Exception:
        pass

    for _ in range(20):  # ~1s total
        for h in driver.window_handles:
            try:
                if h.endswith(target_id):
                    return h
            except Exception:
                continue
        time.sleep(0.05)

    # Robust path: probe handles via CDP
    current = driver.current_window_handle if driver.window_handles else None
    try:
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                info = driver.execute_cdp_cmd("Target.getTargetInfo", {}) or {}
                tid = (info.get("targetInfo") or {}).get("targetId") or info.get("targetId")
                if tid == target_id:
                    return h
            except Exception:
                continue

        # Last resort: enumerate all targets
        try:
            targets = driver.execute_cdp_cmd("Target.getTargets", {}) or {}
            for ti in (targets.get("targetInfos") or []):
                if ti.get("targetId") == target_id:
                    try:
                        driver.execute_cdp_cmd("Target.activateTarget", {"targetId": target_id})
                    except Exception:
                        pass
                    # One last quick scan
                    for h in driver.window_handles:
                        try:
                            if h.endswith(target_id):
                                return h
                        except Exception:
                            continue
                    break
        except Exception:
            pass
    finally:
        if current and current in getattr(driver, "window_handles", []):
            try:
                driver.switch_to.window(current)
            except Exception:
                pass

    return None


__all__ = [
    '_read_devtools_active_port',
    'devtools_active_port_from_file',
    '_devtools_user_data_dir',
    '_verify_port_matches_profile',
    '_same_dir',
    'is_debugger_listening',
    '_ensure_debugger_ready',
    '_handle_for_target',
]
