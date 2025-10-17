"""Diagnostics and debugging information."""

import os
import json
import traceback
from typing import Optional


def collect_diagnostics(driver: Optional[webdriver.Chrome], exc: Optional[Exception], config: dict) -> str:
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
#endregion

#region Tool Implementation
async def start_browser():
    owner = ensure_process_tag()
    try:
        _ensure_driver_and_window()

        if DRIVER is None:
            diag = collect_diagnostics(None, None, get_env_config())
            if isinstance(diag, str):
                    diag = {"summary": diag}
            return json.dumps({
                "ok": False,
                "error": "driver_not_initialized",
                "driver_initialized": False,
                "debugger": (
                    f"{DEBUGGER_HOST}:{DEBUGGER_PORT}"
                    if (DEBUGGER_HOST and DEBUGGER_PORT) else None
                ),
                "diagnostics": diag,
                "message": "Failed to attach/launch a debuggable Chrome session."
            })
        
        handle = getattr(DRIVER, "current_window_handle", None)
        try:
            _close_extra_blank_windows_safe(DRIVER, exclude_handles={handle} if handle else None)
        except Exception:
            pass

        # Wait until the page is ready. Get a snapshot.
        _wait_document_ready(timeout=5.0)
        try:
            snapshot = _make_page_snapshot()
        except Exception:
            snapshot = None
        snapshot = snapshot or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }

        msg = ( # Human-friendly message
            f"Browser session created successfully. "
            f"Session ID: {owner}. "
            f"Current URL: {snapshot.get('url') or 'about:blank'}"
        )

        payload = {
            "ok": True,
            "session_id": owner,
            "debugger": f"{DEBUGGER_HOST}:{DEBUGGER_PORT}" if (DEBUGGER_HOST and DEBUGGER_PORT) else None,
            "lock_ttl_seconds": ACTION_LOCK_TTL_SECS,
            "snapshot": snapshot,
            "message": msg,
        }
    
        return json.dumps(payload)
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot() or {
            "url": "about:blank",
            "title": "",
            "html": "",
            "truncated": False,
        }
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    
# helpers/__init__.py

async def navigate_to_url(
    url: str,
    wait_for: str = "load",     # "load" or "complete"
    timeout_sec: int = 30,
) -> str:
    """
    Navigate to a URL and return JSON with a raw snapshot.
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        DRIVER.get(url)

        # DOM readiness
        try:
            _wait_document_ready(timeout=min(max(timeout_sec, 0), 60))
        except Exception:
            pass

        if (wait_for or "load").lower() == "complete":
            try:
                WebDriverWait(DRIVER, timeout_sec).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                pass

        snapshot = _make_page_snapshot()
        return json.dumps({"ok": True, "action": "navigate", "url": url, "snapshot": snapshot})
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def fill_text(
    selector,
    text,
    selector_type,
    clear_first,
    timeout,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_snapshot_chars=5000,
    aggressive_cleaning=False,
    offset_chars=0,
):
    try:

        el = retry_op(lambda: find_element(
            DRIVER,
            selector,
            selector_type,
            timeout=int(timeout),
            visible_only=True,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
            shadow_root_selector=shadow_root_selector,
            shadow_root_selector_type=shadow_root_selector_type,
            stay_in_context=True,
        ))

        if clear_first:
            try:
                el.clear()
            except Exception:
                pass
        el.send_keys(text)
        _wait_document_ready(timeout=5.0)

        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": True, "action": "fill_text", "selector": selector, "snapshot": snapshot})
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

async def click_element(
    selector,
    selector_type,
    timeout,
    force_js,
    iframe_selector,
    iframe_selector_type,
    shadow_root_selector,
    shadow_root_selector_type,
    max_snapshot_chars=5000,
    aggressive_cleaning=False,
    offset_chars=0,
) -> str:
    try:

        el = retry_op(lambda: find_element(
            DRIVER,
            selector,
            selector_type,
            timeout=int(timeout),
            visible_only=True,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
            shadow_root_selector=shadow_root_selector,
            shadow_root_selector_type=shadow_root_selector_type,
            stay_in_context=True,
        ))

        _wait_clickable_element(el, timeout=timeout)

        if force_js:
            DRIVER.execute_script("arguments[0].click();", el)
        else:
            try:
                el.click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                el = retry_op(lambda: find_element(
                    DRIVER, selector, selector_type, timeout=int(timeout),
                    visible_only=True,
                    iframe_selector=iframe_selector, iframe_selector_type=iframe_selector_type,
                    shadow_root_selector=shadow_root_selector, shadow_root_selector_type=shadow_root_selector_type,
                    stay_in_context=True,
                ))
                DRIVER.execute_script("arguments[0].click();", el)

        _wait_document_ready(timeout=10.0)

        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({
            "ok": True,
            "action": "click",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })
    except TimeoutException:
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({
            "ok": False,
            "error": "timeout",
            "selector": selector,
            "selector_type": selector_type,
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

async def take_screenshot(screenshot_path, return_base64, return_snapshot, thumbnail_width=None) -> str:
    """
    Take a screenshot of the current page.

    Args:
        screenshot_path: Optional path to save the full screenshot
        return_base64: Whether to return base64 encoded image
        return_snapshot: Whether to return page HTML snapshot
        thumbnail_width: Optional width in pixels for thumbnail (requires return_base64=True)
                        Default: 200px if return_base64 is True (accounts for MCP overhead)

    Returns:
        JSON string with ok status, saved path, optional base64 thumbnail, and snapshot
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        # Get full screenshot
        png_bytes = DRIVER.get_screenshot_as_png()

        # Save full screenshot to disk if path provided
        if screenshot_path:
            with open(screenshot_path, "wb") as f:
                f.write(png_bytes)

        payload = {"ok": True, "saved_to": screenshot_path}

        # Handle base64 return with thumbnail
        if return_base64:
            # Default thumbnail width to 200px to account for MCP protocol overhead (~3x)
            # 200px thumbnail = ~6K tokens, plus MCP overhead = ~18K total (under 25K limit)
            if thumbnail_width is None:
                thumbnail_width = 200

            # Validate thumbnail width
            if thumbnail_width < 50:
                return json.dumps({
                    "ok": False,
                    "error": "thumbnail_width_too_small",
                    "message": "thumbnail_width must be at least 50 pixels",
                    "min_width": 50,
                })

            try:
                from PIL import Image
            except ImportError:
                return json.dumps({
                    "ok": False,
                    "error": "pillow_not_installed",
                    "message": "Pillow is required for thumbnails. Install with: pip install Pillow",
                })

            try:
                # Create thumbnail
                img = Image.open(io.BytesIO(png_bytes))
                original_size = img.size

                # Calculate thumbnail dimensions maintaining aspect ratio
                aspect_ratio = img.height / img.width
                thumb_height = int(thumbnail_width * aspect_ratio)

                # Resize to thumbnail
                img.thumbnail((thumbnail_width, thumb_height), Image.Resampling.LANCZOS)

                # Encode thumbnail to base64
                thumb_buffer = io.BytesIO()
                img.save(thumb_buffer, format='PNG', optimize=True)
                thumb_b64 = base64.b64encode(thumb_buffer.getvalue()).decode('utf-8')

                payload["base64"] = thumb_b64
                payload["thumbnail_width"] = thumbnail_width
                payload["thumbnail_height"] = img.height
                payload["original_width"] = original_size[0]
                payload["original_height"] = original_size[1]
                payload["message"] = f"Screenshot saved (thumbnail: {thumbnail_width}x{img.height}px, original: {original_size[0]}x{original_size[1]}px)"

            except Exception as thumb_error:
                # Thumbnail failed but full screenshot was saved
                return json.dumps({
                    "ok": True,
                    "saved_to": screenshot_path,
                    "thumbnail_error": str(thumb_error),
                    "message": "Full screenshot saved, but thumbnail generation failed"
                })

        if return_snapshot:
            payload["snapshot"] = _make_page_snapshot()
        else:
            payload["snapshot"] = "Omitted to save tokens."

        return json.dumps(payload)
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        if return_snapshot:
            snapshot = _make_page_snapshot()
        else:
            snapshot = "Omitted to save tokens."
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def get_debug_diagnostics_info() -> str:
    try:
        cfg = get_env_config()
        udir = cfg.get("user_data_dir")
        port_file = str(Path(udir) / "DevToolsActivePort") if udir else None

        # Read DevToolsActivePort without relying on helpers
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

        diag_summary = collect_diagnostics(DRIVER, None, cfg)  # string
        diagnostics = {
            "summary": diag_summary,
            "driver_initialized": bool(DRIVER),
            "debugger": f"{DEBUGGER_HOST}:{DEBUGGER_PORT}" if (DEBUGGER_HOST and DEBUGGER_PORT) else None,
            "devtools_active_port_file": {"path": port_file, "port": port_val, "exists": port_val is not None},
            "devtools_http_version": devtools_http,
        }

        snapshot = (_make_page_snapshot()
                    if DRIVER
                    else {"url": None, "title": None, "html": "", "truncated": False})
        return json.dumps({"ok": True, "diagnostics": diagnostics, "snapshot": snapshot})
    except Exception as e:

        diag = collect_diagnostics(DRIVER, e, get_env_config())
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
            el = retry_op(lambda: find_element(
                DRIVER,
                selector,
                selector_type,
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
                _wait_clickable_element(el, timeout=timeout)
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
                    html = DRIVER.execute_script("return arguments[0].outerHTML;", el)
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
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

async def unlock_browser():
    owner = ensure_process_tag()
    released = _release_action_lock(owner)
    return json.dumps({"ok": True, "released": bool(released)})

async def close_browser() -> str:
    try:
        closed = close_singleton_window()
        msg = "Browser window closed successfully" if closed else "No window to close"
        return json.dumps({"ok": True, "closed": bool(closed), "message": msg})
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag})

async def force_close_all_chrome() -> str:
    """
    Force close all Chrome processes, quit driver, and clean up all state.
    Use this to recover from stuck Chrome instances or when normal close_browser fails.
    """
    global DRIVER, DEBUGGER_HOST, DEBUGGER_PORT, TARGET_ID, WINDOW_ID, MY_TAG

    killed_processes = []
    errors = []

    try:
        # 1. Try to quit the Selenium driver gracefully
        if DRIVER is not None:
            try:
                DRIVER.quit()
            except Exception as e:
                errors.append(f"Driver quit failed: {e}")
            DRIVER = None

        # 2. Get config to find which Chrome processes to kill
        try:
            cfg = get_env_config()
            user_data_dir = cfg.get("user_data_dir", "")
        except Exception as e:
            user_data_dir = ""
            errors.append(f"Could not get config: {e}")

        # 3. Kill all Chrome processes using the MCP profile
        # First, try targeted kill based on user_data_dir
        chrome_processes_found = []
        for p in psutil.process_iter(["name", "cmdline", "pid"]):
            try:
                if not p.info.get("name"):
                    continue
                if "chrome" not in p.info["name"].lower():
                    continue
                chrome_processes_found.append(p)

                # If we have a user_data_dir, check if this process matches
                if user_data_dir:
                    cmd = p.info.get("cmdline")
                    if cmd:
                        # Check if any argument contains our user_data_dir path
                        # Use 'in' check because paths might have different separators or be normalized differently
                        user_data_normalized = user_data_dir.replace("\\", "/").lower()
                        for arg in cmd:
                            if arg and "--user-data-dir" in arg:
                                arg_normalized = arg.replace("\\", "/").lower()
                                if user_data_normalized in arg_normalized:
                                    p.kill()
                                    killed_processes.append(p.info["pid"])
                                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                errors.append(f"Could not access process: {e}")

        # 4. Fallback: If no Chrome processes were killed but some were found, kill them all
        # This ensures we don't leave zombie Chrome processes
        if not killed_processes and chrome_processes_found:
            for p in chrome_processes_found:
                try:
                    p.kill()
                    killed_processes.append(p.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    errors.append(f"Could not kill process in fallback: {e}")

        # 5. Clean up global state
        DEBUGGER_HOST = None
        DEBUGGER_PORT = None
        TARGET_ID = None
        WINDOW_ID = None

        # 6. Release locks
        try:
            if MY_TAG:
                _release_action_lock(MY_TAG)
        except Exception as e:
            errors.append(f"Lock release failed: {e}")

        # 7. Clean up lock files
        try:
            if user_data_dir:
                lock_dir = Path(LOCK_DIR)
                # lock_dir = Path(tempfile.gettempdir()) / "mcp_browser_locks"
                if lock_dir.exists():
                    profile_key_val = profile_key(cfg) if cfg else ""
                    for lock_file in lock_dir.glob(f"*{profile_key_val}*"):
                        try:
                            lock_file.unlink()
                        except Exception:
                            pass
        except Exception as e:
            errors.append(f"Lock file cleanup failed: {e}")

        msg = f"Force closed Chrome. Killed {len(killed_processes)} processes."
        if errors:
            msg += f" Errors: {'; '.join(errors)}"

        return json.dumps({
            "ok": True,
            "killed_processes": killed_processes,
            "errors": errors,
            "message": msg
        })

    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": str(e),
            "killed_processes": killed_processes,
            "errors": errors
        })

async def scroll(x: int, y: int, max_snapshot_chars=0, aggressive_cleaning=False, offset_chars=0) -> str:
    """
    Scroll the page by the specified pixel amounts.

    Args:
        x: Horizontal scroll amount in pixels (positive = right, negative = left)
        y: Vertical scroll amount in pixels (positive = down, negative = up)
        max_snapshot_chars: Maximum HTML characters to return (default: 0 to save context)
        aggressive_cleaning: Whether to apply aggressive HTML cleaning
        offset_chars: Number of characters to skip from start of HTML (default: 0)

    Returns:
        JSON string with ok status, action, scroll amounts, and page snapshot
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        DRIVER.execute_script(f"window.scrollBy({int(x)}, {int(y)});")
        time.sleep(0.3)  # Brief pause to allow scroll to complete

        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({
            "ok": True,
            "action": "scroll",
            "x": int(x),
            "y": int(y),
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot(max_snapshot_chars, aggressive_cleaning, offset_chars)
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def send_keys(
    key: str,
    selector: Optional[str] = None,
    selector_type: str = "css",
    timeout: float = 10.0,
) -> str:
    """
    Send keyboard keys to an element or to the active element.

    Args:
        key: Key to send (ENTER, TAB, ESCAPE, ARROW_DOWN, etc.)
        selector: Optional CSS selector, XPath, or ID of element to send keys to
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait for element in seconds

    Returns:
        JSON string with ok status, action, key sent, and page snapshot
    """
    try:
        from selenium.webdriver.common.keys import Keys

        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        # Map string key names to Selenium Keys
        key_mapping = {
            "ENTER": Keys.ENTER,
            "RETURN": Keys.RETURN,
            "TAB": Keys.TAB,
            "ESCAPE": Keys.ESCAPE,
            "ESC": Keys.ESCAPE,
            "SPACE": Keys.SPACE,
            "BACKSPACE": Keys.BACKSPACE,
            "DELETE": Keys.DELETE,
            "ARROW_UP": Keys.ARROW_UP,
            "ARROW_DOWN": Keys.ARROW_DOWN,
            "ARROW_LEFT": Keys.ARROW_LEFT,
            "ARROW_RIGHT": Keys.ARROW_RIGHT,
            "PAGE_UP": Keys.PAGE_UP,
            "PAGE_DOWN": Keys.PAGE_DOWN,
            "HOME": Keys.HOME,
            "END": Keys.END,
            "F1": Keys.F1,
            "F2": Keys.F2,
            "F3": Keys.F3,
            "F4": Keys.F4,
            "F5": Keys.F5,
            "F6": Keys.F6,
            "F7": Keys.F7,
            "F8": Keys.F8,
            "F9": Keys.F9,
            "F10": Keys.F10,
            "F11": Keys.F11,
            "F12": Keys.F12,
        }

        selenium_key = key_mapping.get(key.upper(), key)

        if selector:
            # Send keys to specific element
            el = retry_op(lambda: find_element(
                DRIVER,
                selector,
                selector_type,
                timeout=int(timeout),
                visible_only=True,
            ))
            el.send_keys(selenium_key)
        else:
            # Send keys to active element (usually body or focused element)
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(DRIVER).send_keys(selenium_key).perform()

        time.sleep(0.2)  # Brief pause
        snapshot = _make_page_snapshot()

        return json.dumps({
            "ok": True,
            "action": "send_keys",
            "key": key,
            "selector": selector,
            "snapshot": snapshot,
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})

async def wait_for_element(
    selector: str,
    selector_type: str = "css",
    timeout: float = 10.0,
    condition: str = "visible",
    iframe_selector: Optional[str] = None,
    iframe_selector_type: str = "css",
) -> str:
    """
    Wait for an element to meet a specific condition.

    Args:
        selector: CSS selector, XPath, or ID of the element
        selector_type: Type of selector (css, xpath, id)
        timeout: Maximum time to wait in seconds
        condition: Condition to wait for - 'present', 'visible', or 'clickable'
        iframe_selector: Optional selector for iframe containing the element
        iframe_selector_type: Selector type for the iframe

    Returns:
        JSON string with ok status, element found status, and page snapshot
    """
    try:
        if DRIVER is None:
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        visible_only = condition in ("visible", "clickable")

        el = find_element(
            DRIVER,
            selector,
            selector_type,
            timeout=int(timeout),
            visible_only=visible_only,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_selector_type,
        )

        if condition == "clickable":
            _wait_clickable_element(el, timeout=timeout)

        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": True,
            "action": "wait_for_element",
            "selector": selector,
            "condition": condition,
            "found": True,
            "snapshot": snapshot,
            "message": f"Element '{selector}' is now {condition}"
        })
    except TimeoutException:
        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": False,
            "error": "timeout",
            "selector": selector,
            "condition": condition,
            "found": False,
            "snapshot": snapshot,
            "message": f"Element '{selector}' did not become {condition} within {timeout}s"
        })
    except Exception as e:
        diag = collect_diagnostics(DRIVER, e, get_env_config())
        snapshot = _make_page_snapshot()
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})
    finally:
        try:
            if DRIVER is not None:
                DRIVER.switch_to.default_content()
        except Exception:
            pass

#endregion


#region
async def get_current_page_meta():
    """
    Get current page metadata from the active window/tab.

    Returns:
        Dict[str, Optional[str]]: A metadata dictionary with keys such as:
            - "url": The current page URL, or None if not available.
            - "title": The current document.title, or None.
            - "window_tag": An implementation-specific identifier for the window/tab.
    """
    try:
        url = DRIVER.current_url if DRIVER else None
    except Exception:
        url = None
    try:
        title = DRIVER.title if DRIVER else None
    except Exception:
        title = None
    try:
        window_tag = ensure_process_tag()
    except Exception:
        window_tag = None
    return {"url": url, "title": title, "window_tag": window_tag}
#endregion

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
