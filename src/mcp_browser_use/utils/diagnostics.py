"""Diagnostics and debugging information."""

import os
import sys
import json
import platform
import traceback
from typing import Optional
from selenium import webdriver
import selenium


def collect_diagnostics(driver: Optional[webdriver.Chrome], exc: Optional[Exception], config: dict) -> str:
    """Collect diagnostic information about the browser state."""
    from ..browser.chrome import _chrome_binary_for_platform

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


def get_debug_diagnostics_info() -> dict:
    """Get diagnostic information about the current state"""
    from ..helpers import DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, TARGET_ID

    info = {
        "has_driver": DRIVER is not None,
        "debugger_host": DEBUGGER_HOST,
        "debugger_port": DEBUGGER_PORT,
        "target_id": TARGET_ID,
    }

    if DRIVER:
        try:
            info["current_url"] = DRIVER.current_url
            info["window_handles"] = len(DRIVER.window_handles)
        except Exception as e:
            info["driver_error"] = str(e)

    return info


__all__ = [
    'collect_diagnostics',
    'get_debug_diagnostics_info',
]
