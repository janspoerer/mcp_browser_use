"""Diagnostics and debugging information utility functions."""

import sys
import platform
from typing import Optional
from selenium import webdriver
import selenium

from ..context import get_context
from ..browser.chrome_executable import get_chrome_binary_for_platform


def collect_diagnostics(
    driver: Optional[webdriver.Chrome] = None,
    exc: Optional[Exception] = None,
    config: Optional[dict] = None
) -> str:
    """
    Collect diagnostic information about the browser, driver, and environment.

    Args:
        driver: Selenium WebDriver instance (if None, will try to get from context)
        exc: Exception that occurred (can be None)
        config: Configuration dictionary (if None, will get from context)

    Returns:
        str: Formatted diagnostic information
    """
    ctx = get_context()

    # Use context if parameters not provided
    if driver is None:
        driver = ctx.driver

    if config is None:
        config = ctx.config

    # Get Chrome binary path
    chrome_path = config.get('chrome_path')
    if not chrome_path:
        try:
            chrome_path = get_chrome_binary_for_platform()
        except Exception:
            chrome_path = '<unknown>'

    parts = [
        f"OS                : {platform.system()} {platform.release()}",
        f"Python            : {sys.version.split()[0]}",
        f"Selenium          : {getattr(selenium, '__version__', '?')}",
        f"User-data dir     : {config.get('user_data_dir')}",
        f"Profile name      : {config.get('profile_name')}",
        f"Chrome binary     : {chrome_path}",
        f"Driver initialized: {driver is not None}",
        f"Debugger address  : {ctx.get_debugger_address() or '<none>'}",
        f"Window ready      : {ctx.is_window_ready()}",
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
