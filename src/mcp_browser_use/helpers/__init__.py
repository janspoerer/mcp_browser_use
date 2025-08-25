# mcp_browser_use/__init__.py
#region Imports
import os
import sys
import json
import time
import psutil
import socket
import shutil
import hashlib
import asyncio
import tempfile
import platform
import subprocess
import contextlib
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Callable, Optional, Tuple, Dict, Any
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
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
#endregion

#region Imports Dotenv
from dotenv import load_dotenv
load_dotenv()
#endregion


# -----------------------------
# Constants / policy parameters
# -----------------------------
ACTION_LOCK_ACQUIRE_TIMEOUT_SEC = 5.0      # How long to wait to acquire the action lock
ACTION_LOCK_MAX_HOLD_SEC = 10.0            # Hard cap to prevent indefinite blocking
START_LOCK_WAIT_SEC = 8.0                  # How long to wait to acquire the startup lock
RENDEZVOUS_TTL_SEC = 24 * 3600             # How long a rendezvous file is considered valid


#region Configuration and keys
def get_env_config() -> dict:
    """
    Read environment variables and validate required ones.
    Required: CHROME_PROFILE_USER_DATA_DIR
    Optional: CHROME_PROFILE_NAME (default 'Default')
              CHROME_EXECUTABLE_PATH
              CHROME_REMOTE_DEBUG_PORT
    """
    user_data_dir = os.getenv("CHROME_PROFILE_USER_DATA_DIR", "").strip()
    if not user_data_dir:
        raise EnvironmentError("CHROME_PROFILE_USER_DATA_DIR is required.")

    profile_name = os.getenv("CHROME_PROFILE_NAME", "Default").strip() or "Default"
    chrome_path = os.getenv("CHROME_EXECUTABLE_PATH", "").strip() or None
    fixed_port = os.getenv("CHROME_REMOTE_DEBUG_PORT", "").strip()
    fixed_port = int(fixed_port) if fixed_port.isdigit() else None

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
INTRA_PROCESS_LOCK = asyncio.Lock()

DRIVER = None
DEBUGGER_HOST: Optional[str] = None
DEBUGGER_PORT: Optional[int] = None
MY_TAG: Optional[str] = None

# Single-window identity for this process (the MCP server will be started independently by multiple agents; each has its own IDs)
TARGET_ID: Optional[str] = None
WINDOW_ID: Optional[int] = None

LOCK_DIR = os.getenv("MCP_BROWSER_LOCK_DIR") or str(Path(tempfile.gettempdir()) / "mcp_chrome_locks")
Path(LOCK_DIR).mkdir(parents=True, exist_ok=True)

# Action lock TTL (post-action exclusivity) and wait time
ACTION_LOCK_TTL_SECS = int(os.getenv("MCP_ACTION_LOCK_TTL", "10"))
ACTION_LOCK_WAIT_SECS = int(os.getenv("MCP_ACTION_LOCK_WAIT", "30"))
FILE_MUTEX_STALE_SECS = int(os.getenv("MCP_FILE_MUTEX_STALE_SECS", "60"))

# Truncation
MAX_SNAPSHOT_CHARS = int(os.getenv("MCP_MAX_SNAPSHOT_CHARS", "0"))
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

def _renew_action_lock(owner: str, ttl: int = ACTION_LOCK_TTL_SECS):
    try:
        _acquire_softlock(owner=owner, ttl=ttl, wait=False, wait_timeout=0) # 'wait=False' makes this a no-wait best-effort renew
    except Exception:
        pass

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
    # Busy – return a compact JSON payload
    return json.dumps({
        "error": "locked",
        "owner": res.get("owner"),
        "expires_at": res.get("expires_at"),
        "lock_ttl_seconds": ACTION_LOCK_TTL_SECS,
    })
#endregion

#begin Driver & window
def _ensure_driver():
    global DRIVER, DEBUGGER_HOST, DEBUGGER_PORT
    if DRIVER is None:
        host, port, _ = start_or_attach_chrome_from_env(get_env_config())
        DRIVER = create_webdriver(host, port, get_env_config())
        DEBUGGER_HOST, DEBUGGER_PORT = host, port

def ensure_process_tag() -> str:
    global MY_TAG
    if MY_TAG is None:
        MY_TAG = make_process_tag()
    return MY_TAG

def _ensure_singleton_window(driver: webdriver.Chrome):
    global TARGET_ID, WINDOW_ID

    if TARGET_ID:
        h = _handle_for_target(driver, TARGET_ID)
        if h:
            driver.switch_to.window(h)
            return

    # Try to create a real OS window; if no targetId is returned, create one explicitly.
    try:
        win = driver.execute_cdp_cmd("Browser.createWindow", {"state": "normal"})
        WINDOW_ID = win.get("windowId")
        TARGET_ID = win.get("targetId")
        if not TARGET_ID:
            t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
            TARGET_ID = t["targetId"]
            if not WINDOW_ID:
                try:
                    w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": TARGET_ID})
                    WINDOW_ID = w.get("windowId")
                except Exception:
                    WINDOW_ID = None
    except Exception:
        # Fallback to Target API directly
        t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
        TARGET_ID = t["targetId"]
        try:
            w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": TARGET_ID})
            WINDOW_ID = w.get("windowId")
        except Exception:
            WINDOW_ID = None

    h = _handle_for_target(driver, TARGET_ID)
    if h:
        driver.switch_to.window(h)

def _ensure_driver_and_window():
    _ensure_driver()
    ensure_process_tag()
    _ensure_singleton_window(DRIVER)

def close_singleton_window() -> bool:
    """
    Close the singleton window (by targetId) without quitting Chrome.
    Resets TARGET_ID/WINDOW_ID so a subsequent start will create a new window.
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

    TARGET_ID = None
    WINDOW_ID = None
    return closed

def _handle_for_target(driver, target_id: Optional[str]) -> Optional[str]:
    if not target_id:
        return None
    # Fast path
    for h in driver.window_handles:
        if h.endswith(target_id):
            return h
    # Robust path
    current = driver.current_window_handle if driver.window_handles else None
    try:
        for h in driver.window_handles:
            driver.switch_to.window(h)
            info = driver.execute_cdp_cmd("Target.getTargetInfo", {})
            tid = info.get("targetInfo", {}).get("targetId") or info.get("targetId")
            if tid == target_id:
                return h
    finally:
        if current and current in driver.window_handles:
            driver.switch_to.window(current)
    # Last resort
    try:
        driver.execute_cdp_cmd("Target.activateTarget", {"targetId": target_id})
        for h in driver.window_handles:
            if h.endswith(target_id):
                return h
    except Exception:
        pass
    return None

def _ensure_session_window(driver, session):
    tid = session.get("target_id")
    if tid:
        h = _handle_for_target(driver, tid)
        if h:
            driver.switch_to.window(h)
            return

    # Create a real OS window with its own target
    try:
        win = driver.execute_cdp_cmd("Browser.createWindow", {"state": "normal"})
        session["window_id"] = win["windowId"]
        session["target_id"] = win["targetId"]
    except Exception:
        # Fallback to a new window via Target API
        t = driver.execute_cdp_cmd("Target.createTarget", {"url": "about:blank", "newWindow": True})
        session["target_id"] = t["targetId"]
        # You can get window_id after the fact:
        w = driver.execute_cdp_cmd("Browser.getWindowForTarget", {"targetId": session["target_id"]})
        session["window_id"] = w["windowId"]

    h = _handle_for_target(driver, session["target_id"])
    if h:
        driver.switch_to.window(h)

#region
def _wait_document_ready(timeout: float = 10.0):
    try:
        WebDriverWait(DRIVER, timeout).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )
    except Exception:
        # Non-fatal; proceed with snapshot
        pass

def _make_page_snapshot(max_chars: Optional[int] = None) -> Dict[str, Any]:
    """
    Return a cleaned page snapshot: url, title, cleaned html.
    Ensures we are in default_content before capturing page_source.
    """
    if max_chars is None:
        max_chars = MAX_SNAPSHOT_CHARS

    # Make sure we're at top-level document
    try:
        if DRIVER is not None:
            DRIVER.switch_to.default_content()
    except Exception:
        pass

    url = None
    title = None
    try:
        url = DRIVER.current_url
    except Exception:
        pass
    try:
        title = DRIVER.title
    except Exception:
        pass

    html = ""
    truncated = False
    try:
        html = get_cleaned_html(DRIVER) or ""
        if max_chars and max_chars > 0 and len(html) > max_chars:
            html = html[:max_chars]
            truncated = True
    except Exception:
        pass

    return {
        "url": url,
        "title": title,
        "html": html,
        "truncated": truncated,
    }
#endregion

#region Tool helpers (clickable wait using a lambda on the element)
def _wait_clickable_element(el, timeout: float = 10.0):
    WebDriverWait(DRIVER, timeout).until(lambda d: el.is_displayed() and el.is_enabled())
    return el
#endregion


# -----------------------------
# Paths for coordination artifacts
# -----------------------------
def rendezvous_path(config: dict) -> str:
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_rendezvous_{profile_key(config)}.json")

def start_lock_dir(config: dict) -> str:
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_start_lock_{profile_key(config)}")

def action_lock_dir(config: dict) -> str:
    return os.path.join(tempfile.gettempdir(), f"mcp_chrome_action_lock_{profile_key(config)}")

def chromedriver_log_path(config: dict) -> str:
    return os.path.join(tempfile.gettempdir(), f"chromedriver_shared_{profile_key(config)}_{os.getpid()}.log")

# -----------------------------
# DevTools endpoint and Chrome discovery
# -----------------------------
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

# -----------------------------
# Rendezvous API
# -----------------------------
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

# -----------------------------
# Startup lock (single starter)
# -----------------------------
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


# -----------------------------
# Attach or launch Chrome
# -----------------------------
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

def start_or_attach_chrome_from_env(config: dict) -> Tuple[str, int, Optional[psutil.Process]]:
    user_data_dir = config["user_data_dir"]
    profile_name = config["profile_name"]
    fixed_port = config.get("fixed_port")
    host = "127.0.0.1"

    # Fixed port path
    if fixed_port:
        port = fixed_port
        if is_debugger_listening(host, port):
            return host, port, None
        # Start Chrome on fixed port
        binary = _chrome_binary_for_platform(config)
        cmd = [
            binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile_name}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if is_debugger_listening(host, port):
                return host, port, proc
            time.sleep(0.1)
        if chrome_running_with_userdata(user_data_dir):
            raise RuntimeError(
                f"Chrome is already running with this profile but without remote debugging on {port}. "
                "Close Chrome or relaunch with --remote-debugging-port set."
            )
        raise RuntimeError(f"Failed to start Chrome with remote debugging on {port}.")

    # Rendezvous path
    port, pid = read_rendezvous(config)
    if port:
        return host, port, None

    got_lock = acquire_start_lock(config, timeout_sec=START_LOCK_WAIT_SEC)
    try:
        if not got_lock:
            # Spin a little waiting for rendezvous creation by the winner
            for _ in range(50):
                port, pid = read_rendezvous(config)
                if port:
                    return host, port, None
                time.sleep(0.1)
            raise RuntimeError("Timeout acquiring start lock for Chrome rendezvous.")

        # Inside lock: recheck rendezvous
        port, pid = read_rendezvous(config)
        if port:
            return host, port, None

        # Choose a free port and start Chrome
        port = get_free_port()
        binary = _chrome_binary_for_platform(config)
        cmd = [
            binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile_name}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

# -----------------------------
# Selenium WebDriver attached to shared Chrome
# -----------------------------
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

# -----------------------------
# Per-process window ownership
# -----------------------------
def make_process_tag() -> str:
    import uuid
    return f"agent:{uuid.uuid4().hex}"



# -----------------------------
# Resilience: retries and DOM utils
# -----------------------------
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

def remove_unwanted_tags(html_content: str) -> str:
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup.find_all(['script', 'style', 'meta', 'link', 'noscript']):
        tag.extract()
    return ' '.join(str(soup).split())

def get_cleaned_html(driver: webdriver.Chrome) -> str:
    html_content = driver.page_source
    return remove_unwanted_tags(html_content)

# -----------------------------
# Diagnostics
# -----------------------------
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
        drv_ver = driver.capabilities.get("chromedriverVersion") or driver.capabilities.get("browserVersion") or "<unknown>"
        parts.append(f"Driver version    : {drv_ver}")
        opts = driver.capabilities.get("goog:chromeOptions", {}) or {}
        args = opts.get("args") or []
        parts.append(f"Chrome args       : {' '.join(args)}")
    if exc:
        parts += [
            "---- ERROR ----",
            f"Error type        : {type(exc).__name__}",
            f"Error message     : {exc}",
        ]
    return "\n".join(parts)

