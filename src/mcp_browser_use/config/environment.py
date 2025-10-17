"""Environment configuration and validation."""

import os
import hashlib
from pathlib import Path
from typing import Optional

import logging
logger = logging.getLogger(__name__)


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


def is_default_user_data_dir(user_data_dir: str) -> bool:
    """
    Check if the given user_data_dir matches the platform's default Chrome profile location.

    This is used to determine whether we can safely kill all Chrome processes or if we should
    be more conservative (to avoid killing the user's main browser).

    Returns True if user_data_dir matches a known default Chrome profile path for the current platform.
    """
    import platform

    system = platform.system()
    user_data_dir_resolved = str(Path(user_data_dir).resolve())

    # Define default profile locations for each platform
    if system == "Darwin":  # macOS
        default_paths = [
            str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome"),
            str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome Beta"),
            str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome Canary"),
        ]
    elif system == "Windows":
        default_paths = [
            str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"),
            str(Path.home() / "AppData" / "Local" / "Google" / "Chrome Beta" / "User Data"),
            str(Path.home() / "AppData" / "Local" / "Google" / "Chrome SxS" / "User Data"),  # Canary
        ]
    elif system == "Linux":
        default_paths = [
            str(Path.home() / ".config" / "google-chrome"),
            str(Path.home() / ".config" / "google-chrome-beta"),
            str(Path.home() / ".config" / "google-chrome-unstable"),  # Canary equivalent
        ]
    else:
        # Unknown platform - assume it's not default to be safe
        return False

    # Resolve all default paths and check for matches
    for default_path in default_paths:
        try:
            default_resolved = str(Path(default_path).resolve())
            if user_data_dir_resolved == default_resolved:
                return True
        except Exception:
            # If we can't resolve a path, skip it
            continue

    return False
