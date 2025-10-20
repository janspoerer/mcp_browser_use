"""Screenshot capture tool implementations."""

import io
import json
import base64
from typing import Optional
from ..context import get_context
from ..utils.diagnostics import collect_diagnostics
from ..actions.screenshots import _make_page_snapshot


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
    ctx = get_context()

    try:
        if not ctx.is_driver_initialized():
            return json.dumps({"ok": False, "error": "driver_not_initialized"})

        # Get full screenshot
        png_bytes = ctx.driver.get_screenshot_as_png()

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
        diag = collect_diagnostics(ctx.driver, e, ctx.config)
        if return_snapshot:
            snapshot = _make_page_snapshot()
        else:
            snapshot = "Omitted to save tokens."
        return json.dumps({"ok": False, "error": str(e), "diagnostics": diag, "snapshot": snapshot})


__all__ = ['take_screenshot']
