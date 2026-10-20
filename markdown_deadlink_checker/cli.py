from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from markdown_deadlink_checker import __version__
from markdown_deadlink_checker.checker import DeadLinkChecker
from markdown_deadlink_checker.reporter import format_github, format_json, format_text


def load_pyproject_config(config_path: Optional[Path] = None) -> dict:
    """Load configuration from pyproject.toml if present."""
    candidate = config_path or Path("pyproject.toml")
    if not candidate.is_file():
        return {}

    try:
        try:
            import tomllib  # Python 3.11+
            with open(candidate, "rb") as f:
                data = tomllib.load(f)
            tool_section = data.get("tool", {})
            return tool_section.get("markdown-deadlink-checker", {})
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
                with open(candidate, "rb") as f:
                    data = tomllib.load(f)
                tool_section = data.get("tool", {})
                return tool_section.get("markdown-deadlink-checker", {})
            except ImportError:
                return _parse_simple_toml(candidate.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_simple_toml(content: str) -> dict:
    """Robust fallback TOML section extractor for [tool.markdown-deadlink-checker]."""
    in_section = False
    result: dict = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sec_name = line[1:-1].strip()
            in_section = (sec_name == "tool.markdown-deadlink-checker")
            continue
        if in_section and "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [item.strip().strip("'\"") for item in val[1:-1].split(",") if item.strip()]
                result[key] = items
            elif val.lower() in ("true", "false"):
                result[key] = val.lower() == "true"
            elif val.isdigit():
                result[key] = int(val)
            else:
                result[key] = val.strip("'\"")
    return result


def parse_args(args: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="markdown-deadlink-checker",
        description="Verify relative file paths, image references, and heading anchor links in Markdown files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan current directory for dead links
  markdown-deadlink-checker

  # Scan a specific directory or file
  markdown-deadlink-checker docs/ README.md

  # Ignore specific paths and URLs
  markdown-deadlink-checker --ignore-path "legacy/**" --ignore-url "^https?://localhost"

  # Check external URLs as well
  markdown-deadlink-checker --check-external --external-timeout 10

  # Format output for GitHub Actions annotations
  markdown-deadlink-checker --format github
        """,
    )

    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="One or more markdown files or directories to scan (default: current directory).",
    )
    parser.add_argument(
        "--base-dir",
        "-b",
        type=Path,
        default=None,
        help="Base directory for absolute-like links starting with '/' (default: current working directory).",
    )
    parser.add_argument(
        "--ignore-path",
        action="append",
        default=[],
        help="Glob pattern for files or directories to ignore (e.g. 'vendor/**', 'docs/drafts/**'). Can be specified multiple times.",
    )
    parser.add_argument(
        "--ignore-url",
        action="append",
        default=[],
        help="Regex pattern for link URLs to ignore. Can be specified multiple times.",
    )
    parser.add_argument(
        "--check-external",
        action="store_true",
        help="Check external HTTP/HTTPS links over the network (default: disabled).",
    )
    parser.add_argument(
        "--external-timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds for external URL requests (default: 5.0).",
    )
    parser.add_argument(
        "--no-dir-links",
        dest="allow_directories",
        action="store_false",
        help="Disallow relative links that point to directories without an explicit file.",
    )
    parser.add_argument(
        "--require-exact-case",
        action="store_true",
        help="Enforce exact case match for file paths even on case-insensitive filesystems.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json", "github"],
        default="text",
        help="Output format: text (default), json, or github (GitHub Actions workflow annotations).",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to pyproject.toml configuration file.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information including valid and skipped links.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode: suppress summary and only output errors.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser.parse_args(args)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return e.code

    cfg = load_pyproject_config(args.config)

    ignore_paths = list(args.ignore_path)
    cfg_paths = cfg.get("ignore-paths") or cfg.get("ignore_paths")
    if cfg_paths:
        if isinstance(cfg_paths, list):
            ignore_paths.extend(cfg_paths)
        elif isinstance(cfg_paths, str):
            ignore_paths.append(cfg_paths)

    ignore_urls = list(args.ignore_url)
    cfg_urls = cfg.get("ignore-urls") or cfg.get("ignore_urls")
    if cfg_urls:
        if isinstance(cfg_urls, list):
            ignore_urls.extend(cfg_urls)
        elif isinstance(cfg_urls, str):
            ignore_urls.append(cfg_urls)

    check_external = args.check_external or cfg.get("check-external", False) or cfg.get("check_external", False)
    external_timeout = args.external_timeout if args.external_timeout != 5.0 else cfg.get("external-timeout", cfg.get("external_timeout", 5.0))
    allow_directories = args.allow_directories and cfg.get("allow-directories", cfg.get("allow_directories", True))
    require_exact_case = args.require_exact_case or cfg.get("require-exact-case", cfg.get("require_exact_case", False))

    checker = DeadLinkChecker(
        base_dir=args.base_dir,
        ignore_paths=ignore_paths,
        ignore_urls=ignore_urls,
        check_external=check_external,
        external_timeout=external_timeout,
        allow_directories=allow_directories,
        require_exact_case=require_exact_case,
    )

    summary = checker.scan(args.paths)

    if args.format == "json":
        print(format_json(summary))
    elif args.format == "github":
        print(format_github(summary))
    else:
        text_out = format_text(summary, sys.stdout, verbose=args.verbose, quiet=args.quiet)
        if text_out:
            print(text_out)

    return 1 if summary.has_dead_links else 0


if __name__ == "__main__":
    sys.exit(main())
