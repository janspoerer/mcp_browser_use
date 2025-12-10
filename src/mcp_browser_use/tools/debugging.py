"""Debugging and diagnostic tool implementations."""

import json
from pathlib import Path
from typing import Dict, Any
from selenium.common.exceptions import TimeoutException
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics
from ..actions.elements import find_element, _wait_clickable_element
from ..actions.screenshots import _make_page_snapshot
from ..utils.retry import retry_op


async def get_debug_diagnostics_info() -> str:
    """Get debug diagnostics using context."""
    ctx = get_context()

    try:
        cfg = ctx.config
        udir = cfg.get("user_data_dir")
        port_file = str(Path(udir) / "DevToolsActivePort") if udir else None

        # Read DevToolsActivePort
        port_val = None
        if udir:
            p = Path(udir) / "DevToolsActivePort"
            if p.exists():
                try:
                    port_val = int(p.read_text().splitlines()[0].strip())
                except Exception:
                    port_val = None

        devtools_http = None
        if port_val:
            import urllib.request, json as _json
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port_val}/json/version", timeout=1.0) as r:
                    devtools_http = _json.loads(r.read().decode("utf-8"))
            except Exception:
                devtools_http = {"ok": False}

        diag_summary = collect_diagnostics(driver=ctx.driver, exc=None, config=cfg)
        diagnostics = {
            "summary": diag_summary,
            "driver_initialized": ctx.is_driver_initialized(),
            "debugger": ctx.get_debugger_address(),
            "devtools_active_port_file": {"path": port_file, "port": port_val, "exists": port_val is not None},
            "devtools_http_version": devtools_http,
            "context_state": {
                "driver_initialized": ctx.is_driver_initialized(),
                "window_ready": ctx.is_window_ready(),
                "debugger_address": ctx.get_debugger_address(),
                "process_tag": ctx.process_tag,
            }
        }

        snapshot = (_make_page_snapshot()
                    if ctx.is_driver_initialized()
                    else {"url": None, "title": None, "html": "", "truncated": False})
        return json.dumps({"ok": True, "diagnostics": diagnostics, "snapshot": snapshot})

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": {"summary": diag}})

async def debug_element(
    selector,
    selector_type,
    timeout,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_html_length=5000,
    include_html=True,
):
    """
    Debug an element on the page.

    Args:
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait for element
        iframe_selector: Optional iframe selector
        iframe_selector_type: Iframe selector type
        shadow_root_selector: Optional shadow root selector
        shadow_root_selector_type: Shadow root selector type
        max_html_length: Maximum length of outerHTML to return (default: 5000 chars)
        include_html: Whether to include HTML in response (default: True)

    Returns:
        JSON string with debug information
    """
    ctx = get_context()

    try:
        info: Dict[str, Any] = {
            "selector": selector,
            "selector_type": selector_type,
            "exists": False,
            "displayed": None,
            "enabled": None,
            "clickable": None,
            "rect": None,
            "outerHTML": None,
            "truncated": False,
            "notes": [],
        }

        try:
            el = retry_op(fn=lambda: find_element(
                driver=ctx.driver,
                selector=selector,
                selector_type=selector_type,
                timeout=int(timeout),
                visible_only=False,
                iframe_selector=iframe_selector,
                iframe_selector_type=iframe_selector_type,
                shadow_root_selector=shadow_root_selector,
                shadow_root_selector_type=shadow_root_selector_type,
                stay_in_context=True,
            ))
            info["exists"] = True

            try:
                info["displayed"] = bool(el.is_displayed())
            except Exception:
                info["displayed"] = None
            try:
                info["enabled"] = bool(el.is_enabled())
            except Exception:
                info["enabled"] = None

            try:
                _wait_clickable_element(el=el, driver=ctx.driver, timeout=timeout)
                info["clickable"] = True
            except Exception:
                info["clickable"] = False

            try:
                r = el.rect
                info["rect"] = {
                    "x": r.get("x"),
                    "y": r.get("y"),
                    "width": r.get("width"),
                    "height": r.get("height"),
                }
            except Exception:
                info["rect"] = None

            # Get HTML if requested
            if include_html:
                try:
                    html = ctx.driver.execute_script("return arguments[0].outerHTML;", el)
                    # Clean invalid characters
                    html = html.replace('\x00', '').encode('utf-8', errors='ignore').decode('utf-8')

                    # Truncate if too large
                    full_length = len(html)
                    if max_html_length and len(html) > max_html_length:
                        info["outerHTML"] = html[:max_html_length]
                        info["truncated"] = True
                        info["full_html_length"] = full_length
                        info["notes"].append(f"HTML truncated from {full_length} to {max_html_length} chars")
                    else:
                        info["outerHTML"] = html
                        info["truncated"] = False
                except Exception as e:
                    info["outerHTML"] = None
                    info["notes"].append(f"Could not get HTML: {str(e)}")
            else:
                info["notes"].append("HTML omitted (include_html=False)")

        except TimeoutException:
            info["notes"].append("Element not found within timeout")
        except Exception as e:
            info["notes"].append(f"Error while probing element: {repr(e)}")

        snapshot = _make_page_snapshot()
        return json.dumps({"ok": True, "debug": info, "snapshot": snapshot})

    except Exception as e:
        diag = collect_diagnostics(driver=ctx.driver, exc=e, config=ctx.config)
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

    finally:
        try:
            if ctx.is_driver_initialized():
                ctx.driver.switch_to.default_content()
        except Exception:
            pass


__all__ = ['get_debug_diagnostics_info', 'debug_element']
