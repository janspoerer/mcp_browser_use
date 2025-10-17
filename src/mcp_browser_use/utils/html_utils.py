"""HTML processing and cleaning utilities.

This module consolidates HTML cleaning functions from both cleaners.py and helpers.py.
"""

import re
from typing import Tuple, Dict, Optional, Sequence, Pattern, Union
from bs4 import BeautifulSoup, Comment


# Re-export from cleaners.py
from ..cleaners import (
    NOISE_ID_CLASS_PAT,
    HIDDEN_CLASS_PAT,
    approx_token_count,
    CDN_HOST_PATS,
    _build_cdn_pats,
    _is_cdn_url,
    _filter_srcset,
    basic_prune,
    extract_outline,
)


def remove_unwanted_tags(html_content: str, aggressive: bool = False) -> str:
    """
    Remove unwanted tags from HTML.

    Args:
        html_content: Raw HTML string
        aggressive: If True, removes additional tags like svg, iframe, comments, headers, footers, navigation

    Returns:
        Cleaned HTML string with whitespace collapsed
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Always remove these
    basic_removals = ['script', 'style', 'meta', 'link', 'noscript']

    # Aggressive mode removes more
    if aggressive:
        basic_removals.extend([
            'svg', 'iframe', 'canvas', 'form'
        ])

    for tag in soup.find_all(basic_removals):
        tag.extract()

    # Remove HTML comments in aggressive mode
    if aggressive:
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove hidden inputs
        for hidden_input in soup.find_all('input', {'type': 'hidden'}):
            hidden_input.extract()

        # Remove headers, footers, and navigation (huge space savers for e-commerce sites)
        for tag in soup.find_all(['header', 'footer', 'nav']):
            tag.extract()

        # Remove common navigation/menu class patterns (but be more selective)
        for tag in soup.find_all(class_=lambda c: c and any(x in str(c).lower() for x in ['-header', '-footer', '-navigation', 'nav-main', '-menu', '-flyout', '-dropdown', 'breadcrumb'])):
            tag.extract()

        # Remove all attributes except critical ones for product data
        critical_attrs = {'href', 'src', 'alt', 'title', 'class', 'id', 'type', 'name', 'value'}
        for tag in soup.find_all(True):
            # Remove all non-critical attributes
            attrs_to_remove = [attr for attr in tag.attrs if attr not in critical_attrs]
            for attr in attrs_to_remove:
                del tag[attr]

            # Also remove data-* attributes (often just for JS functionality)
            data_attrs = [attr for attr in tag.attrs if attr.startswith('data-')]
            for attr in data_attrs:
                del tag[attr]

        # Remove empty tags after cleaning, but preserve structural tags like body, html, divs with children
        # Only remove leaf nodes that are empty
        for tag in soup.find_all():
            if tag.name not in ['html', 'head', 'body'] and not tag.get_text(strip=True) and not tag.find_all(['img', 'input', 'br', 'hr', 'a']):
                tag.extract()

    return str(soup)


def get_cleaned_html(driver, aggressive: bool = False) -> str:
    """
    Get cleaned HTML from the current page.

    Args:
        driver: Selenium WebDriver instance
        aggressive: If True, applies aggressive HTML cleaning

    Returns:
        Cleaned HTML string
    """
    html_content = driver.page_source
    return remove_unwanted_tags(html_content, aggressive=aggressive)


__all__ = [
    # From cleaners.py
    'NOISE_ID_CLASS_PAT',
    'HIDDEN_CLASS_PAT',
    'approx_token_count',
    'CDN_HOST_PATS',
    '_build_cdn_pats',
    '_is_cdn_url',
    '_filter_srcset',
    'basic_prune',
    'extract_outline',
    # From helpers.py
    'remove_unwanted_tags',
    'get_cleaned_html',
]
