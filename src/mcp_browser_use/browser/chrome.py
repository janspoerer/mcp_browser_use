"""Chrome executable resolution and process management."""

import os
import sys
import time
import shutil
import platform
import subprocess
import psutil
from pathlib import Path
from typing import Optional, Tuple

import logging
logger = logging.getLogger(__name__)


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



__all__ = [
    '_resolve_chrome_executable',
    '_chrome_binary_for_platform',
    'chrome_running_with_userdata',
    'find_chrome_process_by_port',
    'get_chrome_version',
    '_launch_chrome_with_debug',
    'start_or_attach_chrome_from_env',
    'is_default_user_data_dir',
]
