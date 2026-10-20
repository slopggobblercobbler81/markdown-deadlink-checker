from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, TextIO

from markdown_deadlink_checker.models import CheckResult, ScanSummary


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"

    @classmethod
    def enabled(cls, stream: TextIO) -> bool:
        """Check if colored output should be enabled."""
        import os
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("FORCE_COLOR") == "1":
            return True
        return hasattr(stream, "isatty") and stream.isatty()


def format_text(summary: ScanSummary, stream: TextIO = sys.stdout, verbose: bool = False, quiet: bool = False) -> str:
    use_color = Colors.enabled(stream)
    
    def colorize(text: str, color: str) -> str:
        return f"{color}{text}{Colors.RESET}" if use_color else text

    lines: List[str] = []

    # Group dead results by file
    dead_results = [r for r in summary.results if r.is_dead]
    valid_results = [r for r in summary.results if r.is_valid]
    ignored_results = [r for r in summary.results if r.is_ignored]

    if not quiet:
        lines.append(colorize("=== Markdown Deadlink Checker ===", Colors.BOLD + Colors.CYAN))
        lines.append("")

    if dead_results:
        lines.append(colorize(f"Found {len(dead_results)} dead link(s):", Colors.BOLD + Colors.RED))
        lines.append("")
        
        # Group by source file
        by_file: Dict[Path, List[CheckResult]] = {}
        for r in dead_results:
            by_file.setdefault(r.link.source_file, []).append(r)

        for file_path, file_results in by_file.items():
            lines.append(colorize(f"File: {file_path}", Colors.BOLD))
            for res in file_results:
                loc = f"  line {res.link.line}:{res.link.column}"
                status_tag = colorize("[DEAD]", Colors.RED)
                label = f" ({res.link.text})" if res.link.text else ""
                lines.append(f"  {status_tag} {loc} -> {res.link.raw_target}{label}")
                lines.append(f"         {colorize('Error:', Colors.YELLOW)} {res.message}")
                if res.available_anchors:
                    preview = ", ".join(f"#{a}" for a in res.available_anchors[:6])
                    if len(res.available_anchors) > 6:
                        preview += f" ... (+{len(res.available_anchors) - 6} more)"
                    lines.append(f"         {colorize('Available anchors:', Colors.GRAY)} {preview}")
            lines.append("")

    if verbose and valid_results:
        lines.append(colorize(f"Valid links ({len(valid_results)}):", Colors.BOLD + Colors.GREEN))
        for r in valid_results:
            lines.append(f"  {colorize('[OK]', Colors.GREEN)} {r.link.source_file.name}:{r.link.line}:{r.link.column} -> {r.link.raw_target}")
        lines.append("")

    if verbose and ignored_results:
        lines.append(colorize(f"Ignored/Skipped links ({len(ignored_results)}):", Colors.BOLD + Colors.GRAY))
        for r in ignored_results:
            lines.append(f"  {colorize('[SKIP]', Colors.GRAY)} {r.link.source_file.name}:{r.link.line}:{r.link.column} -> {r.link.raw_target} ({r.message})")
        lines.append("")

    # Summary box
    if not quiet or summary.has_dead_links:
        status_banner = (
            colorize("FAILURE", Colors.BOLD + Colors.RED)
            if summary.has_dead_links
            else colorize("SUCCESS", Colors.BOLD + Colors.GREEN)
        )
        lines.append("--------------------------------------------------")
        lines.append(f"Result: {status_banner}")
        lines.append(f"Files scanned:   {summary.files_scanned}")
        lines.append(f"Total links:     {summary.total_links}")
        lines.append(f"Valid links:     {colorize(str(summary.valid_links), Colors.GREEN)}")
        lines.append(f"Dead links:      {colorize(str(summary.dead_links), Colors.RED if summary.dead_links else Colors.GREEN)}")
        lines.append(f"Ignored/Skipped: {colorize(str(summary.ignored_links), Colors.GRAY)}")
        lines.append("--------------------------------------------------")

    return "\n".join(lines)


def format_json(summary: ScanSummary) -> str:
    """Export results as a structured JSON object."""
    output = {
        "status": "failure" if summary.has_dead_links else "success",
        "summary": {
            "files_scanned": summary.files_scanned,
            "total_links": summary.total_links,
            "valid_links": summary.valid_links,
            "dead_links": summary.dead_links,
            "ignored_links": summary.ignored_links,
        },
        "errors": summary.errors,
        "results": [
            {
                "source_file": str(r.link.source_file),
                "line": r.link.line,
                "column": r.link.column,
                "target": r.link.raw_target,
                "text": r.link.text,
                "is_image": r.link.is_image,
                "status": r.status.value,
                "message": r.message,
                "resolved_path": str(r.resolved_path) if r.resolved_path else None,
                "available_anchors": r.available_anchors,
            }
            for r in summary.results
        ],
    }
    return json.dumps(output, indent=2)


def format_github(summary: ScanSummary) -> str:
    """Format dead link errors as GitHub Actions workflow commands."""
    lines: List[str] = []

    for r in summary.results:
        if r.is_dead:
            file_path = str(r.link.source_file).replace("\\", "/")
            lines.append(
                f"::error file={file_path},line={r.link.line},col={r.link.column}::"
                f"Dead link '{r.link.raw_target}': {r.message}"
            )

    if summary.has_dead_links:
        lines.append(
            f"::error::Found {summary.dead_links} dead link(s) across {summary.files_scanned} markdown files."
        )
    else:
        lines.append(
            f"::notice::Checked {summary.total_links} links across {summary.files_scanned} files. No dead links found!"
        )

    return "\n".join(lines)
