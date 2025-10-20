"""Chrome executable resolution, version detection, and directory validation."""

import os
import shutil
import platform
import subprocess
from pathlib import Path

import logging
logger = logging.getLogger(__name__)


def resolve_chrome_executable(cfg: dict) -> str:
    """
    Resolve Chrome executable path from config or platform defaults.

    Args:
        cfg: Configuration dict with optional chrome_path, chrome_executable, etc.

    Returns:
        str: Path to Chrome executable

    Raises:
        FileNotFoundError: If Chrome executable cannot be found
    """
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


def get_chrome_binary_for_platform(config: dict) -> str:
    """
    Get platform-specific Chrome binary path.

    Tries to find Chrome binary based on the current platform.
    Returns a reasonable default if not found.

    Args:
        config: Configuration dict with optional chrome_path

    Returns:
        str: Path to Chrome binary or "chrome" as fallback
    """
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


def get_chrome_version() -> str:
    """
    Get Chrome version string from registry or executable.

    Returns:
        str: Chrome version string or error message
    """
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


def is_default_user_data_dir(user_data_dir: str) -> bool:
    """
    Return True if user_data_dir is one of Chrome's default roots (where DevTools is refused).

    Args:
        user_data_dir: Path to Chrome user data directory

    Returns:
        bool: True if this is a default Chrome directory
    """
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


def validate_user_data_dir(user_data_dir: str) -> None:
    """
    Validate user_data_dir and raise if it's a default directory.

    Args:
        user_data_dir: Path to Chrome user data directory

    Raises:
        RuntimeError: If user_data_dir is a default Chrome directory
    """
    if is_default_user_data_dir(user_data_dir):
        if os.getenv("MCP_ALLOW_DEFAULT_USER_DATA_DIR", "0") != "1":
            raise RuntimeError(
                "Remote debugging is disabled on Chrome's default user-data directories.\n"
                f"Set *_PROFILE_USER_DATA_DIR to a separate path (e.g., '{Path(user_data_dir).parent}/Chrome Beta MCP'), "
                "optionally seed it from your existing profile, then retry.\n"
                "To override (not recommended), set MCP_ALLOW_DEFAULT_USER_DATA_DIR=1."
            )


__all__ = [
    'resolve_chrome_executable',
    'get_chrome_binary_for_platform',
    'get_chrome_version',
    'is_default_user_data_dir',
    'validate_user_data_dir',
]
