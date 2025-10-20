# mcp_browser_use/cleaners.py

import re
from typing import Tuple, Dict, Optional, Sequence, Pattern, Union

NOISE_ID_CLASS_PAT = re.compile(
    r"(gtm|gtag|analytics|ad[s-]?|adslot|sponsor|cookie[-_ ]?banner|chat[-_ ]?widget)",
    re.I
)

HIDDEN_CLASS_PAT = re.compile(r"(sr-only|visually-hidden|offscreen)", re.I)

def approx_token_count(text: str) -> int:
    # Fast heuristic: ~4 chars per token
    return max(0, (len(text) // 4))


# CDN detection and cleanup helpers
CDN_HOST_PATS = [
    re.compile(r"(?:^|\.)cdn(?:[\.-]|$)", re.I),  # matches cdn.*, *.cdn-foo.*, *.cdn.foo.*
    re.compile(r"/cdn/", re.I),                  # handles relative /cdn/... paths
]

def _build_cdn_pats(extra: Optional[Sequence[Union[str, Pattern[str]]]]) -> list[Pattern[str]]:
    pats: list[Pattern[str]] = list(CDN_HOST_PATS)
    for p in extra or []:
        if isinstance(p, str):
            pats.append(re.compile(p, re.I))
        elif hasattr(p, "search"):
            pats.append(p)  # already a compiled regex
    return pats

def _is_cdn_url(url: str, extra_pats=None) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    s = url.strip().strip('\'"')
    # extract from url(...) if style
    s = re.sub(r"^url\((.+?)\)$", r"\1", s).strip('\'"')
    # srcset often has descriptors like "800w" – take only the URL portion
    s = s.split()[0] if s else s

    # support scheme-less //cdn.host
    host, path = "", ""
    try:
        if s.startswith("//"):
            host = s[2:].split("/", 1)[0].lower()
            path = "/" + s[2:].split("/", 1)[1] if "/" in s[2:] else ""
        else:
            from urllib.parse import urlparse
            p = urlparse(s)
            host = (p.netloc or "").lower()
            path = p.path or ""
    except Exception:
        pass

    pats = (extra_pats or []) + CDN_HOST_PATS
    haystacks = [host, path, s]
    return any(p.search(h) for h in haystacks for p in pats)

def _filter_srcset(srcset_val: str, extra_pats=None) -> str | None:
    # Return a cleaned srcset string without CDN candidates, or None if all are removed
    if not srcset_val:
        return None
    pieces = [i.strip() for i in str(srcset_val).split(",") if i.strip()]
    kept = []
    for piece in pieces:
        url = piece.split()[0].strip('\'"')
        if not _is_cdn_url(url, extra_pats):
            kept.append(piece)
    if not kept:
        return None
    return ", ".join(kept)

def _is_button_like(el) -> bool:
    """
    Check if an element should be treated as button-like for class preservation.

    Args:
        el: BeautifulSoup element to check

    Returns:
        bool: True if element is <button>, <input type="button/submit/reset/image">, or role="button"
    """
    try:
        tag = (el.name or "").lower()
    except Exception:
        tag = ""
    if tag == "button":
        return True
    typ = str(el.get("type", "")).lower()
    if tag == "input" and typ in ("button", "submit", "reset", "image"):
        return True
    role = str(el.get("role", "")).lower()
    if role == "button":
        return True
    return False


def _remove_comments(soup, pruned_counts: Dict[str, int]) -> None:
    """
    Remove HTML comments from the document to save tokens.

    Args:
        soup: BeautifulSoup object to modify in-place
        pruned_counts: Dictionary to update with removal counts
    """
    from bs4 import Comment

    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
        pruned_counts["comments_removed"] += 1


def _remove_scripts_and_styles(soup, pruned_counts: Dict[str, int]) -> None:
    """
    Remove non-content tags like scripts, styles, SVG, and non-canonical links.

    Args:
        soup: BeautifulSoup object to modify in-place
        pruned_counts: Dictionary to update with removal counts
    """
    # Remove scripts/styles/noscript/template/svg/canvas/meta/source/track
    for tag_name in ["script", "style", "noscript", "template", "canvas", "svg", "meta", "source", "track"]:
        removed = soup.find_all(tag_name)
        key = tag_name if tag_name in ["script", "style"] else "noise"
        pruned_counts[key] = pruned_counts.get(key, 0) + len(removed)
        for t in removed:
            t.decompose()

    # Remove <link> except canonical (robust to str vs list)
    for link in soup.find_all("link"):
        rel = link.get("rel")
        rels = [s.lower() for s in rel] if isinstance(rel, (list, tuple)) else ([str(rel).lower()] if rel else [])
        if "canonical" in rels:
            continue
        pruned_counts["noise"] += 1
        link.decompose()


def _remove_noise_containers(soup, pruned_counts: Dict[str, int], prune_hidden: bool) -> None:
    """
    Remove ads, trackers, hidden elements, and oversized dropdowns.

    Args:
        soup: BeautifulSoup object to modify in-place
        pruned_counts: Dictionary to update with removal counts
        prune_hidden: If True, remove hidden elements and hidden inputs
    """
    removed_noise = 0
    removed_hidden = 0

    for el in soup.find_all(True):
        if el.attrs is None:
            continue

        idv = el.get("id") or ""
        classes = el.get("class") or []
        classv = " ".join(classes) if isinstance(classes, (list, tuple)) else str(classes)

        aria_hidden = str(el.get("aria-hidden", "")).strip().lower() == "true"
        style_val = el.get("style")

        style_hidden = False
        if isinstance(style_val, str):
            sv = style_val.lower()
            if re.search(r"display\s*:\s*none\b", sv) or re.search(r"visibility\s*:\s*hidden\b", sv):
                style_hidden = True

        hidden_attr = el.has_attr("hidden") or aria_hidden or style_hidden

        # Requires NOISE_ID_CLASS_PAT / HIDDEN_CLASS_PAT to be defined at module scope
        remove_for_noise = bool(NOISE_ID_CLASS_PAT.search(idv) or NOISE_ID_CLASS_PAT.search(classv))
        remove_for_hidden = bool(hidden_attr or HIDDEN_CLASS_PAT.search(classv))

        if remove_for_noise or (prune_hidden and remove_for_hidden):
            if remove_for_noise:
                removed_noise += 1
            if prune_hidden and remove_for_hidden:
                removed_hidden += 1
            el.decompose()

    pruned_counts["noise"] += removed_noise
    pruned_counts["hidden_removed"] += removed_hidden

    # Remove hidden inputs explicitly
    if prune_hidden:
        hidden_inputs_removed = 0
        for inp in soup.find_all("input"):
            typ = str(inp.get("type", "")).lower()
            if typ == "hidden":
                inp.decompose()
                hidden_inputs_removed += 1
        pruned_counts["hidden_removed"] += hidden_inputs_removed

    # Remove large select dropdowns that cause token overflow
    select_removed = 0
    for select in soup.find_all("select"):
        options = select.find_all("option")
        if len(options) > 5:
            select.decompose()
            select_removed += 1
    pruned_counts["noise"] += select_removed

    # Also remove JavaScript dropdown menus with many items
    dropdown_removed = 0
    for dropdown_menu in soup.find_all("div", class_=re.compile(r"dropdown-menu")):
        dropdown_items = dropdown_menu.find_all(class_=re.compile(r"dropdown-item"))
        if len(dropdown_items) > 5:
            dropdown_menu.decompose()
            dropdown_removed += 1
    pruned_counts["noise"] += dropdown_removed


def _clean_cdn_links(
    soup,
    pruned_counts: Dict[str, int],
    cdn_host_patterns: list[str] | None,
    drop_cdn_elements: bool,
) -> None:
    """
    Strip CDN URLs from attributes, inline styles, and text nodes.

    Args:
        soup: BeautifulSoup object to modify in-place
        pruned_counts: Dictionary to update with removal counts
        cdn_host_patterns: Additional CDN pattern strings to match
        drop_cdn_elements: If True, remove entire asset tags with CDN URLs
    """
    cdn_removed = 0
    # Common URL-carrying attributes to inspect
    url_attrs = ("src", "href", "poster", "data-src", "data-lazy", "data-original", "data-lazy-src", "data-srcset")
    asset_tags = {"img", "script", "link", "source", "video", "audio", "track"}

    for el in list(soup.find_all(True)):
        # Clean srcset by filtering out CDN candidates
        if el.has_attr("srcset"):
            cleaned = _filter_srcset(str(el.get("srcset")), cdn_host_patterns)
            original = str(el.get("srcset"))
            if cleaned != original:
                if cleaned:
                    el["srcset"] = cleaned
                else:
                    try:
                        del el.attrs["srcset"]
                    except Exception:
                        pass
                cdn_removed += 1

        # Remove CDN URLs from URL attributes
        for attr in url_attrs:
            if not el.has_attr(attr):
                continue
            val = str(el.get(attr, ""))
            if _is_cdn_url(val, cdn_host_patterns):
                if drop_cdn_elements and el.name in asset_tags:
                    el.decompose()
                    cdn_removed += 1
                    break  # element is gone
                else:
                    try:
                        del el.attrs[attr]
                    except Exception:
                        pass
                    cdn_removed += 1

        # Strip any inline style url(...) pointing to CDNs
        if el.has_attr("style"):
            style_val = str(el["style"])
            # Remove only url(...) tokens that are CDN; keep the rest of the style intact
            def repl(m):
                raw = m.group(1).strip('\'"')
                return "" if _is_cdn_url(raw, cdn_host_patterns) else m.group(0)

            new_style = re.sub(r"url\((.+?)\)", repl, style_val)
            if new_style != style_val:
                # Clean leftover artifacts like empty declarations
                new_style = re.sub(r"\s*;\s*;\s*", ";", new_style).strip(" ;")
                if new_style:
                    el["style"] = new_style
                else:
                    try:
                        del el.attrs["style"]
                    except Exception:
                        pass
                cdn_removed += 1

    pruned_counts["cdn_links_removed"] += cdn_removed

    # Optional: remove plaintext CDN URLs from text nodes
    for t in soup.find_all(string=True):
        new_t = re.sub(r"https?://[^ \t\n\r,]*cdn[^ \t\n\r,]*", "", str(t), flags=re.I)
        if new_t != str(t):
            t.replace_with(new_t)
            pruned_counts["cdn_links_removed"] += 1


def _prune_attributes(soup, pruned_counts: Dict[str, int], prune_classes_except_buttons: bool) -> None:
    """
    Prune non-essential attributes and normalize remaining ones.

    Args:
        soup: BeautifulSoup object to modify in-place
        pruned_counts: Dictionary to update with removal counts
        prune_classes_except_buttons: If True, remove class attributes except from button-like elements
    """
    # Keep class for button-like elements only; drop elsewhere if enabled
    keep_attrs = {"id", "class", "href", "src", "alt", "title", "type", "value", "name", "role", "rel"}

    for el in soup.find_all(True):
        if el.attrs is None:
            continue

        for attr in list(el.attrs.keys()):
            # Always keep aria-* attributes
            if attr.startswith("aria-"):
                continue

            # Class pruning toggle
            if attr == "class" and prune_classes_except_buttons:
                if not _is_button_like(el):
                    try:
                        del el.attrs["class"]
                        pruned_counts["attr_trim"] += 1
                        pruned_counts["class_drops"] += 1
                    except Exception:
                        pass
                    continue  # move on to next attr

            # Drop attributes not in the allowlist
            if attr not in keep_attrs:
                del el.attrs[attr]
                pruned_counts["attr_trim"] += 1
                continue

            # Normalize values
            val = el.get(attr)

            # Preserve list type for class/rel
            if attr in {"class", "rel"} and isinstance(val, (list, tuple)):
                pass  # keep as list
            else:
                # Normalize other list-like values to strings
                if isinstance(val, (list, tuple)):
                    val = " ".join(map(str, val))
                    el[attr] = val

            # Truncate descriptive text fields
            if attr in {"alt", "title"} and isinstance(val, str) and len(val) > 80:
                el[attr] = val[:80] + "...(trunc)"
                pruned_counts["attr_trim"] += 1

        # Strip data URIs on src
        src = el.get("src")
        if isinstance(src, str) and src.startswith("data:"):
            try:
                del el.attrs["src"]
            except Exception:
                pass
            pruned_counts["attr_trim"] += 1


def _collapse_wrappers(soup, pruned_counts: Dict[str, int]) -> None:
    """
    Collapse empty div/span wrappers with a single child and replace images with minimal attributes.

    Args:
        soup: BeautifulSoup object to modify in-place
        pruned_counts: Dictionary to update with removal counts
    """
    # Replace images with minimal attrs
    for img in soup.find_all("img"):
        for k in list(img.attrs.keys()):
            if k not in {"alt", "title"}:
                del img.attrs[k]
        pruned_counts["media"] += 1

    # Collapse empty div/span wrappers with a single child
    changed = True
    while changed:
        changed = False
        for el in list(soup.find_all(["div", "span"])):
            if not el.parent:
                continue
            children = [c for c in el.children if getattr(c, "name", None)]
            if len(children) == 1 and not (el.get_text(strip=True) or "").strip():
                el.replace_with(children[0])
                pruned_counts["wrapper"] += 1
                changed = True
                break


def _normalize_whitespace(soup, pruned_counts: Dict[str, int]) -> str:
    """
    Normalize whitespace in text nodes and final HTML output.

    Args:
        soup: BeautifulSoup object to process
        pruned_counts: Dictionary to update with removal counts

    Returns:
        str: HTML string with normalized whitespace
    """
    from bs4 import NavigableString

    WHITESPACE_SENSITIVE = {"pre", "code", "textarea"}
    changed_nodes = 0

    for t in soup.find_all(string=True):
        parent = getattr(t, "parent", None)
        parent_name = (getattr(parent, "name", "") or "").lower()
        if parent_name in WHITESPACE_SENSITIVE:
            continue
        new_text = re.sub(r"\s+", " ", str(t))
        if new_text != str(t):
            t.replace_with(NavigableString(new_text))
            changed_nodes += 1
    pruned_counts["whitespace_trim"] += changed_nodes

    html_out = str(soup)

    # As a final safety net, ensure no literal newlines/tabs remain
    before_len = len(html_out)
    html_out = re.sub(r"[\r\n\t]+", " ", html_out)
    html_out = re.sub(r" {2,}", " ", html_out)
    html_out = html_out.strip()
    if len(html_out) < before_len:
        pruned_counts["whitespace_trim"] += 1

    return html_out


def basic_prune(
    html: str,
    level: int,
    prune_hidden: bool = True,
    prune_classes_except_buttons: bool = True,
    prune_linebreaks: bool = True,
    remove_cdn_links: bool = True,
    cdn_host_patterns: list[str] | None = None,
    drop_cdn_elements: bool = False,  # if True, remove entire asset tags
) -> Tuple[str, Dict[str, int]]:
    """
    Perform structural pruning on raw HTML to remove non-content noise.

    Args:
        html: Raw HTML string.
        level: Cleaning level. Higher = more aggressive.
        prune_hidden: If True, remove hidden elements and <input type="hidden">.
        prune_classes_except_buttons: If True, drop 'class' attributes for all
            elements except button-like ones (<button>, certain <input>, role="button").
        prune_linebreaks: If True, remove line breaks/tabs and collapse excessive
            whitespace in text nodes (skipping <pre>, <code>, <textarea>).
        remove_cdn_links: If True, strip CDN URLs from attributes and styles.
        cdn_host_patterns: Additional CDN pattern strings to match.
        drop_cdn_elements: If True, remove entire asset tags with CDN URLs.
    """
    pruned_counts = {
        "script": 0,
        "style": 0,
        "noise": 0,
        "attr_trim": 0,
        "wrapper": 0,
        "media": 0,
        "hidden_removed": 0,
        "class_drops": 0,
        "whitespace_trim": 0,
        "comments_removed": 0,
        "cdn_links_removed": 0,
    }

    import bs4
    soup = bs4.BeautifulSoup(html or "", "html.parser")

    # Phase 0: Remove HTML comments
    _remove_comments(soup, pruned_counts)

    # Phase 1: Remove scripts, styles, and non-content tags
    _remove_scripts_and_styles(soup, pruned_counts)

    # Phase 2: Remove noise containers and hidden elements (if level >= 1)
    if level >= 1:
        _remove_noise_containers(soup, pruned_counts, prune_hidden)

    # Phase 2.5: Strip CDN links (if enabled)
    if remove_cdn_links:
        _clean_cdn_links(soup, pruned_counts, cdn_host_patterns, drop_cdn_elements)

    # Phase 3: Prune attributes (if level >= 2)
    if level >= 2:
        _prune_attributes(soup, pruned_counts, prune_classes_except_buttons)

    # Phase 4: Collapse wrappers (if level >= 3)
    if level >= 3:
        _collapse_wrappers(soup, pruned_counts)

    # Phase 5: Normalize whitespace (if enabled)
    if prune_linebreaks:
        html_out = _normalize_whitespace(soup, pruned_counts)
    else:
        html_out = str(soup)

    return html_out, pruned_counts

def extract_outline(html: str, max_items: int = 64):
    import bs4
    soup = bs4.BeautifulSoup(html or "", "html.parser")
    outline = []
    for level, tag in [(1, "h1"), (2, "h2"), (3, "h3"), (4, "h4")]:
        for el in soup.find_all(tag):
            text = el.get_text(" ", strip=True)
            wc = len(text.split())
            # build a rough css_path
            css_path = None
            try:
                # naive css path
                parts = []
                cur = el
                while cur and cur.name and cur.name != "[document]":
                    idp = ("#" + cur.get("id")) if cur.has_attr("id") else ""
                    cls = "." + ".".join(cur.get("class", [])) if cur.has_attr("class") else ""
                    parts.append(f"{cur.name}{idp}{cls}")
                    cur = cur.parent
                css_path = " > ".join(reversed(parts))
            except Exception:
                css_path = None
            outline.append({"level": level, "text": text, "word_count": wc, "css_path": css_path, "subtree_id": None})
            if len(outline) >= max_items:
                return outline
    return outline

