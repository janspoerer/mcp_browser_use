"""Keyboard input and scrolling."""

from selenium.webdriver.common.keys import Keys


def send_keys(keys_string: str) -> dict:
    """Send keyboard input (placeholder)"""
    from ..helpers import DRIVER
    if not DRIVER:
        return {"ok": False, "error": "No driver available"}
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(DRIVER).send_keys(keys_string).perform()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def scroll(direction: str = "down", amount: int = 300) -> dict:
    """Scroll the page"""
    from ..helpers import DRIVER
    if not DRIVER:
        return {"ok": False, "error": "No driver available"}
    try:
        if direction == "down":
            DRIVER.execute_script(f"window.scrollBy(0, {amount});")
        elif direction == "up":
            DRIVER.execute_script(f"window.scrollBy(0, -{amount});")
        elif direction == "top":
            DRIVER.execute_script("window.scrollTo(0, 0);")
        elif direction == "bottom":
            DRIVER.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = [
    'send_keys',
    'scroll',
]
