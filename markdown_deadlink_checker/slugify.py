from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Dict, List, Optional, Set, Tuple


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_MARKDOWN_IMAGE_RE = re.compile(r"\!\[([^\]]*)\]\([^\)]+\)")
_MARKDOWN_FORMATTING_RE = re.compile(r"[*_~`]")
_CUSTOM_ID_RE = re.compile(r"\s*\{#([a-zA-Z0-9_\-]+)\}\s*$")


def strip_markdown(text: str) -> str:
    """Strip basic Markdown and HTML tags to get the plain text representation."""
    text = _MARKDOWN_IMAGE_RE.sub(r"\1", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _MARKDOWN_FORMATTING_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return text.strip()


def slugify_heading(heading_text: str, existing_counts: Optional[Dict[str, int]] = None) -> str:
    """
    Generate a GitHub Flavored Markdown (GFM) slug from heading text.
    Handles disambiguation (-1, -2, ...) using existing_counts dictionary if provided.
    """
    # Check for custom anchor {#id}
    custom_match = _CUSTOM_ID_RE.search(heading_text)
    if custom_match:
        heading_text = heading_text[:custom_match.start()]
    
    cleaned = strip_markdown(heading_text)
    slug = cleaned.lower()
    # Remove all characters except word characters, whitespace, and hyphens
    slug = re.sub(r"[^\w\s\-]", "", slug)
    # Replace whitespace with hyphens
    slug = re.sub(r"\s", "-", slug)
    
    if not slug:
        slug = ""

    if existing_counts is not None:
        count = existing_counts.get(slug, 0)
        existing_counts[slug] = count + 1
        if count > 0:
            slug = f"{slug}-{count}"

    return slug


def ascii_fold(text: str) -> str:
    """Strip accents and diacritics: e.g. café -> cafe."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class DocumentAnchors:
    """Tracks valid anchors in a document, including GFM slugs and explicit HTML IDs."""

    def __init__(self) -> None:
        self.exact_anchors: Set[str] = set()
        self.case_folded_anchors: Dict[str, str] = {}
        self.slug_counts: Dict[str, int] = {}
        self.ordered_anchors: List[str] = []

    def add_anchor(self, anchor: str) -> None:
        """Register an explicit anchor ID or slug, plus common variations."""
        anchor = anchor.strip()
        if not anchor:
            return
        if anchor.startswith("#"):
            anchor = anchor[1:]

        # Add raw
        self._register_variant(anchor)

        # Add single-hyphen collapsed variant if different
        collapsed = re.sub(r"-+", "-", anchor)
        if collapsed != anchor:
            self._register_variant(collapsed)

        # Add ASCII folded variant
        folded = ascii_fold(anchor)
        if folded != anchor:
            self._register_variant(folded)
            folded_collapsed = re.sub(r"-+", "-", folded)
            if folded_collapsed != folded:
                self._register_variant(folded_collapsed)

    def _register_variant(self, variant: str) -> None:
        if variant not in self.exact_anchors:
            self.exact_anchors.add(variant)
            self.ordered_anchors.append(variant)
            self.case_folded_anchors[variant.lower()] = variant

    def add_heading(self, heading_text: str) -> str:
        """Register a heading, extracting custom IDs and generating GFM slug."""
        custom_match = _CUSTOM_ID_RE.search(heading_text)
        if custom_match:
            custom_id = custom_match.group(1)
            self.add_anchor(custom_id)
        
        slug = slugify_heading(heading_text, self.slug_counts)
        if slug:
            self.add_anchor(slug)
        return slug

    def contains(self, anchor: str) -> bool:
        """Check if anchor exists (exact, case-insensitive, or URL decoded)."""
        if anchor.startswith("#"):
            anchor = anchor[1:]
        decoded = urllib.parse.unquote(anchor)
        collapsed = re.sub(r"-+", "-", anchor)
        decoded_collapsed = re.sub(r"-+", "-", decoded)

        candidates = [
            anchor,
            anchor.lower(),
            decoded,
            decoded.lower(),
            collapsed,
            collapsed.lower(),
            decoded_collapsed,
            decoded_collapsed.lower(),
            ascii_fold(anchor).lower(),
            ascii_fold(decoded).lower(),
        ]

        for cand in candidates:
            if cand in self.exact_anchors or cand in self.case_folded_anchors:
                return True
        return False

    def get_all(self) -> List[str]:
        return list(self.ordered_anchors)
