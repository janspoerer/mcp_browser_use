"""Diagnostics and debugging information utility functions."""

import sys
import platform
from typing import Optional
from selenium import webdriver
import selenium

# Import helpers module to access globals (avoids circular imports)
import mcp_browser_use.helpers as helpers


def collect_diagnostics(driver: Optional[webdriver.Chrome], exc: Optional[Exception], config: dict) -> str:
    """
    Collect diagnostic information about the browser, driver, and environment.

    Args:
        driver: Selenium WebDriver instance (can be None)
        exc: Exception that occurred (can be None)
        config: Configuration dictionary with user_data_dir, profile_name, chrome_path

    Returns:
        str: Formatted diagnostic information
    """
    parts = [
        f"OS                : {platform.system()} {platform.release()}",
        f"Python            : {sys.version.split()[0]}",
        f"Selenium          : {getattr(selenium, '__version__', '?')}",
        f"User-data dir     : {config.get('user_data_dir')}",
        f"Profile name      : {config.get('profile_name')}",
        f"Chrome binary     : {config.get('chrome_path') or helpers._chrome_binary_for_platform(config)}",
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
        # Ensure args is iterable
        if not isinstance(args, (list, tuple)):
            args = []
        parts.append(f"Chrome args       : {' '.join(args)}")
    if exc:
        parts += [
            "---- ERROR ----",
            f"Error type        : {type(exc).__name__}",
            f"Error message     : {exc}",
        ]
    return "\n".join(parts)


__all__ = ['collect_diagnostics']
