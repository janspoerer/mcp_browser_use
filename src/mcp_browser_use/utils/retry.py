"""Retry logic and error handling utilities."""

import time
import random
import json
from typing import Callable, Optional
from selenium.common.exceptions import (
    NoSuchWindowException,
    StaleElementReferenceException,
    WebDriverException,
)


def retry_op(fn: Callable, retries: int = 2, base_delay: float = 0.15):
    """
    Retry a function call that may fail due to transient Selenium exceptions.

    Args:
        fn: The function to call
        retries: Number of retry attempts (default: 2)
        base_delay: Base delay between retries in seconds (default: 0.15)

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries fail
    """
    for attempt in range(retries + 1):
        try:
            return fn()
        except (NoSuchWindowException, StaleElementReferenceException, WebDriverException):
            if attempt == retries:
                raise
            time.sleep(base_delay * (1.0 + random.random()))


def _read_json(path: str) -> Optional[dict]:
    """
    Read a JSON file and return its contents as a dict.

    Args:
        path: Path to the JSON file

    Returns:
        Dictionary from JSON file, or None if file doesn't exist or is invalid
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _now() -> float:
    """Get current time as a float timestamp."""
    return time.time()
