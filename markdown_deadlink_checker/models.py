from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class LinkType(str, Enum):
    RELATIVE_FILE = "relative_file"
    SAME_FILE_ANCHOR = "same_file_anchor"
    CROSS_FILE_ANCHOR = "cross_file_anchor"
    IMAGE = "image"
    EXTERNAL = "external"
    SPECIAL = "special"  # mailto, tel, javascript, etc.


class CheckStatus(str, Enum):
    VALID = "valid"
    DEAD_FILE = "dead_file"
    DEAD_ANCHOR = "dead_anchor"
    EXTERNAL_VALID = "external_valid"
    EXTERNAL_DEAD = "external_dead"
    IGNORED = "ignored"
    SKIPPED = "skipped"


@dataclass
class LinkTarget:
    raw_target: str
    file_path: Optional[str]
    anchor: Optional[str]
    link_type: LinkType
    line: int
    column: int
    source_file: Path
    text: str = ""
    is_image: bool = False

    @property
    def is_external(self) -> bool:
        return self.link_type == LinkType.EXTERNAL

    @property
    def is_special(self) -> bool:
        return self.link_type == LinkType.SPECIAL


@dataclass
class CheckResult:
    link: LinkTarget
    status: CheckStatus
    message: str
    resolved_path: Optional[Path] = None
    available_anchors: Optional[List[str]] = None

    @property
    def is_dead(self) -> bool:
        return self.status in (CheckStatus.DEAD_FILE, CheckStatus.DEAD_ANCHOR, CheckStatus.EXTERNAL_DEAD)

    @property
    def is_valid(self) -> bool:
        return self.status in (CheckStatus.VALID, CheckStatus.EXTERNAL_VALID)

    @property
    def is_ignored(self) -> bool:
        return self.status in (CheckStatus.IGNORED, CheckStatus.SKIPPED)


@dataclass
class ScanSummary:
    files_scanned: int = 0
    total_links: int = 0
    valid_links: int = 0
    dead_links: int = 0
    ignored_links: int = 0
    results: List[CheckResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def has_dead_links(self) -> bool:
        return self.dead_links > 0
