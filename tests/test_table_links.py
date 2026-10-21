from pathlib import Path
import pytest
from markdown_deadlink_checker.models import LinkType
from markdown_deadlink_checker.parser import parse_markdown


def test_table_links_extraction():
    md = """# Table Links Test

| Column 1 | Column 2 |
| --- | --- |
| [Link In Table](docs/guide.md) | [Anchor In Table](#section) |
| ![Image In Table](assets/logo.png) | [External](https://example.com) |
"""
    doc = parse_markdown(md, Path("table_test.md"))
    
    # Verify that links inside table cells are successfully parsed and extracted
    assert len(doc.links) >= 4
    
    # 1. Relative file link inside table
    link1 = next((l for l in doc.links if l.text == "Link In Table"), None)
    assert link1 is not None
    assert link1.file_path == "docs/guide.md"
    assert link1.link_type == LinkType.RELATIVE_FILE

    # 2. Anchor link inside table
    link2 = next((l for l in doc.links if l.text == "Anchor In Table"), None)
    assert link2 is not None
    assert link2.anchor == "section"
    assert link2.link_type == LinkType.SAME_FILE_ANCHOR

    # 3. Image inside table
    link3 = next((l for l in doc.links if l.text == "Image In Table"), None)
    assert link3 is not None
    assert link3.file_path == "assets/logo.png"
    assert link3.link_type == LinkType.IMAGE
    assert link3.is_image is True

    # 4. External link inside table
    link4 = next((l for l in doc.links if l.text == "External"), None)
    assert link4 is not None
    assert link4.raw_target == "https://example.com"
    assert link4.link_type == LinkType.EXTERNAL
