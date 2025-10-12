# mcp_browser_use/cleaners.py

import re
from typing import Tuple, Dict

NOISE_ID_CLASS_PAT = re.compile(
    r"(gtm|gtag|analytics|ad[s-]?|adslot|sponsor|cookie[-_ ]?banner|chat[-_ ]?widget)",
    re.I
)

HIDDEN_CLASS_PAT = re.compile(r"(sr-only|visually-hidden|offscreen)", re.I)

def approx_token_count(text: str) -> int:
    # Fast heuristic: ~4 chars per token
    return max(0, (len(text) // 4))



def basic_prune(html: str, level: int) -> Tuple[str, Dict[str, int]]:
    """
    Perform structural pruning on raw HTML to remove non-content noise.
    """
    pruned_counts = {"script": 0, "style": 0, "noise": 0, "attr_trim": 0, "wrapper": 0, "media": 0}

    import bs4
    soup = bs4.BeautifulSoup(html or "", "html.parser")

    # 1) Remove scripts/styles/noscript/template/svg/canvas/meta/source/track
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

    # 2) Remove obvious noise containers
    if level >= 1:
        removed = 0
        for el in soup.find_all(True):
            if el.attrs is None:
                continue
            idv = el.get("id") or ""
            classv = " ".join(el.get("class") or [])
            aria_hidden = str(el.get("aria-hidden", "")).strip().lower() == "true"
            style_val = el.get("style")
            style_hidden = isinstance(style_val, str) and (
                "display:none" in style_val.lower() or "visibility:hidden" in style_val.lower()
            )
            hidden_attr = el.has_attr("hidden") or aria_hidden or style_hidden

            if NOISE_ID_CLASS_PAT.search(idv) or NOISE_ID_CLASS_PAT.search(classv) or hidden_attr or HIDDEN_CLASS_PAT.search(classv):
                el.decompose()
                removed += 1
        pruned_counts["noise"] += removed

    # 3) Attribute pruning
    if level >= 2:
        keep_attrs = {"id", "class", "href", "src", "alt", "title", "type", "value", "name", "role", "rel"}
        for el in soup.find_all(True):
            if el.attrs is None:
                continue

            for attr in list(el.attrs.keys()):
                # Always keep aria-* attributes
                if attr.startswith("aria-"):
                    continue

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

                # Only truncate descriptive text fields
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

    # 4) Wrapper collapsing and media placeholders
    if level >= 3:
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

    return str(soup), pruned_counts

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