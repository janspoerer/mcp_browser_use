#region Imports
import os
import sys
import json
import time
import psutil
import socket
import shutil
import asyncio
import hashlib
import tempfile
import platform
import traceback
import subprocess
import contextlib
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Callable, Optional, Tuple, Dict, Any
import io
import base64

import logging
logger = logging.getLogger(__name__)
#endregion Imports

#region Browser
import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchWindowException,
    StaleElementReferenceException,
    WebDriverException,
    ElementClickInterceptedException,
)

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
#endregion

#region Imports Dotenv
from dotenv import load_dotenv, find_dotenv
# __file__ is src/mcp_browser_use/helpers/__init__.py, so go up 4 levels to project root
# _env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(find_dotenv(filename=".env", usecwd=True), override=True)
#endregion

#region Constants / policy parameters
START_LOCK_WAIT_SEC = 8.0                  # How long to wait to acquire the startup lock
RENDEZVOUS_TTL_SEC = 24 * 3600             # How long a rendezvous file is considered valid
#endregion

#region Configuration and keys
def get_env_config() -> dict:
    """
    Read environment variables and validate required ones.

    Prioritizes Chrome Beta over Chrome Canary over Chrome. This is to free the Chrome instance. Chrome is likely
    used by the user already. It is easier to separate the executables. If a user already has the Chrome executable open,
    the MCP will not work properly as the Chrome DevTool Debug mode will not open when Chrome is already open in normal mode.
    We prioritize Chrome Beta because it is more stable than Canary.

    Required:   Either CHROME_PROFILE_USER_DATA_DIR, BETA_PROFILE_USER_DATA_DIR, or CANARY_PROFILE_USER_DATA_DIR
    Optional:   CHROME_PROFILE_NAME (default 'Default')
                CHROME_EXECUTABLE_PATH
                BETA_EXECUTABLE_PATH (overrides CHROME_EXECUTABLE_PATH)
                CANARY_EXECUTABLE_PATH (overrides BETA and CHROME)
                CHROME_REMOTE_DEBUG_PORT

    If BETA_EXECUTABLE_PATH is set, expects:
                BETA_PROFILE_USER_DATA_DIR
                BETA_PROFILE_NAME
    If CANARY_EXECUTABLE_PATH is set, expects:
                CANARY_PROFILE_USER_DATA_DIR
                CANARY_PROFILE_NAME
    """
    # Base (generic) config
    user_data_dir = (os.getenv("CHROME_PROFILE_USER_DATA_DIR") or "").strip()
    if not user_data_dir and not os.getenv("BETA_PROFILE_USER_DATA_DIR") and not os.getenv("CANARY_PROFILE_USER_DATA_DIR"):
        raise EnvironmentError("CHROME_PROFILE_USER_DATA_DIR is required.")

    profile_name = (os.getenv("CHROME_PROFILE_NAME") or "Default").strip() or "Default"
    chrome_path = (os.getenv("CHROME_EXECUTABLE_PATH") or "").strip() or None

    # Prefer Beta > Canary > Generic Chrome
    canary_path = (os.getenv("CANARY_EXECUTABLE_PATH") or "").strip()
    if canary_path:
        chrome_path = canary_path
        user_data_dir = (os.getenv("CANARY_PROFILE_USER_DATA_DIR") or "").strip()
        profile_name = (os.getenv("CANARY_PROFILE_NAME") or "").strip() or "Default"
        if not user_data_dir:
            raise EnvironmentError("CANARY_PROFILE_USER_DATA_DIR is required when CANARY_EXECUTABLE_PATH is set.")

    beta_path = (os.getenv("BETA_EXECUTABLE_PATH") or "").strip()
    if beta_path:
        chrome_path = beta_path
        user_data_dir = (os.getenv("BETA_PROFILE_USER_DATA_DIR") or "").strip()
        profile_name = (os.getenv("BETA_PROFILE_NAME") or "").strip() or "Default"
        if not user_data_dir:
            raise EnvironmentError("BETA_PROFILE_USER_DATA_DIR is required when BETA_EXECUTABLE_PATH is set.")

    fixed_port_env = (os.getenv("CHROME_REMOTE_DEBUG_PORT") or "").strip()
    fixed_port = int(fixed_port_env) if fixed_port_env.isdigit() else None

    if not user_data_dir:
            raise EnvironmentError(
                "No user_data_dir selected. Set CHROME_PROFILE_USER_DATA_DIR, or provide "
                "BETA_EXECUTABLE_PATH + BETA_PROFILE_USER_DATA_DIR (or CANARY_* equivalents)."
            )

    return {
        "user_data_dir": user_data_dir,
        "profile_name": profile_name,
        "chrome_path": chrome_path,
        "fixed_port": fixed_port,
    }

def profile_key(config: Optional[dict] = None) -> str:
    """
    Stable key used by cross-process locks, based on absolute user_data_dir + profile_name.
    - Hard-fails if CHROME_PROFILE_USER_DATA_DIR is missing/blank.
    - If CHROME_PROFILE_STRICT=1 and the directory doesn't exist, hard-fail.
      Otherwise we allow Chrome to create it and we normalize the path for stability.
    """
    if config is None:
        config = get_env_config()

    user_data_dir = (config.get("user_data_dir") or "").strip()
    profile_name = (config.get("profile_name") or "Default").strip() or "Default"

    if not user_data_dir:
        raise EnvironmentError("CHROME_PROFILE_USER_DATA_DIR is required and cannot be empty.")

    strict = os.getenv("CHROME_PROFILE_STRICT", "0") == "1"
    p = Path(user_data_dir)
    if strict and not p.exists():
        raise FileNotFoundError(f"user_data_dir does not exist: {p}")

    # Normalize to a stable absolute string
    try:
        user_data_dir = str(p.resolve())
    except Exception:
        user_data_dir = str(p.absolute())

    raw = f"{user_data_dir}|{profile_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
#endregion

#region Globals
DRIVER = None
DEBUGGER_HOST: Optional[str] = None
DEBUGGER_PORT: Optional[int] = None
MY_TAG: Optional[str] = None
ALLOW_ATTACH_ANY = os.getenv("MCP_ATTACH_ANY_PROFILE", "0") == "1"

# Single-window identity for this process (the MCP server will be started independently by multiple agents; each has its own IDs)
TARGET_ID: Optional[str] = None
WINDOW_ID: Optional[int] = None

# Lock directory - defaults to tmp/ folder in project root for easy visibility
# __file__ is src/mcp_browser_use/helpers/__init__.py, so go up to project root
_DEFAULT_LOCK_DIR = str(Path(__file__).parent.parent.parent.parent / "tmp" / "mcp_locks")
LOCK_DIR = os.getenv("MCP_BROWSER_LOCK_DIR") or _DEFAULT_LOCK_DIR
Path(LOCK_DIR).mkdir(parents=True, exist_ok=True)

# Action lock TTL (post-action exclusivity) and wait time
ACTION_LOCK_TTL_SECS = int(os.getenv("MCP_ACTION_LOCK_TTL", "30"))
ACTION_LOCK_WAIT_SECS = int(os.getenv("MCP_ACTION_LOCK_WAIT", "60"))
FILE_MUTEX_STALE_SECS = int(os.getenv("MCP_FILE_MUTEX_STALE_SECS", "60"))

# Truncation
MAX_SNAPSHOT_CHARS = int(os.getenv("MCP_MAX_SNAPSHOT_CHARS", "10000"))
#endregion

#region Lock
MCP_INTRA_PROCESS_LOCK: Optional[asyncio.Lock] = None
def get_intra_process_lock() -> asyncio.Lock:
    global MCP_INTRA_PROCESS_LOCK
    if MCP_INTRA_PROCESS_LOCK is None:
        MCP_INTRA_PROCESS_LOCK = asyncio.Lock()
    return MCP_INTRA_PROCESS_LOCK

def _renew_action_lock(owner: str, ttl: int) -> bool:
    """
    Extend the action lock if owned by `owner`, or if stale. No-op if owned by someone else and not stale.
    Also updates the window registry heartbeat as a piggyback optimization.
    Returns True if we wrote a new expiry.
    """
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
#endregion

#region Cross-process softlock (JSON + file mutex) keyed by profile_key(CONFIG)
def _now() -> float:
    return time.time()

def _lock_paths():
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

def _read_softlock(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def _write_softlock(path: str, state: Dict[str, Any]):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)

def _acquire_softlock(owner: str, ttl: int, wait: bool = True, wait_timeout: float = ACTION_LOCK_WAIT_SECS) -> Dict[str, Any]:
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
    softlock_json, softlock_mutex, _ = _lock_paths()
    with _file_mutex(softlock_mutex, stale_secs=FILE_MUTEX_STALE_SECS, wait_timeout=5.0):
        state = _read_softlock(softlock_json)
        if state.get("owner") == owner:
            _write_softlock(softlock_json, {})
            return True
        return False

def _acquire_action_lock_or_error(owner: str) -> Optional[str]:
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
#endregion

#region Window Registry (tracks which agent owns which browser window)
WINDOW_REGISTRY_STALE_THRESHOLD = int(os.getenv("MCP_WINDOW_REGISTRY_STALE_SECS", "300"))  # 5 minutes

def _window_registry_path() -> str:
    """Get path to window registry file for this profile."""
    key = profile_key(get_env_config())
    return str(Path(LOCK_DIR) / f"{key}.window_registry.json")

def _read_window_registry() -> Dict[str, Any]:
    """Read the window registry. Returns empty dict if not found or invalid."""
    path = _window_registry_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def _write_window_registry(registry: Dict[str, Any]):
    """Write window registry atomically using temp file + rename."""
    path = _window_registry_path()
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass  # Non-critical if write fails

def _register_window(agent_id: str, target_id: str, window_id: Optional[int]):
    """Register a window as owned by this agent."""
    registry = _read_window_registry()
    registry[agent_id] = {
        "target_id": target_id,
        "window_id": window_id,
        "pid": os.getpid(),
        "last_heartbeat": time.time(),
        "created_at": time.time(),
    }
    _write_window_registry(registry)

def _update_window_heartbeat(agent_id: str):
    """Update the heartbeat timestamp for this agent's window."""
    registry = _read_window_registry()
    if agent_id in registry:
        registry[agent_id]["last_heartbeat"] = time.time()
        _write_window_registry(registry)

def _unregister_window(agent_id: str):
    """Remove this agent's window from the registry."""
    registry = _read_window_registry()
    if agent_id in registry:
        del registry[agent_id]
        _write_window_registry(registry)

def cleanup_orphaned_windows(driver: webdriver.Chrome, *, close_on_stale: bool = False):
    """
    Close windows owned by dead processes. Optionally close very stale windows if explicitly enabled.

    - Default behavior: only close when the owning PID no longer exists.
    - Stale heartbeats are logged but not closed by default to avoid killing idle sessions.
    """
    # If you have a registry/file lock, acquire it here
    # with _registry_lock():
    registry = _read_window_registry()
    now = time.time()

    to_remove: list[str] = []
    changed = False

    # Optional: detect already-missing targets to avoid noisy close attempts
    try:
        targets_resp = driver.execute_cdp_cmd("Target.getTargets", {})
        known_targets = {t.get("targetId") for t in targets_resp.get("targetInfos", [])}
    except Exception:
        known_targets = None  # fall back to best-effort without pre-check

    for agent_id, info in list(registry.items()):
        pid = info.get("pid")
        last_hb = info.get("last_heartbeat")
        target_id = info.get("target_id")

        # Robustness: skip weird records
        if target_id is None:
            logger.info(f"Removing registry entry with no target_id: agent={agent_id}, pid={pid}")
            to_remove.append(agent_id)
            changed = True
            continue

        # Compute states safely
        try:
            is_dead = bool(pid) and not psutil.pid_exists(int(pid))
        except Exception:
            # If pid cannot be parsed, treat as unknown (do not close)
            is_dead = False

        is_stale = False
        if isinstance(last_hb, (int, float)):
            try:
                is_stale = (now - float(last_hb)) > WINDOW_REGISTRY_STALE_THRESHOLD
            except Exception:
                is_stale = False

        # If target is already gone, just drop the registry entry
        if known_targets is not None and target_id not in known_targets:
            logger.info(f"Target already gone; pruning registry entry: agent={agent_id}, target={target_id}")
            to_remove.append(agent_id)
            changed = True
            continue

        # Decide whether to close
        should_close = is_dead or (close_on_stale and is_stale)
        if not should_close:
            if is_stale:
                logger.debug(f"Stale heartbeat but not closing (agent={agent_id}, pid={pid})")
            continue

        # Try to close the target
        try:
            res = driver.execute_cdp_cmd("Target.closeTarget", {"targetId": target_id})
            success = (res.get("success", True) if isinstance(res, dict) else True)
            logger.info(
                f"Closed orphaned window: agent={agent_id}, target={target_id}, "
                f"dead={is_dead}, stale={is_stale}, success={success}"
            )
        except Exception as e:
            # Even if we fail to close a window of a dead process, remove the entry to avoid leaks
            logger.debug(f"Could not close target {target_id} for agent {agent_id}: {e}")

        to_remove.append(agent_id)
        changed = True

    # Clean up registry
    if to_remove:
        for agent_id in to_remove:
            registry.pop(agent_id, None)
        _write_window_registry(registry)
        logger.info(f"Cleaned up {len(to_remove)} window registry entry(ies)")
    elif changed:
        # In case we changed something else
        _write_window_registry(registry)
#endregion

#region Driver & window
def _resolve_chrome_executable(cfg: dict) -> str:
    if cfg.get("chrome_path"):
            return cfg["chrome_path"]
    

    # Try config keys first
    candidates = [
        cfg.get("chrome_executable"),
        cfg.get("chrome_binary"),
        cfg.get("chrome_executable_path"),
        os.getenv("CHROME_EXECUTABLE_PATH"),
    ]
    # Common macOS fallbacks
    defaults = [
        "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    ]
    for p in candidates + defaults:
        if p and os.path.exists(p):
            return p
    raise FileNotFoundError(
        "Chrome executable not found. Set CHROME_EXECUTABLE_PATH to the full binary path, "
        "e.g. /Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
    )

def _read_devtools_active_port(user_data_dir: str) -> int | None:
    p = Path(user_data_dir) / "DevToolsActivePort"
    if not p.exists():
        return None
    try:
        first = p.read_text().splitlines()[0].strip()
        return int(first)
    except Exception:
        return None

def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def _launch_chrome_with_debug(cfg: dict, port: int) -> None:
    exe = _resolve_chrome_executable(cfg)
    udir = cfg["user_data_dir"]
    prof = cfg.get("profile_name")

    # Check if headless mode is enabled
    headless = os.getenv("MCP_HEADLESS", "0").strip()
    is_headless = headless in ("1", "true", "True", "yes", "Yes")

    cmd = [
        exe,
        f"--user-data-dir={udir}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",  # Fix 1: Force new window even if Chrome is running
        "--disable-features=ProcessPerSite",  # Fix 3: Better process isolation
        "--disable-gpu",  # Stability: Disable GPU hardware acceleration
        "--disable-dev-shm-usage",  # Stability: Overcome limited resource problems
        "--disable-software-rasterizer",  # Stability: Disable software rasterizer
        "--disable-hang-monitor",  # Keep Chrome alive longer
        "about:blank",
    ]
    if prof:
        cmd.append(f"--profile-directory={prof}")
    if is_headless:
        cmd.append("--headless=new")

    # Fix 2: Create error log file (opened but not passed to Chrome to avoid handle issues)
    log_dir = Path(tempfile.gettempdir()) / "mcp_browser_logs"
    log_dir.mkdir(exist_ok=True)
    error_log = log_dir / f"chrome_debug_{port}.log"

    # Start detached; Chrome writes DevToolsActivePort when ready.
    # On Windows, use CREATE_NO_WINDOW to avoid console but allow debug port initialization
    if platform.system() == "Windows":
        proc = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL
        )
    else:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    # Fix 4: Verify Chrome actually started (wait for process to stabilize)
    time.sleep(2.0)  # Give Chrome time to fully initialize
    try:
        # Check if process is still alive
        if proc.poll() is not None:
            # Process exited immediately, read error log
            try:
                with open(error_log, "r") as log:
                    error_content = log.read()
                    logger.error(f"Chrome failed to start. Exit code: {proc.returncode}. Log: {error_content}")
            except Exception:
                pass
    except Exception:
        pass

def _ensure_debugger_ready(cfg: dict, max_wait_secs: float | None = None) -> None:
    """
    Ensure a debuggable Chrome is running for the configured user-data-dir,
    set DEBUGGER_HOST/DEBUGGER_PORT accordingly.
    """
    global DEBUGGER_HOST, DEBUGGER_PORT
    try:
        host, port, _ = start_or_attach_chrome_from_env(cfg)
        if not (ALLOW_ATTACH_ANY or _verify_port_matches_profile(host, port, cfg["user_data_dir"])):
            raise RuntimeError("DevTools port does not belong to the configured profile")
        DEBUGGER_HOST, DEBUGGER_PORT = host, port
        return
    except Exception:
        DEBUGGER_HOST = None
        DEBUGGER_PORT = None

    # Allow override by env; default to 10 seconds (reduced for faster failures)
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
        DEBUGGER_HOST, DEBUGGER_PORT = "127.0.0.1", file_port
        return

    # 2) If allowed, attach to a known open port (useful in shared test envs)
    if ALLOW_ATTACH_ANY:
        for p in filter(None, [env_port, 9223]):
            if _is_port_open("127.0.0.1", p):
                DEBUGGER_HOST, DEBUGGER_PORT = "127.0.0.1", p
                return

    # 3) Launch our own debuggable Chrome on env_port or default 9225
    port = env_port or 9225
    _launch_chrome_with_debug(cfg, port)

    # Wait until Chrome writes the file OR the TCP port answers
    t0 = time.time()
    while time.time() - t0 < max_wait_secs:
        p = _read_devtools_active_port(udir)
        if (p and _is_port_open("127.0.0.1", p)) or _is_port_open("127.0.0.1", port):
            DEBUGGER_HOST, DEBUGGER_PORT = "127.0.0.1", p or port
            return
        time.sleep(0.1)

    DEBUGGER_HOST = DEBUGGER_PORT = None

def _ensure_driver() -> None:
    """Attach Selenium to the debuggable Chrome instance (headed by default)."""
    global DRIVER
    if DRIVER is not None:
        return

    cfg = get_env_config()
    _ensure_debugger_ready(cfg)  # allow full wait (e.g., 30s via env)
    if not (DEBUGGER_HOST and DEBUGGER_PORT):
        return  # caller will return driver_not_initialized

    # Use the shared factory so Chromedriver logs and options are consistent
    DRIVER = create_webdriver(DEBUGGER_HOST, DEBUGGER_PORT, cfg)

def ensure_process_tag() -> str:
    global MY_TAG
    if MY_TAG is None:
        MY_TAG = make_process_tag()
    return MY_TAG

def _validate_window_context(driver: webdriver.Chrome, expected_target_id: str) -> bool:
    """
    Validate that the current window context matches the expected target.
    Returns True if validation passes, False otherwise.
    Handles NoSuchWindowException gracefully.
    """
    if not expected_target_id:
        return False
    
    try:
        # Check if current window handle exists and matches expected target
        current_handle = driver.current_window_handle
        if current_handle and current_handle.endswith(expected_target_id):
            return True
            
        # Double-check by getting target info via CDP
        try:
            info = driver.execute_cdp_cmd("Target.getTargetInfo", {}) or {}
            current_target = (info.get("targetInfo") or {}).get("targetId") or info.get("targetId")
            return current_target == expected_target_id
        except Exception:
            pass
            
        return False
    except Exception:
        # NoSuchWindowException or other window-related exceptions
        return False

def _ensure_singleton_window(driver: webdriver.Chrome):
    global TARGET_ID, WINDOW_ID

    # 0) If we already have a target, validate context and attempt recovery
    if TARGET_ID:
        # First validate we're in the correct window context
        if _validate_window_context(driver, TARGET_ID):
            return  # Already in correct window

        # Context validation failed - attempt recovery
        h = _handle_for_target(driver, TARGET_ID)
        if h:
            try:
                driver.switch_to.window(h)
                # Verify recovery succeeded
                if _validate_window_context(driver, TARGET_ID):
                    return
            except Exception:
                pass  # Recovery failed, will recreate window below

        # Window handle not found or recovery failed - clear target and recreate
        TARGET_ID = None
        WINDOW_ID = None

    # 1) First-time in this process or recovery failed: create a new real OS window for this agent
    if not TARGET_ID:
        # Cleanup orphaned windows from dead/stale processes before creating new window
        try:
            cleanup_orphaned_windows(driver)
        except Exception as e:
            logger.debug(f"Window cleanup failed (non-critical): {e}")
        try:
            win = driver.execute_cdp_cmd("Browser.createWindow", {"state": "normal"})
            if not isinstance(win, dict):
                raise RuntimeError(f"Browser.createWindow returned {win!r}")
            WINDOW_ID = win.get("windowId")
            TARGET_ID = win.get("targetId")

            if not TARGET_ID:
                # Fallback: ensure there is a page target tied to a new window
                t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
                if not isinstance(t, dict) or "targetId" not in t:
                    raise RuntimeError(f"Target.createTarget returned {t!r}")
                TARGET_ID = t["targetId"]
                if not WINDOW_ID:
                    try:
                        w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": TARGET_ID}) or {}
                        WINDOW_ID = w.get("windowId")
                    except Exception:
                        WINDOW_ID = None
        except Exception:
            # Last resort: create via Target API
            t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
            if not isinstance(t, dict) or "targetId" not in t:
                raise RuntimeError(f"Target.createTarget returned {t!r}")
            TARGET_ID = t["targetId"]
            try:
                w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": TARGET_ID}) or {}
                WINDOW_ID = w.get("windowId")
            except Exception:
                WINDOW_ID = None

    # 2) Map targetId -> Selenium handle (with brief retry)
    h = _handle_for_target(driver, TARGET_ID)
    if not h:
        for _ in range(20):  # ~1s
            time.sleep(0.05)
            h = _handle_for_target(driver, TARGET_ID)
            if h:
                break
    
    if h:
        driver.switch_to.window(h)
        # Final validation to ensure we're in the correct window
        if not _validate_window_context(driver, TARGET_ID):
            raise RuntimeError(f"Failed to establish correct window context for target {TARGET_ID}")

        # Register this window in the registry
        try:
            owner = ensure_process_tag()
            _register_window(owner, TARGET_ID, WINDOW_ID)
        except Exception as e:
            logger.debug(f"Window registration failed (non-critical): {e}")
    else:
        raise RuntimeError(f"Failed to find window handle for target {TARGET_ID}")

def _ensure_driver_and_window() -> None:
    global DRIVER, TARGET_ID
    _ensure_driver()
    if DRIVER is None:
        return
    _ensure_singleton_window(DRIVER)


def _close_extra_blank_windows_safe(driver, exclude_handles=None) -> int:
    exclude = set(exclude_handles or ())
    # Only operate within our own OS window
    own_window_id = WINDOW_ID
    if own_window_id is None:
        return 0

    try:
        keep = driver.current_window_handle
    except Exception:
        keep = None

    closed = 0
    for h in list(getattr(driver, "window_handles", [])):
        if h in exclude or (keep and h == keep):
            continue
        try:
            driver.switch_to.window(h)
            # Map this handle -> targetId -> windowId
            info = driver.execute_cdp_cmd("Target.getTargetInfo", {}) or {}
            tid = (info.get("targetInfo") or {}).get("targetId") or info.get("targetId")
            if not tid:
                continue
            w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": tid}) or {}
            if w.get("windowId") != own_window_id:
                # Belongs to another agent's OS window; do not touch
                continue

            url = (driver.current_url or "").lower()
            title = (driver.title or "").strip()
            if url in ("about:blank", "chrome://newtab/") or (not url and not title):
                driver.close()
                closed += 1
        except Exception:
            continue

    # Restore our original window if it still exists
    if keep and keep in getattr(driver, "window_handles", []):
        try:
            driver.switch_to.window(keep)
        except Exception:
            pass
    return closed

def close_singleton_window() -> bool:
    """
    Close the singleton window (by targetId) without quitting Chrome.
    Resets TARGET_ID/WINDOW_ID so a subsequent start will create a new window.
    Also unregisters the window from the registry.
    """
    global DRIVER, TARGET_ID, WINDOW_ID
    if DRIVER is None or not TARGET_ID:
        return False

    closed = False
    try:
        DRIVER.execute_cdp_cmd("Target.closeTarget", {"targetId": TARGET_ID})
        closed = True
    except Exception:
        # Fallback: find Selenium handle for this target and close it
        try:
            h = _handle_for_target(DRIVER, TARGET_ID)
            if h:
                DRIVER.switch_to.window(h)
                DRIVER.close()
                closed = True
        except Exception:
            pass

    # Unregister from window registry
    if closed:
        try:
            owner = ensure_process_tag()
            _unregister_window(owner)
        except Exception as e:
            logger.debug(f"Window unregistration failed (non-critical): {e}")

    TARGET_ID = None
    WINDOW_ID = None
    return closed

def _handle_for_target(driver, target_id: Optional[str]) -> Optional[str]:
    if not target_id:
        return None

    # Fast path: Selenium handle suffix matches CDP targetId
    for h in driver.window_handles:
        try:
            if h.endswith(target_id):
                return h
        except Exception:
            pass

    # Nudge Chrome to foreground that target, then retry a bit
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

    # Robust path: probe handles via CDP, then list all targets
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

        # Last resort: enumerate all targets and try another activation
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

#endregion

#region Wait and snapshot
def _wait_document_ready(timeout: float = 10.0):
    try:
        WebDriverWait(DRIVER, timeout).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )
    except Exception:
        # Not fatal
        pass


def _make_page_snapshot(
    max_snapshot_chars: Optional[int] = None,   # ignored (legacy)
    aggressive_cleaning: bool = False,          # ignored (legacy)
    offset_chars: int = 0,                      # ignored (legacy)
) -> dict:
    """
    Capture the raw page snapshot (no cleaning, no truncation).
    Returns a dict: {"url": str|None, "title": str|None, "html": str}
    """
    url = None
    title = None
    html = ""
    try:
        if DRIVER is not None:
            try:
                DRIVER.switch_to.default_content()
            except Exception:
                pass
            try:
                url = DRIVER.current_url
            except Exception:
                url = None
            try:
                title = DRIVER.title
            except Exception:
                title = None

            # Ensure DOM is ready, then apply configurable settle
            try:
                _wait_document_ready(timeout=5.0)
            except Exception:
                pass
            try:
                settle_ms = int(os.getenv("SNAPSHOT_SETTLE_MS", "200") or "0")
                if settle_ms > 0:
                    time.sleep(settle_ms / 1000.0)
            except Exception:
                pass

            # Prefer outerHTML; fall back to page_source
            try:
                html = DRIVER.execute_script("return document.documentElement.outerHTML") or ""
                if not html:
                    html = DRIVER.page_source or ""
            except Exception:
                try:
                    html = DRIVER.page_source or ""
                except Exception:
                    html = ""
    except Exception:
        pass
    return {"url": url, "title": title, "html": html}
#endregion

#region Tool helpers (clickable wait using a lambda on the element)
def _same_dir(a: str, b: str) -> bool:
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except Exception:
        return a == b

def _devtools_user_data_dir(host: str, port: int, timeout: float = 1.5) -> str | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/json/version", timeout=timeout) as resp:
            meta = json.load(resp)
            return meta.get("userDataDir")
    except Exception:
        return None

def _verify_port_matches_profile(host: str, port: int, expected_dir: str) -> bool:
    actual = _devtools_user_data_dir(host, port)
    return _same_dir(actual, expected_dir)

def _wait_clickable_element(el, timeout: float = 10.0):
    WebDriverWait(DRIVER, timeout).until(lambda d: el.is_displayed() and el.is_enabled())
    return el
#endregion

#region Paths for coordination artifacts
def rendezvous_path(config: dict) -> str:
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_rendezvous_{profile_key(config)}.json")

def start_lock_dir(config: dict) -> str:
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_start_lock_{profile_key(config)}")

def chromedriver_log_path(config: dict) -> str:
    return os.path.join(tempfile.gettempdir(), f"chromedriver_shared_{profile_key(config)}_{os.getpid()}.log")
#endregion

#region DevTools endpoint and Chrome discovery
def is_debugger_listening(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/json/version", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def chrome_running_with_userdata(user_data_dir: str) -> bool:
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if not p.info["name"] or "chrome" not in p.info["name"].lower():
                continue
            cmd = p.info.get("cmdline") or []
            if any((arg or "").startswith("--user-data-dir=") and (arg.split("=", 1)[1].strip('"') == user_data_dir)
                   for arg in cmd):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def find_chrome_process_by_port(port: int) -> Optional[psutil.Process]:
    target = f"--remote-debugging-port={port}"
    for p in psutil.process_iter(["name", "cmdline", "exe"]):
        try:
            if not p.info["name"]:
                continue
            if "chrome" not in p.info["name"].lower():
                continue
            cmd = p.info.get("cmdline") or []
            if any(target in (arg or "") for arg in cmd):
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def is_default_user_data_dir(user_data_dir: str) -> bool:
    """Return True if user_data_dir is one of Chrome's default roots (where DevTools is refused)."""
    p = Path(user_data_dir).expanduser().resolve()
    system = platform.system()
    defaults = []
    if system == "Darwin":
        defaults = [
            Path.home() / "Library/Application Support/Google/Chrome",
            Path.home() / "Library/Application Support/Google/Chrome Beta",
            Path.home() / "Library/Application Support/Google/Chrome Canary",
        ]
    elif system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            base = Path(local) / "Google"
            defaults = [
                base / "Chrome" / "User Data",
                base / "Chrome Beta" / "User Data",
                base / "Chrome SxS" / "User Data",  # Canary
            ]
    else:  # Linux
        home = Path.home()
        defaults = [
            home / ".config/google-chrome",
            home / ".config/google-chrome-beta",
            home / ".config/google-chrome-unstable",  # Canary
            home / ".config/chromium",
        ]
    return any(p == d for d in defaults)
#endregion

#region Rendezvous API
def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None

def read_rendezvous(config: dict) -> Tuple[Optional[int], Optional[int]]:
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
    try:
        os.remove(rendezvous_path(config))
    except Exception:
        pass
#endregion

#region Startup lock (single starter)
def acquire_start_lock(config: dict, timeout_sec: float = START_LOCK_WAIT_SEC) -> bool:
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
    try:
        shutil.rmtree(start_lock_dir(config), ignore_errors=True)
    except Exception:
        pass
#endregion

#region Attach or launch Chrome
def _chrome_binary_for_platform(config: dict) -> str:
    if config.get("chrome_path"):
        return config["chrome_path"]
    system = platform.system()
    candidates = []
    if system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "chrome",
        ]
    elif system == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        candidates = ["google-chrome", "chrome", "chromium", "chromium-browser"]
    for c in candidates:
        if os.path.isfile(c) or shutil.which(c):
            return c
    return "chrome"

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

def start_or_attach_chrome_from_env(config: dict) -> Tuple[str, int, Optional[psutil.Process]]:
    user_data_dir = config["user_data_dir"]
    profile_name = config["profile_name"]
    fixed_port = config.get("fixed_port")
    host = "127.0.0.1"

    # Ensure directory exists
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    # Refuse default channel dirs unless explicitly allowed
    if is_default_user_data_dir(user_data_dir) and os.getenv("MCP_ALLOW_DEFAULT_USER_DATA_DIR", "0") != "1":
        raise RuntimeError(
            "Remote debugging is disabled on Chrome's default user-data directories.\n"
            f"Set *_PROFILE_USER_DATA_DIR to a separate path (e.g., '{Path(user_data_dir).parent}/Chrome Beta MCP'), "
            "optionally seed it from your existing profile, then retry.\n"
            "To override (not recommended), set MCP_ALLOW_DEFAULT_USER_DATA_DIR=1."
        )

# If a DevTools port is already active for this profile, attach to it.
    if not fixed_port:
        existing_port = devtools_active_port_from_file(user_data_dir)
        if existing_port and is_debugger_listening(host, existing_port):
            chrome_proc = find_chrome_process_by_port(existing_port)
            write_rendezvous(config, existing_port, chrome_proc.pid if chrome_proc else os.getpid())
            return host, existing_port, None

    # Fixed port path
    if fixed_port:
        # If the profile is already debuggable on another port, prefer attaching to that.
        existing_port = devtools_active_port_from_file(user_data_dir)
        if existing_port and existing_port != fixed_port and is_debugger_listening(host, existing_port):
            chrome_proc = find_chrome_process_by_port(existing_port)
            write_rendezvous(config, existing_port, chrome_proc.pid if chrome_proc else os.getpid())
            return host, existing_port, None

        port = fixed_port
        if is_debugger_listening(host, port):
            chrome_proc = find_chrome_process_by_port(port)
            write_rendezvous(config, port, chrome_proc.pid if chrome_proc else os.getpid())
            return host, port, None

        # Start Chrome on fixed port
        binary = _chrome_binary_for_platform(config)

        # Check if headless mode is enabled
        headless = os.getenv("MCP_HEADLESS", "0").strip()
        is_headless = headless in ("1", "true", "True", "yes", "Yes")

        cmd = [
            binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile_name}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",  # Fix 1: Force new window even if Chrome is running
            "--disable-features=ProcessPerSite",  # Fix 3: Better process isolation
            "--disable-gpu",  # Stability: Disable GPU hardware acceleration
            "--disable-dev-shm-usage",  # Stability: Overcome limited resource problems
            "--disable-software-rasterizer",  # Stability: Disable software rasterizer
            "about:blank",
        ]
        if is_headless:
            cmd.append("--headless=new")

        # Fix 2: Create error log file
        log_dir = Path(tempfile.gettempdir()) / "mcp_browser_logs"
        log_dir.mkdir(exist_ok=True)
        error_log = log_dir / f"chrome_debug_{port}.log"

        # On Windows, use CREATE_NO_WINDOW to avoid console but allow debug port initialization
        if platform.system() == "Windows":
            proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

        # Fix 4: Verify Chrome actually started
        time.sleep(2.0)  # Give Chrome time to fully initialize
        try:
            if proc.poll() is not None:
                try:
                    with open(error_log, "r") as log:
                        error_content = log.read()
                        logger.error(f"Chrome failed to start. Exit code: {proc.returncode}. Log: {error_content}")
                except Exception:
                    pass
        except Exception:
            pass

        # Wait for DevTools endpoint
        for _ in range(100):
            if is_debugger_listening(host, port):
                chrome_proc = find_chrome_process_by_port(port)
                write_rendezvous(config, port, chrome_proc.pid if chrome_proc else proc.pid)
                return host, port, proc
            time.sleep(0.1)

        if chrome_running_with_userdata(user_data_dir):
            raise RuntimeError(
                "DevTools endpoint did not appear. Likely causes:\n"
                " - Chrome refused remote debugging because the user-data-dir is a default channel directory.\n"
                " - Another Chrome instance (started without --remote-debugging-port) is holding this user-data-dir.\n"
                "Actions:\n"
                f" - Use a separate automation dir (e.g., '{Path(user_data_dir).parent}/Chrome Beta MCP'), "
                "optionally seeded from your profile, and try again.\n"
                " - Or ensure all Chrome/Chrome Beta processes are fully quit before starting."
            )
        raise RuntimeError(f"Failed to start Chrome with remote debugging on {port}.")

    # Rendezvous path
    port, pid = read_rendezvous(config)
    if port:
        return host, port, None

    got_lock = acquire_start_lock(config, timeout_sec=START_LOCK_WAIT_SEC)
    try:
        if not got_lock:
                    # Spin a little waiting for rendezvous by the winner
                    for _ in range(50):
                        port, pid = read_rendezvous(config)
                        if port:
                            return host, port, None
                        # Also attach via DevToolsActivePort if it appears sooner
                        p2 = devtools_active_port_from_file(user_data_dir)
                        if p2 and is_debugger_listening(host, p2):
                            chrome_proc = find_chrome_process_by_port(p2)
                            write_rendezvous(config, p2, chrome_proc.pid if chrome_proc else os.getpid())
                            return host, p2, None
                        time.sleep(0.1)
                    raise RuntimeError("Timeout acquiring start lock for Chrome rendezvous.")

        # Inside lock: recheck rendezvous
        port, pid = read_rendezvous(config)
        if port:
            return host, port, None

        # Choose a free port and start Chrome
        port = get_free_port()
        binary = _chrome_binary_for_platform(config)

        # Check if headless mode is enabled
        headless = os.getenv("MCP_HEADLESS", "0").strip()
        is_headless = headless in ("1", "true", "True", "yes", "Yes")

        cmd = [
            binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile_name}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",  # Fix 1: Force new window even if Chrome is running
            "--disable-features=ProcessPerSite",  # Fix 3: Better process isolation
            "--disable-gpu",  # Stability: Disable GPU hardware acceleration
            "--disable-dev-shm-usage",  # Stability: Overcome limited resource problems
            "--disable-software-rasterizer",  # Stability: Disable software rasterizer
            "about:blank",
        ]
        if is_headless:
            cmd.append("--headless=new")

        # Fix 2: Create error log file
        log_dir = Path(tempfile.gettempdir()) / "mcp_browser_logs"
        log_dir.mkdir(exist_ok=True)
        error_log = log_dir / f"chrome_debug_{port}.log"

        # On Windows, use CREATE_NO_WINDOW to avoid console but allow debug port initialization
        if platform.system() == "Windows":
            proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        else:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

        # Fix 4: Verify Chrome actually started
        time.sleep(2.0)  # Give Chrome time to fully initialize
        try:
            if proc.poll() is not None:
                try:
                    with open(error_log, "r") as log:
                        error_content = log.read()
                        logger.error(f"Chrome failed to start. Exit code: {proc.returncode}. Log: {error_content}")
                except Exception:
                    pass
        except Exception:
            pass

        # Wait for DevTools endpoint
        for _ in range(100):
            if is_debugger_listening(host, port):
                chrome_proc = find_chrome_process_by_port(port)
                if chrome_proc:
                    write_rendezvous(config, port, chrome_proc.pid)
                else:
                    write_rendezvous(config, port, proc.pid)
                return host, port, proc
            time.sleep(0.1)

        # If endpoint never appeared
        if chrome_running_with_userdata(user_data_dir):
            raise RuntimeError(
                "Chrome is already running with this user-data-dir but without DevTools remote debugging. "
                "Close Chrome, or set CHROME_REMOTE_DEBUG_PORT to a known port and retry."
            )
        else:
            raise RuntimeError("Failed to start Chrome with remote debugging; endpoint never came up.")
    finally:
        if got_lock:
            release_start_lock(config)
#endregion

#region Selenium WebDriver attached to shared Chrome
def create_webdriver(debugger_host: str, debugger_port: int, config: dict) -> webdriver.Chrome:
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service as ChromeService

    options = Options()
    chrome_path = config.get("chrome_path")
    if chrome_path:
        options.binary_location = chrome_path
    options.add_experimental_option("debuggerAddress", f"{debugger_host}:{debugger_port}")

    # Handle differing Selenium versions that accept log_output vs. log_path
    log_file = chromedriver_log_path(config)
    try:
        service = ChromeService(log_output=log_file)  # newer Selenium
    except TypeError:
        service = ChromeService(log_path=log_file)    # older Selenium

    driver = webdriver.Chrome(service=service, options=options)
    return driver
#endregion

#region Per-process window ownership
def make_process_tag() -> str:
    import uuid
    return f"agent:{uuid.uuid4().hex}"

def _cleanup_own_blank_tabs(driver):
    handle = getattr(driver, "current_window_handle", None)
    try:
        _close_extra_blank_windows_safe(
            driver,
            exclude_handles={handle} if handle else None,
        )
    except Exception:
        pass
#endregion

#region Resilience: retries and DOM utils
def retry_op(fn: Callable, retries: int = 2, base_delay: float = 0.15):
    import random
    for attempt in range(retries + 1):
        try:
            return fn()
        except (NoSuchWindowException, StaleElementReferenceException, WebDriverException):
            if attempt == retries:
                raise
            time.sleep(base_delay * (1.0 + random.random()))

def get_by_selector(selector_type: str):
    return {
        'css': By.CSS_SELECTOR,
        'xpath': By.XPATH,
        'id': By.ID,
        'name': By.NAME,
        'tag': By.TAG_NAME,
        'class': By.CLASS_NAME,
        'link_text': By.LINK_TEXT,
        'partial_link_text': By.PARTIAL_LINK_TEXT
    }.get(selector_type.lower())

def find_element(
    driver: webdriver.Chrome,
    selector: str,
    selector_type: str = "css",
    timeout: int = 10,
    visible_only: bool = False,
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
    shadow_root_selector: Optional[str] = None,
    shadow_root_selector_type: str = "css",
    stay_in_context: bool = False,  # <-- added
):
    """
    Locate an element with optional iframe and shadow DOM support.

    - If stay_in_context is True and an iframe was entered, we do NOT switch back
      to default_content. This is needed for actions (click/type) inside iframes.
    - If stay_in_context is False (default), we restore to default_content() so
      callers aren't left in an iframe.
    """
    original_driver = driver
    switched_iframe = False
    try:
        if iframe_selector:
            by_iframe = get_by_selector(iframe_selector_type)
            if not by_iframe:
                raise ValueError(f"Unsupported iframe selector type: {iframe_selector_type}")
            iframe = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by_iframe, iframe_selector))
            )
            driver.switch_to.frame(iframe)
            switched_iframe = True

        search_context = driver
        if shadow_root_selector:
            by_shadow_host = get_by_selector(shadow_root_selector_type)
            if not by_shadow_host:
                raise ValueError(f"Unsupported shadow root selector type: {shadow_root_selector_type}")
            shadow_host = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by_shadow_host, shadow_root_selector))
            )
            shadow_root = shadow_host.shadow_root
            search_context = shadow_root

        by_selector = get_by_selector(selector_type)
        if not by_selector:
            raise ValueError(f"Unsupported selector type: {selector_type}")

        wait = WebDriverWait(search_context, timeout)
        if visible_only:
            element = wait.until(EC.visibility_of_element_located((by_selector, selector)))
        else:
            element = wait.until(EC.presence_of_element_located((by_selector, selector)))

        return element

    except TimeoutException:
        if switched_iframe and not stay_in_context:
            try:
                original_driver.switch_to.default_content()
            except Exception:
                pass
        raise
    except Exception:
        if switched_iframe and not stay_in_context:
            try:
                original_driver.switch_to.default_content()
            except Exception:
                pass
        raise
    finally:
        if switched_iframe and not stay_in_context:
            try:
                original_driver.switch_to.default_content()
            except Exception:
                pass

def remove_unwanted_tags(html_content: str, aggressive: bool = False) -> str:
    """
    Remove unwanted tags from HTML.

    Args:
        html_content: Raw HTML string
        aggressive: If True, removes additional tags like svg, iframe, comments, headers, footers, navigation

    Returns:
        Cleaned HTML string with whitespace collapsed
    """
    from bs4 import Comment

    soup = BeautifulSoup(html_content, 'html.parser')

    # Always remove these
    basic_removals = ['script', 'style', 'meta', 'link', 'noscript']

    # Aggressive mode removes more
    if aggressive:
        basic_removals.extend([
            'svg', 'iframe', 'canvas', 'form'
        ])

    for tag in soup.find_all(basic_removals):
        tag.extract()

    # Remove HTML comments in aggressive mode
    if aggressive:
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove hidden inputs
        for hidden_input in soup.find_all('input', {'type': 'hidden'}):
            hidden_input.extract()

        # Remove headers, footers, and navigation (huge space savers for e-commerce sites)
        for tag in soup.find_all(['header', 'footer', 'nav']):
            tag.extract()

        # Remove common navigation/menu class patterns (but be more selective)
        for tag in soup.find_all(class_=lambda c: c and any(x in str(c).lower() for x in ['-header', '-footer', '-navigation', 'nav-main', '-menu', '-flyout', '-dropdown', 'breadcrumb'])):
            tag.extract()

        # Remove all attributes except critical ones for product data
        critical_attrs = {'href', 'src', 'alt', 'title', 'class', 'id', 'type', 'name', 'value'}
        for tag in soup.find_all(True):
            # Remove all non-critical attributes
            attrs_to_remove = [attr for attr in tag.attrs if attr not in critical_attrs]
            for attr in attrs_to_remove:
                del tag[attr]

            # Also remove data-* attributes (often just for JS functionality)
            data_attrs = [attr for attr in tag.attrs if attr.startswith('data-')]
            for attr in data_attrs:
                del tag[attr]

        # Remove empty tags after cleaning, but preserve structural tags like body, html, divs with children
        # Only remove leaf nodes that are empty
        for tag in soup.find_all():
            if tag.name not in ['html', 'head', 'body'] and not tag.get_text(strip=True) and not tag.find_all(['img', 'input', 'br', 'hr', 'a']):
                tag.extract()

    # Collapse whitespace
    return ' '.join(str(soup).split())

def get_cleaned_html(driver: webdriver.Chrome, aggressive: bool = False) -> str:
    """
    Get cleaned HTML from the current page.

    Args:
        driver: Selenium WebDriver instance
        aggressive: If True, applies aggressive HTML cleaning

    Returns:
        Cleaned HTML string
    """
    html_content = driver.page_source
    return remove_unwanted_tags(html_content, aggressive=aggressive)
#endregion

#region Diagnostics
def get_chrome_version() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as key:
                    version, _ = winreg.QueryValueEx(key, "version")
                    return f"Google Chrome {version}"
            except Exception:
                pass
            # Fallbacks
            for candidate in [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "chrome",
            ]:
                try:
                    path = candidate if os.path.isfile(candidate) else shutil.which(candidate)
                    if path:
                        out = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT).decode().strip()
                        return out
                except Exception:
                    continue
            return "Error fetching Chrome version: chrome binary not found"
        elif system == "Darwin":
            path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            out = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT).decode().strip()
            return out
        else:
            for candidate in ["google-chrome", "chrome", "chromium", "chromium-browser"]:
                try:
                    path = shutil.which(candidate)
                    if path:
                        out = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT).decode().strip()
                        return out
                except Exception:
                    continue
            return "Error fetching Chrome version: chrome binary not found"
    except Exception as e:
        return f"Error fetching Chrome version: {e}"

def get_chromedriver_capability_version(driver: Optional[webdriver.Chrome] = None) -> Optional[str]:
    """
    Best effort Chromedriver version string.
    - If a driver is provided, prefer driver.capabilities['chromedriverVersion'].
    - Else, fall back to `chromedriver --version` if available in PATH.
    """
    try:
        if driver:
            v = driver.capabilities.get("chromedriverVersion")
            if isinstance(v, str) and v:
                # Typically like "114.0.5735.90 (some hash)"
                return v.split(" ")[0]
        path = shutil.which("chromedriver")
        if path:
            out = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT).decode().strip()
            return out
    except Exception:
        pass
    return None

def collect_diagnostics(driver: Optional[webdriver.Chrome], exc: Optional[Exception], config: dict) -> str:
    parts = [
        f"OS                : {platform.system()} {platform.release()}",
        f"Python            : {sys.version.split()[0]}",
        f"Selenium          : {getattr(selenium, '__version__', '?')}",
        f"User-data dir     : {config.get('user_data_dir')}",
        f"Profile name      : {config.get('profile_name')}",
        f"Chrome binary     : {config.get('chrome_path') or _chrome_binary_for_platform(config)}",
    ]
    if driver:
        try:
            ver = driver.execute_cdp_cmd("Browser.getVersion", {}) or {}
            parts.append(f"Browser version   : {ver.get('product', '<unknown>')}")
        except Exception:
            parts.append("Browser version   : <unknown>")

        cap = getattr(driver, "capabilities", None) or {}
        drv_ver = cap.get("chromedriverVersion") or cap.get("browserVersion") or "<unknown>"
        parts.append(f"Driver version    : {drv_ver}")
        opts = cap.get("goog:chromeOptions") or {}
        args = opts.get("args") or []
        parts.append(f"Chrome args       : {' '.join(args)}")
    if exc:
        parts += [
            "---- ERROR ----",
            f"Error type        : {type(exc).__name__}",
            f"Error message     : {exc}",
        ]
    return "\n".join(parts)
#endregion

#region Tool Implementation
async def start_browser():
    owner = ensure_process_tag()
    try:
        _ensure_driver_and_window()

        if DRIVER is None:
            diag = collect_diagnostics(None, None, get_env_config())
            if isinstance(diag, str):
                    diag = {"summary": diag}
            return json.dumps({
                "ok": False,
                "error": "driver_not_initialized",
                "driver_initialized": False,
                "debugger": (
                    f"{DEBUGGER_HOST}:{DEBUGGER_PORT}"
                    if (DEBUGGER_HOST and DEBUGGER_PORT) else None
                ),
                "diagnostics": diag,
                "message": "Failed to attach/launch a debuggable Chrome session."
            })
        
        handle = getattr(DRIVER, "current_window_handle", None)
        try:
            _close_extra_blank_windows_safe(DRIVER, exclude_handles={handle} if handle else None)
        except Exception:
            pass

        # Wait until the page is ready. Get a snapshot.
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

        msg = ( # Human-friendly message
            f"Browser session created successfully. "
            f"Session ID: {owner}. "
            f"Current URL: {snapshot.get('url') or 'about:blank'}"
        )

        payload = {
            "ok": True,
            "session_id": owner,
            "debugger": f"{DEBUGGER_HOST}:{DEBUGGER_PORT}" if (DEBUGGER_HOST and DEBUGGER_PORT) else None,
            "lock_ttl_seconds": ACTION_LOCK_TTL_SECS,
            "snapshot": snapshot,
            "message": msg,
        }
    
        return json.dumps(payload)
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot() or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    
# helpers/__init__.py

async def navigate_to_url(
    url: str,
    wait_for: str = "load",     # "load" or "complete"
    timeout_sec: int = 30,
) -> str:
    """
    Navigate to a URL and return JSON with a raw snapshot.
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        DRIVER.get(url)

        # DOM readiness
        try:
            _wait_document_ready(timeout=min(max(timeout_sec, 0), 60))
        except Exception:
            pass

        if (wait_for or "load").lower() == "complete":
            try:
                WebDriverWait(DRIVER, timeout_sec).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

        snapshot = _make_page_snapshot()
        return json.dumps({"ok": True, "action": "navigate", "url": url, "snapshot": snapshot})
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def fill_text(
    selector,
    text,
    selector_type,
    clear_first,
    timeout,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_snapshot_chars=5000,
    aggressive_cleaning=False,
    offset_chars=0,
):
    try:

        el = retry_op(lambda: find_element(
            DRIVER,
            selector,
            selector_type,
            timeout=int(timeout),
            visible_only=True,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
            shadow_root_selector=shadow_root_selector,
            shadow_root_selector_type=shadow_root_selector_type,
            stay_in_context=True,
        ))

        if clear_first:
            try:
                el.clear()
            except Exception:
                pass
        el.send_keys(text)
        _wait_document_ready(timeout=5.0)

        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": True, "action": "fill_text", "selector": selector, "snapshot": snapshot})
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

async def click_element(
    selector,
    selector_type,
    timeout,
    force_js,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_snapshot_chars=5000,
    aggressive_cleaning=False,
    offset_chars=0,
) -> str:
    try:

        el = retry_op(lambda: find_element(
            DRIVER,
            selector,
            selector_type,
            timeout=int(timeout),
            visible_only=True,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
            shadow_root_selector=shadow_root_selector,
            shadow_root_selector_type=shadow_root_selector_type,
            stay_in_context=True,
        ))

        _wait_clickable_element(el, timeout=timeout)

        if force_js:
            DRIVER.execute_script("arguments[0].click();", el)
        else:
            try:
                el.click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                el = retry_op(lambda: find_element(
                    DRIVER, selector, selector_type, timeout=int(timeout),
                    visible_only=True,
                    iframe_selector=iframe_selector, iframe_selector_type=iframe_selector_type,
                    shadow_root_selector=shadow_root_selector, shadow_root_selector_type=shadow_root_selector_type,
                    stay_in_context=True,
                ))
                DRIVER.execute_script("arguments[0].click();", el)

        _wait_document_ready(timeout=10.0)

        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({
            "ok": True,
            "action": "click",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })
    except TimeoutException:
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({
            "ok": False,
            "error": "timeout",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

async def take_screenshot(screenshot_path, return_base64, return_snapshot, thumbnail_width=None) -> str:
    """
    Take a screenshot of the current page.

    Args:
        screenshot_path: Optional path to save the full screenshot
        return_base64: Whether to return base64 encoded image
        return_snapshot: Whether to return page HTML snapshot
        thumbnail_width: Optional width in pixels for thumbnail (requires return_base64=True)
                        Default: 200px if return_base64 is True (accounts for MCP overhead)

    Returns:
        JSON string with ok status, saved path, optional base64 thumbnail, and snapshot
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        # Get full screenshot
        png_bytes = DRIVER.get_screenshot_as_png()

        # Save full screenshot to disk if path provided
        if screenshot_path:
            with open(screenshot_path, "wb") as f:
                f.write(png_bytes)

        payload = {"ok": True, "saved_to": screenshot_path}

        # Handle base64 return with thumbnail
        if return_base64:
            # Default thumbnail width to 200px to account for MCP protocol overhead (~3x)
            # 200px thumbnail = ~6K tokens, plus MCP overhead = ~18K total (under 25K limit)
            if thumbnail_width is None:
                thumbnail_width = 200

            # Validate thumbnail width
            if thumbnail_width < 50:
                return json.dumps({
                    "ok": False,
                    "error": "thumbnail_width_too_small",
                    "message": "thumbnail_width must be at least 50 pixels",
                    "min_width": 50,
                })

            try:
                from PIL import Image
            except ImportError:
                return json.dumps({
                    "ok": False,
                    "error": "pillow_not_installed",
                    "message": "Pillow is required for thumbnails. Install with: pip install Pillow",
                })

            try:
                # Create thumbnail
                img = Image.open(io.BytesIO(png_bytes))
                original_size = img.size

                # Calculate thumbnail dimensions maintaining aspect ratio
                aspect_ratio = img.height / img.width
                thumb_height = int(thumbnail_width * aspect_ratio)

                # Resize to thumbnail
                img.thumbnail((thumbnail_width, thumb_height), Image.Resampling.LANCZOS)

                # Encode thumbnail to base64
                thumb_buffer = io.BytesIO()
                img.save(thumb_buffer, format='PNG', optimize=True)
                thumb_b64 = base64.b64encode(thumb_buffer.getvalue()).decode('utf-8')

                payload["base64"] = thumb_b64
                payload["thumbnail_width"] = thumbnail_width
                payload["thumbnail_height"] = img.height
                payload["original_width"] = original_size[0]
                payload["original_height"] = original_size[1]
                payload["message"] = f"Screenshot saved (thumbnail: {thumbnail_width}x{img.height}px, original: {original_size[0]}x{original_size[1]}px)"

            except Exception as thumb_error:
                # Thumbnail failed but full screenshot was saved
                return json.dumps({
                    "ok": True,
                    "saved_to": screenshot_path,
                    "thumbnail_error": str(thumb_error),
                    "message": "Full screenshot saved, but thumbnail generation failed"
                })

        if return_snapshot:
            payload["snapshot"] = _make_page_snapshot()
        else:
            payload["snapshot"] = "Omitted to save tokens."

        return json.dumps(payload)
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        if return_snapshot:
            snapshot = _make_page_snapshot()
        else:
            snapshot = "Omitted to save tokens."
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def get_debug_diagnostics_info() -> str:
    try:
        cfg = get_env_config()
        udir = cfg.get("user_data_dir")
        port_file = str(Path(udir) / "DevToolsActivePort") if udir else None

        # Read DevToolsActivePort without relying on helpers
        port_val = None
        if udir:
            p = Path(udir) / "DevToolsActivePort"
            if p.exists():
                try:
                    port_val = int(p.read_text().splitlines()[0].strip())
                except Exception:
                    port_val = None

        devtools_http = None
        if port_val:
            import urllib.request, json as _json
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port_val}/json/version", timeout=1.0) as r:
                    devtools_http = _json.loads(r.read().decode("utf-8"))
            except Exception:
                devtools_http = {"ok": False}

        diag_summary = collect_diagnostics(DRIVER, None, cfg)  # string
        diagnostics = {
            "summary": diag_summary,
            "driver_initialized": bool(DRIVER),
            "debugger": f"{DEBUGGER_HOST}:{DEBUGGER_PORT}" if (DEBUGGER_HOST and DEBUGGER_PORT) else None,
            "devtools_active_port_file": {"path": port_file, "port": port_val, "exists": port_val is not None},
            "devtools_http_version": devtools_http,
        }

        snapshot = (_make_page_snapshot()
                    if DRIVER
                    else {"url": None, "title": None, "html": "", "truncated": False})
        return json.dumps({"ok": True, "diagnostics": diagnostics, "snapshot": snapshot})
    except Exception as e:

        diag = collect_diagnostics(DRIVER, e, get_env_config())
        return json.dumps({"ok": False, "error": str(e), "diagnostics": {"summary": diag}})

async def debug_element(
    selector,
    selector_type,
    timeout,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_html_length=5000,
    include_html=True,
):
    """
    Debug an element on the page.

    Args:
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait for element
        iframe_selector: Optional iframe selector
        iframe_selector_type: Iframe selector type
        shadow_root_selector: Optional shadow root selector
        shadow_root_selector_type: Shadow root selector type
        max_html_length: Maximum length of outerHTML to return (default: 5000 chars)
        include_html: Whether to include HTML in response (default: True)

    Returns:
        JSON string with debug information
    """
    try:
        info: Dict[str, Any] = {
            "selector": selector,
            "selector_type": selector_type,
            "exists": False,
            "displayed": None,
            "enabled": None,
            "clickable": None,
            "rect": None,
            "outerHTML": None,
            "truncated": False,
            "notes": [],
        }

        try:
            el = retry_op(lambda: find_element(
                DRIVER,
                selector,
                selector_type,
                timeout=int(timeout),
                visible_only=False,
                iframe_selector=iframe_selector,
                iframe_selector_type=iframe_selector_type,
                shadow_root_selector=shadow_root_selector,
                shadow_root_selector_type=shadow_root_selector_type,
                stay_in_context=True,
            ))
            info["exists"] = True

            try:
                info["displayed"] = bool(el.is_displayed())
            except Exception:
                info["displayed"] = None
            try:
                info["enabled"] = bool(el.is_enabled())
            except Exception:
                info["enabled"] = None

            try:
                _wait_clickable_element(el, timeout=timeout)
                info["clickable"] = True
            except Exception:
                info["clickable"] = False

            try:
                r = el.rect
                info["rect"] = {
                    "x": r.get("x"),
                    "y": r.get("y"),
                    "width": r.get("width"),
                    "height": r.get("height"),
                }
            except Exception:
                info["rect"] = None

            # Get HTML if requested
            if include_html:
                try:
                    html = DRIVER.execute_script("return arguments[0].outerHTML;", el)
                    # Clean invalid characters
                    html = html.replace('\x00', '').encode('utf-8', errors='ignore').decode('utf-8')

                    # Truncate if too large
                    full_length = len(html)
                    if max_html_length and len(html) > max_html_length:
                        info["outerHTML"] = html[:max_html_length]
                        info["truncated"] = True
                        info["full_html_length"] = full_length
                        info["notes"].append(f"HTML truncated from {full_length} to {max_html_length} chars")
                    else:
                        info["outerHTML"] = html
                        info["truncated"] = False
                except Exception as e:
                    info["outerHTML"] = None
                    info["notes"].append(f"Could not get HTML: {str(e)}")
            else:
                info["notes"].append("HTML omitted (include_html=False)")

        except TimeoutException:
            info["notes"].append("Element not found within timeout")
        except Exception as e:
            info["notes"].append(f"Error while probing element: {repr(e)}")

        snapshot = _make_page_snapshot()
        return json.dumps({"ok": True, "debug": info, "snapshot": snapshot})
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

async def unlock_browser():
    owner = ensure_process_tag()
    released = _release_action_lock(owner)
    return json.dumps({"ok": True, "released": bool(released)})

async def close_browser() -> str:
    try:
        closed = close_singleton_window()
        msg = "Browser window closed successfully" if closed else "No window to close"
        return json.dumps({"ok": True, "closed": bool(closed), "message": msg})
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag})

async def force_close_all_chrome() -> str:
    """
    Force close all Chrome processes, quit driver, and clean up all state.
    Use this to recover from stuck Chrome instances or when normal close_browser fails.
    """
    global DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, TARGET_ID, WINDOW_ID, MY_TAG

    killed_processes = []
    errors = []

    try:
        # 1. Try to quit the Selenium driver gracefully
        if DRIVER is not None:
            try:
                DRIVER.quit()
            except Exception as e:
                errors.append(f"Driver quit failed: {e}")
            DRIVER = None

        # 2. Get config to find which Chrome processes to kill
        try:
            cfg = get_env_config()
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
        DEBUGGER_HOST = None
        DEBUGGER_PORT = None
        TARGET_ID = None
        WINDOW_ID = None

        # 6. Release locks
        try:
            if MY_TAG:
                _release_action_lock(MY_TAG)
        except Exception as e:
            errors.append(f"Lock release failed: {e}")

        # 7. Clean up lock files
        try:
            if user_data_dir:
                lock_dir = Path(LOCK_DIR)
                # lock_dir = Path(tempfile.gettempdir()) / "mcp_browser_locks"
                if lock_dir.exists():
                    profile_key_val = profile_key(cfg) if cfg else ""
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

async def scroll(x: int, y: int, max_snapshot_chars=0, aggressive_cleaning=False, offset_chars=0) -> str:
    """
    Scroll the page by the specified pixel amounts.

    Args:
        x: Horizontal scroll amount in pixels (positive = right, negative = left)
        y: Vertical scroll amount in pixels (positive = down, negative = up)
        max_snapshot_chars: Maximum HTML characters to return (default: 0 to save context)
        aggressive_cleaning: Whether to apply aggressive HTML cleaning
        offset_chars: Number of characters to skip from start of HTML (default: 0)

    Returns:
        JSON string with ok status, action, scroll amounts, and page snapshot
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        DRIVER.execute_script(f"window.scrollBy({int(x)}, {int(y)});")
        time.sleep(0.3)  # Brief pause to allow scroll to complete

        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({
            "ok": True,
            "action": "scroll",
            "x": int(x),
            "y": int(y),
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def send_keys(
    key: str,
    selector: Optional[str] = None,
    selector_type: str = "css",
    timeout: float = 10.0,
) -> str:
    """
    Send keyboard keys to an element or to the active element.

    Args:
        key: Key to send (ENTER, TAB, ESCAPE, ARROW_DOWN, etc.)
        selector: Optional CSS selector, XPath, or ID of element to send keys to
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait for element in seconds

    Returns:
        JSON string with ok status, action, key sent, and page snapshot
    """
    try:
        from selenium.webdriver.common.keys import Keys

        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        # Map string key names to Selenium Keys
        key_mapping = {
            "ENTER": Keys.ENTER,
            "RETURN": Keys.RETURN,
            "TAB": Keys.TAB,
            "ESCAPE": Keys.ESCAPE,
            "ESC": Keys.ESCAPE,
            "SPACE": Keys.SPACE,
            "BACKSPACE": Keys.BACKSPACE,
            "DELETE": Keys.DELETE,
            "ARROW_UP": Keys.ARROW_UP,
            "ARROW_DOWN": Keys.ARROW_DOWN,
            "ARROW_LEFT": Keys.ARROW_LEFT,
            "ARROW_RIGHT": Keys.ARROW_RIGHT,
            "PAGE_UP": Keys.PAGE_UP,
            "PAGE_DOWN": Keys.PAGE_DOWN,
            "HOME": Keys.HOME,
            "END": Keys.END,
            "F1": Keys.F1,
            "F2": Keys.F2,
            "F3": Keys.F3,
            "F4": Keys.F4,
            "F5": Keys.F5,
            "F6": Keys.F6,
            "F7": Keys.F7,
            "F8": Keys.F8,
            "F9": Keys.F9,
            "F10": Keys.F10,
            "F11": Keys.F11,
            "F12": Keys.F12,
        }

        selenium_key = key_mapping.get(key.upper(), key)

        if selector:
            # Send keys to specific element
            el = retry_op(lambda: find_element(
                DRIVER,
                selector,
                selector_type,
                timeout=int(timeout),
                visible_only=True,
            ))
            el.send_keys(selenium_key)
        else:
            # Send keys to active element (usually body or focused element)
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(DRIVER).send_keys(selenium_key).perform()

        time.sleep(0.2)  # Brief pause
        snapshot = _make_page_snapshot()

        return json.dumps({
            "ok": True,
            "action": "send_keys",
            "key": key,
            "selector": selector,
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def wait_for_element(
    selector: str,
    selector_type: str = "css",
    timeout: float = 10.0,
    condition: str = "visible",
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
) -> str:
    """
    Wait for an element to meet a specific condition.

    Args:
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait in seconds
        condition: Condition to wait for - 'present', 'visible', or 'clickable'
        iframe_selector: Optional selector for iframe containing the element
        iframe_selector_type: Selector type for the iframe

    Returns:
        JSON string with ok status, element found status, and page snapshot
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        visible_only = condition in ("visible", "clickable")

        el = find_element(
            DRIVER,
            selector,
            selector_type,
            timeout=int(timeout),
            visible_only=visible_only,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
        )

        if condition == "clickable":
            _wait_clickable_element(el, timeout=timeout)

        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": True,
            "action": "wait_for_element",
            "selector": selector,
            "condition": condition,
            "found": True,
            "snapshot": snapshot,
            "message": f"Element '{selector}' is now {condition}"
        })
    except TimeoutException:
        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": False,
            "error": "timeout",
            "selector": selector,
            "condition": condition,
            "found": False,
            "snapshot": snapshot,
            "message": f"Element '{selector}' did not become {condition} within {timeout}s"
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

#endregion


#region
async def get_current_page_meta():
    """
    Get current page metadata from the active window/tab.

    Returns:
        Dict[str, Optional[str]]: A metadata dictionary with keys such as:
            - "url": The current page URL, or None if not available.
            - "title": The current document.title, or None.
            - "window_tag": An implementation-specific identifier for the window/tab.
    """
    try:
        url = DRIVER.current_url if DRIVER else None
    except Exception:
        url = None
    try:
        title = DRIVER.title if DRIVER else None
    except Exception:
        title = None
    try:
        window_tag = ensure_process_tag()
    except Exception:
        window_tag = None
    return {"url": url, "title": title, "window_tag": window_tag}
#endregion