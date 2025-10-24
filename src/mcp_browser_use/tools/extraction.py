"""Element extraction tool implementations."""

from typing import Optional, List, Dict
from ..actions.extraction import extract_elements as _extract_elements_action


async def extract_elements(
    selectors: Optional[List[Dict[str, str]]] = None,
    container_selector: Optional[str] = None,
    fields: Optional[List[Dict[str, str]]] = None,
    selector_type: Optional[str] = None,
    wait_for_visible: bool = False,
    timeout: int = 10,
    max_items: Optional[int] = None,
    discover_containers: bool = False,
) -> str:
    """
    Extract content from specific elements on the current page.

    This is a wrapper around the extraction action that provides the tool interface.

    Supports two modes:
    - Simple extraction: Use 'selectors' parameter
    - Structured extraction: Use 'container_selector' + 'fields' parameters
    - Discovery mode: Use 'container_selector' + 'discover_containers=True'

    Args:
        selectors: [MODE 1] Optional list of selector specifications
        container_selector: [MODE 2] CSS or XPath selector for containers
        fields: [MODE 2] List of field extractors with field_name, selector, etc.
        selector_type: [MODE 2] Type of container_selector (auto-detects if None)
        wait_for_visible: [MODE 2] Wait for containers to be visible
        timeout: [MODE 2] Timeout in seconds
        max_items: [MODE 2] Limit number of containers to extract
        discover_containers: [MODE 2] Return container analysis instead of extraction

    Returns:
        JSON string with extraction results and page snapshot.
    """
    return await _extract_elements_action(
        selectors=selectors,
        container_selector=container_selector,
        fields=fields,
        selector_type=selector_type,
        wait_for_visible=wait_for_visible,
        timeout=timeout,
        max_items=max_items,
        discover_containers=discover_containers
    )


__all__ = ['extract_elements']
