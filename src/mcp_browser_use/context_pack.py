# mcp_browser_use/context_pack.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


class ReturnMode:
    HTML = "html"
    TEXT = "text"
    OUTLINE = "outline"
    DOMPATHS = "dompaths"
    MIXED = "mixed"

class CleaningLevel:
    RAW_VISIBLE = 0
    LIGHT = 1
    DEFAULT = 2
    AGGRESSIVE = 3

@dataclass
class IframeInfo:
    index: int
    name: Optional[str]
    id: Optional[str]
    src: Optional[str]
    same_origin: Optional[bool]
    css_path: Optional[str]
    visible: Optional[bool]
    summary_title: Optional[str] = None
    subtree_id: Optional[str] = None

@dataclass
class OutlineItem:
    level: int
    text: str
    word_count: int
    css_path: Optional[str]
    subtree_id: Optional[str]

@dataclass
class CatalogInteractive:
    role: Optional[str]
    text_excerpt: str
    css_path: Optional[str]
    xpath: Optional[str]
    nth_path: Optional[str]
    clickable: Optional[bool]
    enabled: Optional[bool]

@dataclass
class ContextPack:
    # meta
    window_tag: Optional[str]
    url: Optional[str]
    title: Optional[str]
    page_fingerprint: Optional[str] = None
    lock_owner: Optional[str] = None
    lock_expires_at: Optional[str] = None

    # stats
    cleaning_level_applied: int = CleaningLevel.DEFAULT
    approx_tokens: int = 0
    pruned_counts: Dict[str, int] = field(default_factory=dict)
    tokens_budget: Optional[int] = None
    nodes_kept: Optional[int] = None
    nodes_pruned: Optional[int] = None
    hard_capped: bool = False

    # presence flags
    snapshot_mode: str = ReturnMode.OUTLINE
    outline_present: bool = False
    diff_present: bool = False
    iframe_index_present: bool = False

    # payloads
    outline: List[OutlineItem] = field(default_factory=list)
    html: Optional[str] = None
    text: Optional[str] = None
    dompaths: Optional[List[Dict[str, Any]]] = None
    mixed: Optional[Dict[str, Any]] = None
    catalogs: Optional[Dict[str, Any]] = None
    forms: Optional[Dict[str, Any]] = None
    iframe_index: Optional[List[IframeInfo]] = None

    errors: List[Dict[str, Any]] = field(default_factory=list)