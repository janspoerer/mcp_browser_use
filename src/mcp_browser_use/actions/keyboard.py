"""Keyboard input and scrolling."""

from selenium.webdriver.common.keys import Keys

from ..context import get_context


def send_keys(keys_string: str) -> dict:
    """Send keyboard input."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(ctx.driver).send_keys(keys_string).perform()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def scroll(direction: str = "down", amount: int = 300) -> dict:
    """Scroll the page."""
    ctx = get_context()
    if not ctx.driver:
        return {"ok": False, "error": "No driver available"}
    try:
        if direction == "down":
            ctx.driver.execute_script(f"window.scrollBy(0, {amount});")
        elif direction == "up":
            ctx.driver.execute_script(f"window.scrollBy(0, -{amount});")
        elif direction == "top":
            ctx.driver.execute_script("window.scrollTo(0, 0);")
        elif direction == "bottom":
            ctx.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = [
    'send_keys',
    'scroll',
]
