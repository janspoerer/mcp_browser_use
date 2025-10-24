"""Element extraction functionality for fine-grained data collection."""

import json
import re
from typing import Optional, List, Dict, Any
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from ..context import get_context
from .elements import find_element, get_by_selector
from .screenshots import _make_page_snapshot


async def extract_elements(
    selectors: Optional[List[Dict[str, str]]] = None,
    container_selector: Optional[str] = None,
    fields: Optional[List[Dict[str, str]]] = None,
    selector_type: str = "css",
    wait_for_visible: bool = False,
    timeout: int = 10,
    max_items: Optional[int] = None,
    discover_containers: bool = False,
) -> str:
    """
    Extract content from specific elements on the current page.

    Supports two extraction modes:

    MODE 1: Simple extraction (using 'selectors' parameter)
    - Extract individual elements with CSS/XPath
    - Returns list of extracted elements

    MODE 2: Structured extraction (using 'container_selector' + 'fields' parameters)
    - Find multiple containers (e.g., product items)
    - Extract named fields from each container
    - Support attribute extraction and regex cleaning
    - Returns array of structured objects

    Args:
        selectors: [MODE 1] Optional list of selector specifications. Each specification is a dict:
            {
                "selector": str,           # The CSS selector or XPath expression
                "type": str,               # "css" or "xpath" (default: "css")
                "format": str,             # "html" or "text" (default: "html")
                "name": str,               # Optional: field name for the result
                "iframe_selector": str,    # Optional: selector for parent iframe
                "iframe_type": str,        # Optional: "css" or "xpath" for iframe
                "shadow_root_selector": str,  # Optional: selector for shadow root host
                "shadow_root_type": str,   # Optional: "css" or "xpath" for shadow root
            }

        container_selector: [MODE 2] CSS or XPath selector for container elements
        fields: [MODE 2] List of field extractors, each with:
            {
                "field_name": str,         # Output field name (e.g., "price_net")
                "selector": str,           # CSS or XPath relative to container
                "selector_type": str,      # "css" or "xpath" (default: "css")
                "attribute": str,          # Optional: extract attribute instead of text (e.g., "href")
                "regex": str,              # Optional: regex pattern to extract/clean value
                "fallback": str            # Optional: fallback value if extraction fails
            }
        selector_type: [MODE 2] Default selector type for container ("css" or "xpath")
        wait_for_visible: [MODE 2] Wait for containers to be visible
        timeout: [MODE 2] Timeout in seconds (default: 10s)
        max_items: [MODE 2] Limit number of containers to extract (None = all).
                  Useful for testing selectors and preventing token explosions.
                  Recommended: 10 for testing, 50-100 for production.
        discover_containers: [MODE 2] If True, returns container analysis instead of extraction.
                            Use this to explore page structure and find correct selectors.
                            Fast (~5s) and lightweight (~1K tokens).

    Returns:
        JSON string with structure:

        MODE 1 (simple):
        {
            "ok": bool,
            "mode": "simple",
            "extracted_elements": [{selector, found, content, ...}, ...],
            "snapshot": {...}
        }

        MODE 2 (structured):
        {
            "ok": bool,
            "mode": "structured",
            "items": [{field_name: value, ...}, ...],
            "count": int,
            "snapshot": {...}
        }

    Examples:
        # MODE 1: Simple extraction
        selectors = [
            {"selector": "span.price", "type": "css", "format": "text", "name": "price"},
            {"selector": "div.stock-info", "type": "css", "format": "html"}
        ]

        # MODE 2: Structured extraction (products on a listing page)
        container_selector = "article.product-item"
        fields = [
            {"field_name": "product_name", "selector": "h3.title", "selector_type": "css"},
            {"field_name": "mpn", "selector": "span[data-mpn]", "attribute": "data-mpn"},
            {"field_name": "price_brutto", "selector": ".price", "regex": r"[0-9,.]+"},
            {"field_name": "url", "selector": "a.product-link", "attribute": "href"}
        ]
    """
    ctx = get_context()

    # Determine extraction mode
    if container_selector:
        if discover_containers:
            # DISCOVERY MODE: Analyze containers without extracting fields
            discovery = await _discover_containers(
                container_selector=container_selector,
                selector_type=selector_type,
                timeout=min(timeout, 5)  # Cap at 5s for fast discovery
            )
            snapshot = _make_page_snapshot()
            return json.dumps({
                "ok": True,
                "mode": "discovery",
                **discovery,
                "snapshot": snapshot
            })
        elif fields:
            # MODE 2: Structured extraction
            items = await _extract_structured(
                container_selector=container_selector,
                fields=fields,
                selector_type=selector_type,
                wait_for_visible=wait_for_visible,
                timeout=timeout,
                max_items=max_items
            )
            snapshot = _make_page_snapshot()
            return json.dumps({
                "ok": True,
                "mode": "structured",
                "items": items,
                "count": len(items),
                "snapshot": snapshot
            })
        else:
            # Container specified but no fields - treat as discovery
            discovery = await _discover_containers(
                container_selector=container_selector,
                selector_type=selector_type,
                timeout=min(timeout, 5)
            )
            snapshot = _make_page_snapshot()
            return json.dumps({
                "ok": True,
                "mode": "discovery",
                **discovery,
                "snapshot": snapshot
            })
    else:
        # MODE 1: Simple extraction (existing behavior)
        extracted_results: List[Dict[str, Any]] = []
        if selectors:
            for spec in selectors:
                result = await _extract_single_element(spec)
                extracted_results.append(result)

        snapshot = _make_page_snapshot()
        return json.dumps({
            "ok": True,
            "mode": "simple",
            "extracted_elements": extracted_results,
            "snapshot": snapshot
        })


async def _discover_containers(
    container_selector: str,
    selector_type: Optional[str] = None,
    timeout: int = 5,
) -> Dict[str, Any]:
    """
    Discover and analyze containers without extracting fields.

    Returns metadata about matching containers for agent exploration.

    Args:
        container_selector: Selector for container elements
        selector_type: Type of selector (auto-detects if None)
        timeout: Timeout in seconds (default: 5s for fast discovery)

    Returns:
        Dictionary with discovered_containers info
    """
    ctx = get_context()

    # Auto-detect selector type
    if selector_type is None:
        if container_selector.startswith('//') or container_selector.startswith('/'):
            selector_type = "xpath"
        else:
            selector_type = "css"

    try:
        by_type = get_by_selector(selector_type)
        if not by_type:
            return {
                "discovered_containers": {
                    "selector": container_selector,
                    "selector_type": selector_type,
                    "count": 0,
                    "error": f"Invalid selector_type: {selector_type}"
                }
            }

        # Quick check with short timeout
        try:
            WebDriverWait(ctx.driver, timeout).until(
                EC.presence_of_element_located((by_type, container_selector))
            )
        except TimeoutException:
            return {
                "discovered_containers": {
                    "selector": container_selector,
                    "selector_type": selector_type,
                    "count": 0,
                    "error": f"No containers found within {timeout}s timeout"
                }
            }

        # Find all containers
        containers = ctx.driver.find_elements(by_type, container_selector)
        count = len(containers)

        if count == 0:
            return {
                "discovered_containers": {
                    "selector": container_selector,
                    "selector_type": selector_type,
                    "count": 0,
                    "error": "Selector matched but no elements found"
                }
            }

        # Analyze first container as sample
        first_container = containers[0]

        # Get sample HTML (truncated)
        sample_html = ctx.driver.execute_script(
            "return arguments[0].outerHTML;",
            first_container
        )
        sample_html = sample_html[:500] + ("..." if len(sample_html) > 500 else "")

        # Get sample text
        sample_text = ctx.driver.execute_script(
            "return arguments[0].textContent;",
            first_container
        )
        if sample_text:
            sample_text = ' '.join(sample_text.split())  # Normalize whitespace
            sample_text = sample_text[:300] + ("..." if len(sample_text) > 300 else "")
        else:
            sample_text = ""

        # Get common attributes
        attrs = first_container.get_property('attributes')
        common_attributes = [attr['name'] for attr in attrs] if attrs else []

        # Analyze common child elements (helpful for field extraction)
        common_child_selectors = _analyze_child_elements(first_container, ctx)

        return {
            "discovered_containers": {
                "selector": container_selector,
                "selector_type": selector_type,
                "count": count,
                "sample_html": sample_html,
                "sample_text": sample_text,
                "common_attributes": common_attributes,
                "common_child_selectors": common_child_selectors,
                "recommendation": (
                    f"Found {count} containers. "
                    f"Use max_items=10 to test extraction on first 10 items."
                )
            }
        }

    except Exception as e:
        return {
            "discovered_containers": {
                "selector": container_selector,
                "selector_type": selector_type,
                "count": 0,
                "error": f"Discovery failed: {str(e)}"
            }
        }


def _analyze_child_elements(container, ctx) -> List[Dict[str, Any]]:
    """
    Analyze common child elements within a container.

    Returns list of common child selector patterns found in the container.
    Helps agents understand the structure for field extraction.
    """
    try:
        # Common selector patterns to check
        patterns = [
            # Headings
            "h1", "h2", "h3", "h4", "h5", "h6",
            # Common elements
            "a", "span", "div", "p", "img",
            # Common class patterns
            "[class*='price']", "[class*='title']", "[class*='name']",
            "[class*='stock']", "[class*='availability']", "[class*='description']",
            # Data attributes
            "[data-price]", "[data-id]", "[data-product]", "[data-mpn]"
        ]

        child_info = []
        for pattern in patterns:
            try:
                elements = container.find_elements(By.CSS_SELECTOR, pattern)
                if elements:
                    # Get sample text from first element
                    sample = None
                    try:
                        text = elements[0].text
                        if text:
                            sample = text[:50] if len(text) > 50 else text
                    except:
                        pass

                    child_info.append({
                        "selector": pattern,
                        "count_per_container": len(elements),
                        "sample_text": sample
                    })
            except:
                continue

        # Limit to top 10 most relevant
        return child_info[:10]

    except:
        return []


async def _extract_structured(
    container_selector: str,
    fields: List[Dict[str, str]],
    selector_type: Optional[str] = None,
    wait_for_visible: bool = False,
    timeout: int = 10,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Extract structured data from multiple containers on the page.

    Args:
        container_selector: Selector for container elements (e.g., product items)
        fields: List of field extractors with field_name, selector, etc.
        selector_type: Type of container_selector ("css" or "xpath").
                      If None, auto-detects from selector syntax:
                      - Starts with // or / -> xpath
                      - Otherwise -> css
        wait_for_visible: Wait for containers to be visible
        timeout: Timeout in seconds

    Returns:
        List of dictionaries, each representing one container's extracted data
    """
    ctx = get_context()
    items = []

    try:
        # Auto-detect selector type if not provided
        if selector_type is None:
            if container_selector.startswith('//') or container_selector.startswith('/'):
                selector_type = "xpath"
            else:
                selector_type = "css"

        # Find all container elements
        by_type = get_by_selector(selector_type)
        if not by_type:
            return [{
                "_error": f"Invalid selector_type: {selector_type}"
            }]

        # Wait for containers to appear
        if wait_for_visible:
            WebDriverWait(ctx.driver, timeout).until(
                EC.visibility_of_element_located((by_type, container_selector))
            )
        else:
            WebDriverWait(ctx.driver, timeout).until(
                EC.presence_of_element_located((by_type, container_selector))
            )

        # Find all containers
        all_containers = ctx.driver.find_elements(by_type, container_selector)
        total_count = len(all_containers)

        # Apply max_items limit if specified
        if max_items is not None and max_items > 0:
            containers = all_containers[:max_items]
            limited = True
        else:
            containers = all_containers
            limited = False

        # Extract fields from each container
        for idx, container in enumerate(containers):
            item = {}
            item["_container_index"] = idx

            for field_spec in fields:
                field_name = field_spec.get("field_name", f"field_{idx}")
                value = _extract_field_from_container(container, field_spec, ctx)
                item[field_name] = value

            items.append(item)

        # Add note if results were limited
        if limited and total_count > len(containers):
            items.append({
                "_note": f"Results limited to first {max_items} items. Total containers available: {total_count}",
                "_limited": True,
                "_extracted_count": len(containers),
                "_total_count": total_count
            })

    except TimeoutException:
        items.append({
            "_error": f"Container not found within {timeout}s timeout",
            "_container_selector": container_selector
        })
    except Exception as e:
        items.append({
            "_error": f"Error during structured extraction: {str(e)}",
            "_container_selector": container_selector
        })

    return items


def _extract_field_from_container(
    container,
    field_spec: Dict[str, str],
    ctx
) -> Any:
    """
    Extract a single field value from a container element.

    Args:
        container: WebElement representing the container
        field_spec: Field extraction specification
        ctx: Browser context

    Returns:
        Extracted and cleaned value, or fallback/None if not found
    """
    selector = field_spec.get("selector", "")
    field_selector_type = field_spec.get("selector_type", "css").lower()
    attribute = field_spec.get("attribute")
    regex_pattern = field_spec.get("regex")
    fallback = field_spec.get("fallback")

    try:
        # Find element within container
        by_type = get_by_selector(field_selector_type)
        if not by_type:
            return fallback or f"Invalid selector_type: {field_selector_type}"

        # Find element relative to container
        element = container.find_element(by_type, selector)

        # Extract value
        if attribute:
            # Extract from attribute
            value = element.get_attribute(attribute)
        else:
            # Extract text content
            value = ctx.driver.execute_script("return arguments[0].textContent;", element)
            if value:
                # Clean and normalize whitespace
                value = value.replace('\x00', '').encode('utf-8', errors='ignore').decode('utf-8')
                value = ' '.join(value.split())

        # Apply regex if specified
        if value and regex_pattern:
            try:
                match = re.search(regex_pattern, value)
                if match:
                    # Return first capturing group if exists, otherwise whole match
                    value = match.group(1) if match.lastindex else match.group(0)
                else:
                    # Regex didn't match, use fallback if available
                    value = fallback if fallback is not None else value
            except re.error:
                # Invalid regex, keep original value
                pass

        return value if value is not None else fallback

    except NoSuchElementException:
        return fallback
    except Exception as e:
        return fallback if fallback is not None else f"Error: {str(e)}"


async def _extract_single_element(spec: Dict[str, str]) -> Dict[str, Any]:
    """
    Extract content from a single element specification.

    Args:
        spec: Selector specification dictionary

    Returns:
        Dictionary with extraction result
    """
    ctx = get_context()

    # Parse specification with defaults
    selector = spec.get("selector")
    selector_type = spec.get("type", "css").lower()
    output_format = spec.get("format", "html").lower()
    field_name = spec.get("name")  # Optional field name
    iframe_selector = spec.get("iframe_selector")
    iframe_type = spec.get("iframe_type", "css")
    shadow_root_selector = spec.get("shadow_root_selector")
    shadow_root_type = spec.get("shadow_root_type", "css")
    timeout = int(spec.get("timeout", 10))

    # Validate inputs
    if not selector:
        result = {
            "selector": selector,
            "selector_type": selector_type,
            "found": False,
            "content": None,
            "format": output_format,
            "error": "No selector provided"
        }
        if field_name:
            result["name"] = field_name
        return result

    if selector_type not in ("css", "xpath"):
        result = {
            "selector": selector,
            "selector_type": selector_type,
            "found": False,
            "content": None,
            "format": output_format,
            "error": f"Invalid selector_type: {selector_type}. Must be 'css' or 'xpath'"
        }
        if field_name:
            result["name"] = field_name
        return result

    if output_format not in ("html", "text"):
        output_format = "html"  # Default fallback

    result = {
        "selector": selector,
        "selector_type": selector_type,
        "found": False,
        "content": None,
        "format": output_format,
        "error": None
    }
    if field_name:
        result["name"] = field_name

    try:
        # Find the element
        element = find_element(
            driver=ctx.driver,
            selector=selector,
            selector_type=selector_type,
            timeout=timeout,
            visible_only=False,
            iframe_selector=iframe_selector,
            iframe_selector_type=iframe_type,
            shadow_root_selector=shadow_root_selector,
            shadow_root_selector_type=shadow_root_type,
            stay_in_context=True,  # Stay in iframe context for extraction
        )

        result["found"] = True

        # Extract content based on format
        if output_format == "html":
            # Get outerHTML
            html = ctx.driver.execute_script("return arguments[0].outerHTML;", element)
            # Clean invalid characters
            html = html.replace('\x00', '').encode('utf-8', errors='ignore').decode('utf-8')
            result["content"] = html
        else:  # text
            # Get textContent (preserves whitespace better than .text property)
            text = ctx.driver.execute_script("return arguments[0].textContent;", element)
            # Clean and normalize
            if text:
                text = text.replace('\x00', '').encode('utf-8', errors='ignore').decode('utf-8')
                # Basic whitespace normalization
                text = ' '.join(text.split())
            result["content"] = text or ""

    except TimeoutException:
        result["error"] = f"Element not found within {timeout}s timeout"
    except NoSuchElementException:
        result["error"] = "Element not found"
    except Exception as e:
        result["error"] = f"Error extracting element: {str(e)}"
    finally:
        # Always switch back to default content
        try:
            if ctx.is_driver_initialized():
                ctx.driver.switch_to.default_content()
        except Exception:
            pass

    return result


__all__ = ['extract_elements']
