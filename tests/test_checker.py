import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from markdown_deadlink_checker.checker import DeadLinkChecker
from markdown_deadlink_checker.models import CheckStatus


@pytest.fixture
def workspace(tmp_path: Path):
    """Creates a temporary workspace with files and folders for testing."""
    # Structure:
    # workspace/
    #   README.md
    #   docs/
    #     guide.md
    #     images/
    #       logo.png
    #   sub/
    #     README.md
    
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    images_dir = docs_dir / "images"
    images_dir.mkdir()
    (images_dir / "logo.png").write_bytes(b"PNG_DATA")

    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    (sub_dir / "README.md").write_text("# Sub Readme\n## Subtopic\nContent\n", encoding="utf-8")

    (docs_dir / "guide.md").write_text(
        """# User Guide
## Getting Started
Welcome!

See [Root Readme](../README.md#welcome) and [Logo](images/logo.png).
Broken cross-anchor: [Missing Section](../README.md#non-existent).
Broken file: [Missing File](does_not_exist.md).
""",
        encoding="utf-8",
    )

    (tmp_path / "README.md").write_text(
        """# Welcome
## Installation
Run pip install.

Links:
- [Guide](docs/guide.md)
- [Guide Heading](docs/guide.md#getting-started)
- [Same Anchor](#installation)
- [Dead Anchor](#does-not-exist)
- [Sub Dir](sub/)
- [Sub Anchor](sub/#subtopic)
- [External](https://example.com)
- [Email](mailto:hello@example.com)
""",
        encoding="utf-8",
    )

    return tmp_path


def test_checker_valid_and_dead_links(workspace: Path):
    checker = DeadLinkChecker(base_dir=workspace)
    readme = workspace / "README.md"
    summary = checker.scan([readme])

    assert summary.files_scanned == 1
    assert summary.total_links == 8

    # Check status by target
    results_map = {r.link.raw_target: r for r in summary.results}

    assert results_map["docs/guide.md"].status == CheckStatus.VALID
    assert results_map["docs/guide.md#getting-started"].status == CheckStatus.VALID
    assert results_map["#installation"].status == CheckStatus.VALID
    assert results_map["#does-not-exist"].status == CheckStatus.DEAD_ANCHOR
    assert results_map["sub/"].status == CheckStatus.VALID
    assert results_map["sub/#subtopic"].status == CheckStatus.VALID
    assert results_map["https://example.com"].status == CheckStatus.SKIPPED
    assert results_map["mailto:hello@example.com"].status == CheckStatus.SKIPPED

    assert summary.dead_links == 1


def test_checker_cross_file_dead_links(workspace: Path):
    checker = DeadLinkChecker(base_dir=workspace)
    guide = workspace / "docs" / "guide.md"
    summary = checker.scan([guide])

    assert summary.files_scanned == 1
    results_map = {r.link.raw_target: r for r in summary.results}

    assert results_map["../README.md#welcome"].status == CheckStatus.VALID
    assert results_map["images/logo.png"].status == CheckStatus.VALID
    assert results_map["../README.md#non-existent"].status == CheckStatus.DEAD_ANCHOR
    assert results_map["does_not_exist.md"].status == CheckStatus.DEAD_FILE

    assert summary.dead_links == 2


def test_checker_ignore_rules(workspace: Path):
    checker = DeadLinkChecker(
        base_dir=workspace,
        ignore_urls=[r"^https://example\.com"],
        ignore_paths=["docs/**"],
    )

    files = checker.discover_files([workspace])
    # docs/guide.md should be ignored
    assert workspace / "docs" / "guide.md" not in files
    assert workspace / "README.md" in files

    summary = checker.scan([workspace / "README.md"])
    results_map = {r.link.raw_target: r for r in summary.results}
    assert results_map["https://example.com"].status == CheckStatus.IGNORED


def test_checker_external_links(workspace: Path):
    checker = DeadLinkChecker(base_dir=workspace, check_external=True)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        readme = workspace / "README.md"
        summary = checker.scan([readme])
        results_map = {r.link.raw_target: r for r in summary.results}
        assert results_map["https://example.com"].status == CheckStatus.EXTERNAL_VALID


def test_checker_base_dir_resolution(tmp_path: Path):
    (tmp_path / "root.md").write_text("# Root\nContent\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    doc = sub / "doc.md"
    doc.write_text("[Root](/root.md)\n[Missing](/missing.md)", encoding="utf-8")

    checker = DeadLinkChecker(base_dir=tmp_path)
    summary = checker.scan([doc])
    results_map = {r.link.raw_target: r for r in summary.results}

    assert results_map["/root.md"].status == CheckStatus.VALID
    assert results_map["/missing.md"].status == CheckStatus.DEAD_FILE
