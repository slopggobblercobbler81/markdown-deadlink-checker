import io
import json
from pathlib import Path
from markdown_deadlink_checker.models import (
    CheckResult,
    CheckStatus,
    LinkTarget,
    LinkType,
    ScanSummary,
)
from markdown_deadlink_checker.reporter import (
    format_github,
    format_json,
    format_text,
)


def sample_summary() -> ScanSummary:
    target1 = LinkTarget(
        raw_target="docs/setup.md#missing-step",
        file_path="docs/setup.md",
        anchor="missing-step",
        link_type=LinkType.CROSS_FILE_ANCHOR,
        line=12,
        column=5,
        source_file=Path("README.md"),
        text="Setup Step",
    )
    result1 = CheckResult(
        link=target1,
        status=CheckStatus.DEAD_ANCHOR,
        message="Anchor '#missing-step' not found in docs/setup.md",
        available_anchors=["install", "usage"],
    )

    target2 = LinkTarget(
        raw_target="docs/guide.md",
        file_path="docs/guide.md",
        anchor=None,
        link_type=LinkType.RELATIVE_FILE,
        line=20,
        column=1,
        source_file=Path("README.md"),
        text="Guide",
    )
    result2 = CheckResult(
        link=target2,
        status=CheckStatus.VALID,
        message="Target file exists",
    )

    return ScanSummary(
        files_scanned=2,
        total_links=2,
        valid_links=1,
        dead_links=1,
        ignored_links=0,
        results=[result1, result2],
    )


def test_format_text():
    summary = sample_summary()
    output = format_text(summary, stream=io.StringIO(), verbose=True)
    assert "Found 1 dead link(s)" in output
    assert "README.md" in output
    assert "missing-step" in output
    assert "Valid links (1):" in output
    assert "Result: FAILURE" in output


def test_format_json():
    summary = sample_summary()
    output = format_json(summary)
    parsed = json.loads(output)
    assert parsed["status"] == "failure"
    assert parsed["summary"]["total_links"] == 2
    assert parsed["summary"]["dead_links"] == 1
    assert len(parsed["results"]) == 2
    assert parsed["results"][0]["status"] == "dead_anchor"


def test_format_github():
    summary = sample_summary()
    output = format_github(summary)
    assert "::error file=" in output
    assert "line=12,col=5" in output
    assert "Dead link 'docs/setup.md#missing-step'" in output
