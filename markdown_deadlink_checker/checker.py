from __future__ import annotations

import fnmatch
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from markdown_deadlink_checker.models import (
    CheckResult,
    CheckStatus,
    LinkTarget,
    LinkType,
    ScanSummary,
)
from markdown_deadlink_checker.parser import ParsedDocument, parse_markdown
from markdown_deadlink_checker.slugify import DocumentAnchors


MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdx"}

DEFAULT_IGNORE_PATHS = [
    "**/.git/**",
    "**/.venv/**",
    "**/venv/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/dist/**",
    "**/build/**",
    "**/.tox/**",
    "**/.mypy_cache/**",
]


def check_exact_case_exists(path: Path) -> bool:
    """Verify that every segment of path exists with exact case match."""
    try:
        resolved = path.resolve()
        current = Path(resolved.root)
        for part in resolved.parts[1:] if resolved.drive else resolved.parts:
            if part == resolved.drive:
                current = Path(part + os.sep)
                continue
            candidates = os.listdir(current)
            if part not in candidates:
                return False
            current = current / part
        return True
    except (OSError, ValueError):
        return False


def check_external_url(url: str, timeout: float = 5.0) -> Tuple[bool, str]:
    """Perform a network check on an external URL using standard library urllib."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) markdown-deadlink-checker/0.1.0"
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status < 400:
                return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as e:
        if e.code in (405, 403, 400):
            try:
                get_req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(get_req, timeout=timeout) as response:
                    if response.status < 400:
                        return True, f"HTTP {response.status}"
            except Exception as get_err:
                return False, f"GET failed: {get_err}"
        return False, f"HTTP {e.code}: {e.reason}"
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        return False, f"Connection failed: {e}"
    except Exception as e:
        return False, f"Error: {e}"
    return True, "OK"


class DeadLinkChecker:
    """
    Scans markdown files and directories to verify relative file paths,
    image references, and heading anchor links exist.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        ignore_paths: Optional[Sequence[str]] = None,
        ignore_urls: Optional[Sequence[str]] = None,
        check_external: bool = False,
        external_timeout: float = 5.0,
        allow_directories: bool = True,
        require_exact_case: bool = False,
    ) -> None:
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
        
        self.ignore_paths = list(DEFAULT_IGNORE_PATHS)
        if ignore_paths:
            self.ignore_paths.extend(ignore_paths)

        self.ignore_urls = [re.compile(p) for p in (ignore_urls or [])]
        self.check_external = check_external
        self.external_timeout = external_timeout
        self.allow_directories = allow_directories
        self.require_exact_case = require_exact_case

        # Caches
        self._document_cache: Dict[Path, ParsedDocument] = {}
        self._external_cache: Dict[str, Tuple[bool, str]] = {}

    def is_path_ignored(self, path: Path) -> bool:
        """Check if a file or directory path matches any ignore pattern."""
        resolved = path.resolve() if path.is_absolute() else path
        path_str = str(resolved).replace("\\", "/")
        norm_path = os.path.normpath(str(resolved)).replace("\\", "/")
        name = resolved.name

        rel_str: Optional[str] = None
        if resolved.is_absolute():
            try:
                rel_str = str(resolved.relative_to(self.base_dir)).replace("\\", "/")
            except ValueError:
                rel_str = None
        else:
            rel_str = path_str

        for pattern in self.ignore_paths:
            p_norm = pattern.replace("\\", "/").rstrip("/")
            p_glob = f"{p_norm}/*" if not p_norm.endswith("*") else p_norm

            # Match on file/dir name
            if fnmatch.fnmatch(name, p_norm) or fnmatch.fnmatch(name, p_glob):
                return True

            # Match on full path
            if fnmatch.fnmatch(path_str, p_norm) or fnmatch.fnmatch(path_str, p_glob):
                return True

            # Match on relative path
            if rel_str is not None:
                if fnmatch.fnmatch(rel_str, p_norm) or fnmatch.fnmatch(rel_str, p_glob):
                    return True
                if fnmatch.fnmatch(rel_str, f"*/{p_norm}") or fnmatch.fnmatch(rel_str, f"*/{p_glob}"):
                    return True

            # Pattern prefix match (e.g. docs/** or legacy/**)
            clean_p = p_norm.lstrip("*/")
            if rel_str and (rel_str.startswith(clean_p) or rel_str == clean_p.rstrip("/*")):
                return True
            if name.startswith(clean_p):
                return True

        return False

    def is_url_ignored(self, raw_url: str) -> bool:
        """Check if link target matches any ignore URL regex."""
        for pattern in self.ignore_urls:
            if pattern.search(raw_url):
                return True
        return False

    def get_document(self, path: Path) -> Optional[ParsedDocument]:
        """Load and cache parsed markdown document."""
        resolved = path.resolve()
        if resolved in self._document_cache:
            return self._document_cache[resolved]

        if not resolved.is_file():
            return None

        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
            doc = parse_markdown(content, resolved)
            self._document_cache[resolved] = doc
            return doc
        except Exception:
            return None

    def discover_files(self, targets: Sequence[Path | str]) -> List[Path]:
        """Find all markdown files under the target directories or single files."""
        discovered: List[Path] = []
        for target in targets:
            target_path = Path(target)
            if not target_path.exists():
                continue

            if target_path.is_file():
                if target_path.suffix.lower() in MARKDOWN_EXTENSIONS:
                    if not self.is_path_ignored(target_path):
                        discovered.append(target_path.resolve())
            elif target_path.is_dir():
                for root, dirs, files in os.walk(target_path):
                    root_path = Path(root)
                    dirs[:] = [
                        d for d in dirs if not self.is_path_ignored(root_path / d)
                    ]

                    for f in files:
                        p = root_path / f
                        if p.suffix.lower() in MARKDOWN_EXTENSIONS:
                            if not self.is_path_ignored(p):
                                discovered.append(p.resolve())

        return sorted(list(set(discovered)))

    def check_link(self, link: LinkTarget, current_doc: ParsedDocument) -> CheckResult:
        """Check a single link target for validity."""
        raw = link.raw_target.strip()

        # Check URL ignores
        if self.is_url_ignored(raw):
            return CheckResult(
                link=link,
                status=CheckStatus.IGNORED,
                message=f"Ignored by pattern match: {raw}",
            )

        # Check Special links (mailto, tel, javascript)
        if link.link_type == LinkType.SPECIAL:
            return CheckResult(
                link=link,
                status=CheckStatus.SKIPPED,
                message=f"Special protocol skipped: {raw}",
            )

        # Check External links
        if link.link_type == LinkType.EXTERNAL:
            if not self.check_external:
                return CheckResult(
                    link=link,
                    status=CheckStatus.SKIPPED,
                    message="External link check skipped",
                )
            
            if raw not in self._external_cache:
                self._external_cache[raw] = check_external_url(raw, self.external_timeout)
            
            success, msg = self._external_cache[raw]
            status = CheckStatus.EXTERNAL_VALID if success else CheckStatus.EXTERNAL_DEAD
            return CheckResult(link=link, status=status, message=msg)

        # Check Same-file anchor
        if link.link_type == LinkType.SAME_FILE_ANCHOR:
            anchor = link.anchor or ""
            if not anchor:
                return CheckResult(link=link, status=CheckStatus.VALID, message="Top of page anchor")

            if current_doc.anchors.contains(anchor):
                return CheckResult(
                    link=link,
                    status=CheckStatus.VALID,
                    message=f"Anchor #{anchor} found in {link.source_file.name}",
                )
            else:
                available = current_doc.anchors.get_all()
                return CheckResult(
                    link=link,
                    status=CheckStatus.DEAD_ANCHOR,
                    message=f"Anchor '#{anchor}' not found in document",
                    available_anchors=available,
                )

        # Clean file path: remove query parameters, url decoding
        raw_file_path = link.file_path or ""
        clean_file = raw_file_path.split("?")[0]
        decoded_file = urllib.parse.unquote(clean_file)

        # Check if the target path is explicitly ignored
        if self.is_path_ignored(Path(decoded_file)):
            return CheckResult(
                link=link,
                status=CheckStatus.IGNORED,
                message=f"Target path ignored: {decoded_file}",
            )

        # Resolve file path
        source_dir = link.source_file.parent
        if decoded_file.startswith("/") or decoded_file.startswith("\\"):
            target_path = (self.base_dir / decoded_file.lstrip("/\\")).resolve()
        else:
            target_path = (source_dir / decoded_file).resolve()

        if self.is_path_ignored(target_path):
            return CheckResult(
                link=link,
                status=CheckStatus.IGNORED,
                message=f"Target path ignored: {target_path}",
            )

        # Check case-sensitivity if required
        if self.require_exact_case and target_path.exists():
            if not check_exact_case_exists(target_path):
                return CheckResult(
                    link=link,
                    status=CheckStatus.DEAD_FILE,
                    message=f"File exists with different casing on disk: {target_path}",
                    resolved_path=target_path,
                )

        # Check if target exists
        if not target_path.exists():
            return CheckResult(
                link=link,
                status=CheckStatus.DEAD_FILE,
                message=f"Target file does not exist: {target_path}",
                resolved_path=target_path,
            )

        # If target is a directory
        if target_path.is_dir():
            if not self.allow_directories:
                return CheckResult(
                    link=link,
                    status=CheckStatus.DEAD_FILE,
                    message=f"Target is a directory (directory links disabled): {target_path}",
                    resolved_path=target_path,
                )
            
            if link.anchor:
                index_candidates = [target_path / "README.md", target_path / "index.md"]
                index_doc = None
                for cand in index_candidates:
                    if cand.is_file():
                        index_doc = self.get_document(cand)
                        if index_doc:
                            break

                if index_doc:
                    if index_doc.anchors.contains(link.anchor):
                        return CheckResult(
                            link=link,
                            status=CheckStatus.VALID,
                            message=f"Anchor #{link.anchor} found in {index_doc.file_path.name}",
                            resolved_path=target_path,
                        )
                    else:
                        return CheckResult(
                            link=link,
                            status=CheckStatus.DEAD_ANCHOR,
                            message=f"Anchor '#{link.anchor}' not found in directory index ({index_doc.file_path.name})",
                            resolved_path=target_path,
                            available_anchors=index_doc.anchors.get_all(),
                        )
                else:
                    return CheckResult(
                        link=link,
                        status=CheckStatus.DEAD_ANCHOR,
                        message=f"Anchor '#{link.anchor}' specified on directory without README.md or index.md",
                        resolved_path=target_path,
                    )
            
            return CheckResult(
                link=link,
                status=CheckStatus.VALID,
                message=f"Target directory exists: {target_path}",
                resolved_path=target_path,
            )

        # Cross-file anchor
        if link.anchor:
            if target_path.suffix.lower() in MARKDOWN_EXTENSIONS:
                target_doc = self.get_document(target_path)
                if not target_doc:
                    return CheckResult(
                        link=link,
                        status=CheckStatus.DEAD_FILE,
                        message=f"Could not read target markdown file: {target_path}",
                        resolved_path=target_path,
                    )
                if target_doc.anchors.contains(link.anchor):
                    return CheckResult(
                        link=link,
                        status=CheckStatus.VALID,
                        message=f"Anchor #{link.anchor} found in {target_path.name}",
                        resolved_path=target_path,
                    )
                else:
                    return CheckResult(
                        link=link,
                        status=CheckStatus.DEAD_ANCHOR,
                        message=f"Anchor '#{link.anchor}' not found in {target_path.name}",
                        resolved_path=target_path,
                        available_anchors=target_doc.anchors.get_all(),
                    )
            else:
                return CheckResult(
                    link=link,
                    status=CheckStatus.VALID,
                    message=f"File exists (non-markdown anchor not verified): {target_path}",
                    resolved_path=target_path,
                )

        return CheckResult(
            link=link,
            status=CheckStatus.VALID,
            message="Target file exists",
            resolved_path=target_path,
        )

    def scan(self, targets: Sequence[Path | str]) -> ScanSummary:
        """Scan target markdown files and verify all links."""
        files = self.discover_files(targets)
        summary = ScanSummary(files_scanned=len(files))

        for f in files:
            self.get_document(f)

        for f in files:
            doc = self.get_document(f)
            if not doc:
                summary.errors.append(f"Failed to parse document: {f}")
                continue

            for link in doc.links:
                summary.total_links += 1
                result = self.check_link(link, doc)
                summary.results.append(result)

                if result.is_dead:
                    summary.dead_links += 1
                elif result.is_valid:
                    summary.valid_links += 1
                elif result.is_ignored:
                    summary.ignored_links += 1

        return summary
