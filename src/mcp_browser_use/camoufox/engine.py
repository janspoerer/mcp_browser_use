"""Camoufox (Firefox-based) browser engine for anti-bot scraping."""

import base64
import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Global session store: session_id -> {'cf': AsyncCamoufox, 'browser': Browser|BrowserContext, 'page': Page}
_sessions: dict = {}


def _get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        raise KeyError(f"No camoufox session '{session_id}'. Call camoufox_start first.")
    return _sessions[session_id]


async def start(
    headless: bool = False,
    locale: str = "de-DE",
    os_hint: Optional[list] = None,
    profile_dir: Optional[str] = None,
) -> str:
    """Start a camoufox browser session. Returns session_id.

    If profile_dir is given, a persistent Firefox profile is used so that
    cookies and localStorage survive MCP server restarts.
    """
    from camoufox.async_api import AsyncCamoufox

    session_id = str(uuid.uuid4())[:8]
    os_list = os_hint or ["windows"]

    kwargs = dict(headless=headless, geoip=False, os=os_list, locale=locale)

    if profile_dir:
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        kwargs["persistent_context"] = True
        kwargs["user_data_dir"] = str(profile_dir)

    cf = AsyncCamoufox(**kwargs)
    browser_or_ctx = await cf.__aenter__()
    page = await browser_or_ctx.new_page()

    _sessions[session_id] = {"cf": cf, "browser": browser_or_ctx, "page": page}
    logger.info(
        f"Camoufox session {session_id} started "
        f"(os={os_list}, locale={locale}, headless={headless}, profile={profile_dir!r})"
    )
    return session_id


async def navigate(session_id: str, url: str) -> dict:
    sess = _get_session(session_id)
    page = sess["page"]
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    title = await page.title()
    return {"url": page.url, "title": title, "status": resp.status if resp else None}


async def get_html(session_id: str, clean: bool = True) -> str:
    """Return page HTML, optionally stripped of script/style tags."""
    sess = _get_session(session_id)
    page = sess["page"]
    html = await page.content()
    if clean:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["script", "style", "meta", "link", "noscript"]):
            tag.extract()
        html = " ".join(str(soup).split())
    return html


async def screenshot(session_id: str) -> str:
    """Take screenshot and return base64-encoded PNG."""
    sess = _get_session(session_id)
    page = sess["page"]
    data = await page.screenshot(type="png")
    return base64.b64encode(data).decode("utf-8")


async def click(session_id: str, selector: str, selector_type: str = "css") -> dict:
    sess = _get_session(session_id)
    page = sess["page"]
    if selector_type == "xpath":
        loc = page.locator(f"xpath={selector}").first
    else:
        loc = page.locator(selector).first
    await loc.click(timeout=10_000)
    await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    title = await page.title()
    return {"url": page.url, "title": title}


async def fill_text(session_id: str, selector: str, text: str, selector_type: str = "css") -> dict:
    sess = _get_session(session_id)
    page = sess["page"]
    if selector_type == "xpath":
        loc = page.locator(f"xpath={selector}").first
    else:
        loc = page.locator(selector).first
    await loc.fill(text, timeout=10_000)
    title = await page.title()
    return {"url": page.url, "title": title}


async def wait_for_element(session_id: str, selector: str, timeout: int = 10, selector_type: str = "css") -> dict:
    sess = _get_session(session_id)
    page = sess["page"]
    if selector_type == "xpath":
        loc = page.locator(f"xpath={selector}").first
    else:
        loc = page.locator(selector).first
    await loc.wait_for(state="visible", timeout=timeout * 1000)
    return {"found": True, "selector": selector}


async def evaluate_js(session_id: str, script: str) -> any:
    """Evaluate JavaScript in the current page context. Returns the result."""
    sess = _get_session(session_id)
    page = sess["page"]
    result = await page.evaluate(script)
    return result


async def close(session_id: str) -> None:
    if session_id not in _sessions:
        return
    sess = _sessions.pop(session_id)
    try:
        await sess["cf"].__aexit__(None, None, None)
    except Exception as e:
        logger.warning(f"Error closing camoufox session {session_id}: {e}")
    logger.info(f"Camoufox session {session_id} closed.")


async def close_all() -> int:
    session_ids = list(_sessions.keys())
    for sid in session_ids:
        await close(sid)
    return len(session_ids)
