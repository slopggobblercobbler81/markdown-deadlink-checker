from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from markdown_deadlink_checker.models import LinkTarget, LinkType
from markdown_deadlink_checker.slugify import DocumentAnchors


_FENCED_CODE_START = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
_HTML_COMMENT_START = re.compile(r"<!--")
_HTML_COMMENT_END = re.compile(r"-->")
_INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1", re.DOTALL)

_ATX_HEADING_RE = re.compile(r"^[ ]{0,3}#{1,6}\s+(.+?)(?:\s+#+)?$")
_SETEXT_UNDERLINE_RE = re.compile(r"^[ ]{0,3}(?:=+|-+)\s*$")
_HTML_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_HTML_ID_ATTR_RE = re.compile(r"""<\w+\s+[^>]*?(?:id|name)=["']([^"']+)["'][^>]*>""", re.IGNORECASE)

# Markdown link regex: [text](target "optional title")
# Supports angle bracket target: [text](<path with spaces>)
_MD_LINK_RE = re.compile(
    r"""(?P<is_img>!?)\[(?P<text>(?:[^\[\]]|\[[^\]]*\])*)\]\(\s*(?:<(?P<url_bracket>[^>]+)>|(?P<url>[^\s\)]+))(?:\s+["'(].*?["')])?\s*\)"""
)

# Reference definitions: [label]: target "title"
_REF_DEF_RE = re.compile(
    r"""^[ ]{0,3}\[(?P<label>[^\]]+)\]:\s*(?:<(?P<url_bracket>[^>]+)>|(?P<url>\S+))(?:\s+["'(].*?["')])?\s*$"""
)

# Reference links: [text][label] or [text][]
_REF_LINK_RE = re.compile(
    r"""(?P<is_img>!?)\[(?P<text>[^\]]+)\]\[(?P<label>[^\]]*)\]"""
)

# HTML links and images
_HTML_A_RE = re.compile(
    r"""<a\s+[^>]*?href=["']([^"']+)["'][^>]*>(.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_HTML_A_STANDALONE_RE = re.compile(
    r"""<a\s+[^>]*?href=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)
_HTML_IMG_RE = re.compile(
    r"""<img\s+[^>]*?src=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)


@dataclass
class ParsedDocument:
    file_path: Path
    anchors: DocumentAnchors
    links: List[LinkTarget]


def mask_code_and_comments(content: str) -> str:
    """
    Mask fenced code blocks, HTML comments, and inline code with spaces,
    preserving exact length and newline positions so line/column indexing remains exact.
    """
    lines = content.splitlines(keepends=True)
    masked_lines: List[str] = []
    
    in_fence: Optional[str] = None
    fence_char: str = ""
    fence_len: int = 0
    in_html_comment: bool = False

    for line in lines:
        stripped_line = line.strip()
        
        # Handle ongoing HTML comment
        if in_html_comment:
            end_match = _HTML_COMMENT_END.search(line)
            if end_match:
                in_html_comment = False
                masked_lines.append(" " * end_match.end() + line[end_match.end():])
            else:
                masked_lines.append(" " * (len(line) - 1) + ("\n" if line.endswith("\n") else " "))
            continue

        # Handle ongoing fenced block
        if in_fence:
            # Check for closing fence: must use same char and at least same length
            m = _FENCED_CODE_START.match(line)
            if m and m.group(1).startswith(fence_char) and len(m.group(1)) >= fence_len:
                in_fence = None
            masked_lines.append(" " * (len(line) - 1) + ("\n" if line.endswith("\n") else " "))
            continue

        # Check for opening fence
        m = _FENCED_CODE_START.match(line)
        if m:
            in_fence = m.group(1)
            fence_char = in_fence[0]
            fence_len = len(in_fence)
            masked_lines.append(" " * (len(line) - 1) + ("\n" if line.endswith("\n") else " "))
            continue

        # Check for start of HTML comment
        c_match = _HTML_COMMENT_START.search(line)
        if c_match:
            end_match = _HTML_COMMENT_END.search(line, c_match.end())
            if end_match:
                # Comment opens and closes on same line
                line = line[:c_match.start()] + (" " * (end_match.end() - c_match.start())) + line[end_match.end():]
            else:
                in_html_comment = True
                masked_lines.append(line[:c_match.start()] + (" " * (len(line) - c_match.start() - 1)) + ("\n" if line.endswith("\n") else " "))
                continue

        # Mask inline code: `...`
        def _replace_inline(match: re.Match) -> str:
            return " " * len(match.group(0))

        line = _INLINE_CODE_RE.sub(_replace_inline, line)
        masked_lines.append(line)

    return "".join(masked_lines)


def classify_target(raw_target: str, is_image: bool = False) -> Tuple[LinkType, Optional[str], Optional[str]]:
    """
    Classify a link target and split into (LinkType, file_part, anchor_part).
    """
    target = raw_target.strip()
    
    # Check special protocols
    lower = target.lower()
    if lower.startswith(("mailto:", "tel:", "sms:", "javascript:", "data:", "irc:", "ssh:", "git:", "magnet:", "urn:")):
        return LinkType.SPECIAL, None, None

    # Check external URLs
    if lower.startswith(("http://", "https://", "//", "ftp://")):
        return LinkType.EXTERNAL, None, None

    # Same file anchor
    if target.startswith("#"):
        anchor = target[1:]
        return LinkType.SAME_FILE_ANCHOR, None, anchor

    # Cross-file anchor or relative file
    if "#" in target:
        file_part, anchor_part = target.split("#", 1)
        file_part = file_part.strip()
        anchor_part = anchor_part.strip()
        return LinkType.CROSS_FILE_ANCHOR, file_part, anchor_part

    if is_image:
        return LinkType.IMAGE, target, None

    return LinkType.RELATIVE_FILE, target, None


def extract_anchors(raw_content: str) -> DocumentAnchors:
    """Extract all valid anchors (headings, HTML IDs) from a Markdown document."""
    anchors = DocumentAnchors()
    lines = raw_content.splitlines()
    
    # 1. ATX headings
    in_fence = False
    fence_char = ""
    fence_len = 0

    for i, line in enumerate(lines):
        # Code fence check
        m = _FENCED_CODE_START.match(line)
        if m:
            if not in_fence:
                in_fence = True
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
            elif m.group(1).startswith(fence_char) and len(m.group(1)) >= fence_len:
                in_fence = False
            continue

        if in_fence:
            continue

        # ATX heading
        atx_m = _ATX_HEADING_RE.match(line)
        if atx_m:
            heading_text = atx_m.group(1).strip()
            anchors.add_heading(heading_text)
            continue

        # Setext heading (check next line)
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if _SETEXT_UNDERLINE_RE.match(next_line) and line.strip() and not line.strip().startswith("#"):
                anchors.add_heading(line.strip())

    # 2. HTML elements with id or name
    for match in _HTML_ID_ATTR_RE.finditer(raw_content):
        anchors.add_anchor(match.group(1))

    # 3. HTML headings: <h1>...</h1>
    for match in _HTML_HEADING_RE.finditer(raw_content):
        heading_text = match.group(2).strip()
        anchors.add_heading(heading_text)

    return anchors


def parse_markdown(content: str, file_path: Path) -> ParsedDocument:
    """
    Parse a Markdown file, discovering all internal and external links with line & column numbers.
    """
    anchors = extract_anchors(content)
    masked_content = mask_code_and_comments(content)
    
    links: List[LinkTarget] = []

    # Map byte/char positions to (line, col)
    # Build cumulative line starts
    line_starts = [0]
    for m in re.finditer(r"\n", masked_content):
        line_starts.append(m.end())

    def get_line_col(pos: int) -> Tuple[int, int]:
        import bisect
        line_idx = bisect.bisect_right(line_starts, pos) - 1
        col = (pos - line_starts[line_idx]) + 1
        return line_idx + 1, col

    # 1. Parse reference definitions: [label]: target
    ref_defs: Dict[str, Tuple[str, int, int]] = {}
    lines = content.splitlines()
    for line_idx, line in enumerate(lines, start=1):
        ref_m = _REF_DEF_RE.match(line)
        if ref_m:
            label = ref_m.group("label").strip().lower()
            url = ref_m.group("url_bracket") or ref_m.group("url")
            col = ref_m.start("url_bracket") if ref_m.group("url_bracket") else ref_m.start("url")
            ref_defs[label] = (url, line_idx, col + 1)

    # 2. Extract standard markdown links: [text](target)
    for match in _MD_LINK_RE.finditer(masked_content):
        is_img = match.group("is_img") == "!"
        text = match.group("text")
        raw_url = match.group("url_bracket") or match.group("url")
        start_pos = match.start()
        line, col = get_line_col(start_pos)
        
        link_type, file_part, anchor = classify_target(raw_url, is_image=is_img)
        links.append(
            LinkTarget(
                raw_target=raw_url,
                file_path=file_part,
                anchor=anchor,
                link_type=link_type,
                line=line,
                column=col,
                source_file=file_path,
                text=text,
                is_image=is_img,
            )
        )

    # 3. Extract reference links: [text][label] or [text][]
    for match in _REF_LINK_RE.finditer(masked_content):
        is_img = match.group("is_img") == "!"
        text = match.group("text")
        label = match.group("label").strip()
        if not label:
            label = text.strip()
        
        label_key = label.lower()
        if label_key in ref_defs:
            raw_url, def_line, def_col = ref_defs[label_key]
            line, col = get_line_col(match.start())
            link_type, file_part, anchor = classify_target(raw_url, is_image=is_img)
            links.append(
                LinkTarget(
                    raw_target=raw_url,
                    file_path=file_part,
                    anchor=anchor,
                    link_type=link_type,
                    line=line,
                    column=col,
                    source_file=file_path,
                    text=text,
                    is_image=is_img,
                )
            )

    # 4. Extract HTML <a> tags
    for match in _HTML_A_STANDALONE_RE.finditer(masked_content):
        raw_url = match.group(1).strip()
        line, col = get_line_col(match.start())
        link_type, file_part, anchor = classify_target(raw_url, is_image=False)
        links.append(
            LinkTarget(
                raw_target=raw_url,
                file_path=file_part,
                anchor=anchor,
                link_type=link_type,
                line=line,
                column=col,
                source_file=file_path,
                text="",
                is_image=False,
            )
        )

    # 5. Extract HTML <img> tags
    for match in _HTML_IMG_RE.finditer(masked_content):
        raw_url = match.group(1).strip()
        line, col = get_line_col(match.start())
        link_type, file_part, anchor = classify_target(raw_url, is_image=True)
        links.append(
            LinkTarget(
                raw_target=raw_url,
                file_path=file_part,
                anchor=anchor,
                link_type=link_type,
                line=line,
                column=col,
                source_file=file_path,
                text="",
                is_image=True,
            )
        )

    # Sort links by line and column
    links.sort(key=lambda l: (l.line, l.column))
    return ParsedDocument(file_path=file_path, anchors=anchors, links=links)
