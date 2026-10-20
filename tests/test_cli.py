import json
from pathlib import Path
import pytest
from markdown_deadlink_checker.cli import main, parse_args


def test_cli_help(capsys):
    code = main(["--help"])
    assert code == 0
    captured = capsys.readouterr()
    assert "markdown-deadlink-checker" in captured.out
    assert "--ignore-path" in captured.out


def test_cli_success(tmp_path: Path, capsys):
    doc = tmp_path / "valid.md"
    doc.write_text("# Hello\n\nLink to [Self](#hello)\n", encoding="utf-8")

    code = main([str(doc)])
    assert code == 0
    captured = capsys.readouterr()
    assert "SUCCESS" in captured.out
    assert "Dead links:      0" in captured.out


def test_cli_failure(tmp_path: Path, capsys):
    doc = tmp_path / "broken.md"
    doc.write_text("# Hello\n\nLink to [Dead](#nonexistent)\n", encoding="utf-8")

    code = main([str(doc)])
    assert code == 1
    captured = capsys.readouterr()
    assert "FAILURE" in captured.out
    assert "nonexistent" in captured.out


def test_cli_json_format(tmp_path: Path, capsys):
    doc = tmp_path / "broken.md"
    doc.write_text("[Dead File](missing.md)", encoding="utf-8")

    code = main([str(doc), "--format", "json"])
    assert code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "failure"
    assert data["summary"]["dead_links"] == 1


def test_cli_github_format(tmp_path: Path, capsys):
    doc = tmp_path / "broken.md"
    doc.write_text("[Dead](nope.md)", encoding="utf-8")

    code = main([str(doc), "--format", "github"])
    assert code == 1
    captured = capsys.readouterr()
    assert "::error file=" in captured.out


def test_cli_config_toml(tmp_path: Path, capsys):
    doc = tmp_path / "test.md"
    doc.write_text("[Ignored](legacy/old.md)", encoding="utf-8")

    config = tmp_path / "pyproject.toml"
    config.write_text(
        """[tool.markdown-deadlink-checker]
ignore-paths = ["legacy/**"]
""",
        encoding="utf-8",
    )

    code = main([str(doc), "--config", str(config)])
    assert code == 0
