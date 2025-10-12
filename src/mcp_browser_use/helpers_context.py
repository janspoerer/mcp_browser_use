# mcp_browser_use/helpers_context.py
import os
import time
from typing import Optional
from selenium.webdriver.support.ui import WebDriverWait
from .context_pack import ContextPack, ReturnMode
from .cleaners import basic_prune, approx_token_count, extract_outline


def _wait_for_dom_ready(driver, timeout=15):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def _apply_snapshot_settle():
    settle_ms = int(os.getenv("SNAPSHOT_SETTLE_MS", "200"))  # 0 disables
    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)

def get_outer_html(driver) -> str:
    _wait_for_dom_ready(driver)
    _apply_snapshot_settle()
    # If you currently use driver.page_source, keep that; both are fine.
    return driver.execute_script("return document.documentElement.outerHTML")

def take_screenshot(driver, path: str):
    _wait_for_dom_ready(driver)
    _apply_snapshot_settle()
    driver.save_screenshot(path)

def pack_snapshot(
    *,
    window_tag: Optional[str],
    url: Optional[str],
    title: Optional[str],
    raw_html: Optional[str],
    return_mode: str,
    cleaning_level: int,
    token_budget: Optional[int],
) -> ContextPack:
    cp = ContextPack(
        window_tag=window_tag,
        url=url,
        title=title,
        cleaning_level_applied=cleaning_level,
        snapshot_mode=return_mode,
        tokens_budget=token_budget,
    )

    html = raw_html or ""
    cleaned_html, pruned_counts = basic_prune(html, level=cleaning_level)
    cp.pruned_counts = pruned_counts

    if return_mode == ReturnMode.OUTLINE:
        outline = extract_outline(cleaned_html)
        cp.outline_present = True
        cp.outline = [
            # convert dict -> dataclass-ish dict; leaving as dict is fine for now
            o for o in outline
        ]
        cp.approx_tokens = approx_token_count(" ".join([o["text"] for o in outline]))
        return cp

    if return_mode == ReturnMode.HTML:
        # Respect token budget by truncating cleaned_html conservatively
        if token_budget:
            # Convert tokens -> chars budget ~4 chars/token
            char_budget = token_budget * 4
            if len(cleaned_html) > char_budget:
                cleaned_html = cleaned_html[:char_budget]
                cp.hard_capped = True
        cp.html = cleaned_html
        cp.approx_tokens = approx_token_count(cleaned_html)
        return cp

    if return_mode == ReturnMode.TEXT:
        # Very naive visible text extraction through soup.get_text()
        try:
            from bs4 import BeautifulSoup
            txt = BeautifulSoup(cleaned_html, "html.parser").get_text("\n", strip=True)
        except Exception:
            txt = ""
        if token_budget:
            char_budget = token_budget * 4
            if len(txt) > char_budget:
                txt = txt[:char_budget]
                cp.hard_capped = True
        cp.text = txt
        cp.approx_tokens = approx_token_count(txt)
        return cp

    # Fallback to outline
    outline = extract_outline(cleaned_html)
    cp.outline_present = True
    cp.outline = [o for o in outline]
    cp.approx_tokens = approx_token_count(" ".join([o["text"] for o in outline]))
    return cp



def pack_from_snapshot_dict(
    snapshot: dict,
    window_tag: Optional[str],
    return_mode: str,
    cleaning_level: int,
    token_budget: Optional[int],
):
    """
    Build a ContextPack object from a raw snapshot dict and packing controls.

    Applies structural/content pruning and optional truncation to fit the `token_budget`,
    derives the selected representation (outline/text/html/dompaths/mixed), and attaches
    metadata including `window_tag`.

    Args:
        snapshot: Raw snapshot dict (e.g., {"url", "title", "html", ...}).
        window_tag: Optional identifier for the active window/tab.
        return_mode: Target representation to materialize in the ContextPack.
        cleaning_level: Structural/content cleaning intensity (0–3).
        token_budget: Optional approximate token cap for the returned snapshot.

    Returns:
        ContextPack: The structured envelope ready for JSON serialization.

    Notes:
        - Consider computing a `page_fingerprint` (e.g., sha256 of cleaned html) to assist
          agents in cheap change detection between steps.
    """
    return pack_snapshot(
        window_tag=window_tag,
        url=snapshot.get("url"),
        title=snapshot.get("title"),
        raw_html=snapshot.get("html"),
        return_mode=return_mode,
        cleaning_level=cleaning_level,
        token_budget=token_budget,
    )