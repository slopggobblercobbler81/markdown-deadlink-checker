from pathlib import Path
import pytest
from markdown_deadlink_checker.models import LinkType
from markdown_deadlink_checker.parser import (
    classify_target,
    extract_anchors,
    mask_code_and_comments,
    parse_markdown,
)


def test_classify_target():
    # External
    assert classify_target("https://github.com")[0] == LinkType.EXTERNAL
    assert classify_target("http://localhost:8080")[0] == LinkType.EXTERNAL
    assert classify_target("//cdn.example.com/lib.js")[0] == LinkType.EXTERNAL

    # Special
    assert classify_target("mailto:user@example.com")[0] == LinkType.SPECIAL
    assert classify_target("tel:+123456789")[0] == LinkType.SPECIAL
    assert classify_target("javascript:void(0)")[0] == LinkType.SPECIAL

    # Same file anchor
    t, f, a = classify_target("#introduction")
    assert t == LinkType.SAME_FILE_ANCHOR
    assert f is None
    assert a == "introduction"

    # Cross file anchor
    t, f, a = classify_target("docs/guide.md#installation")
    assert t == LinkType.CROSS_FILE_ANCHOR
    assert f == "docs/guide.md"
    assert a == "installation"

    # Relative file
    t, f, a = classify_target("docs/guide.md")
    assert t == LinkType.RELATIVE_FILE
    assert f == "docs/guide.md"
    assert a is None

    # Image
    t, f, a = classify_target("assets/logo.png", is_image=True)
    assert t == LinkType.IMAGE
    assert f == "assets/logo.png"


def test_mask_code_and_comments():
    md = """
Before code.
```python
# [not a link](docs/fake.md)
print("hello")
```
After code.
<!-- [hidden link](secret.md) -->
Inline `[also not link](fake2.md)` here.
Valid [real link](real.md).
"""
    masked = mask_code_and_comments(md)
    assert "[not a link]" not in masked
    assert "[hidden link]" not in masked
    assert "[also not link]" not in masked
    assert "[real link](real.md)" in masked


def test_extract_anchors():
    md = """
# Main Title
## Section 1
Text here.
### Section 1
<h2 id="html-heading">HTML Heading</h2>
<div id="div-anchor">Content</div>
<a name="old-anchor"></a>
"""
    anchors = extract_anchors(md)
    assert anchors.contains("main-title")
    assert anchors.contains("section-1")
    assert anchors.contains("section-1-1")  # disambiguated
    assert anchors.contains("html-heading")
    assert anchors.contains("div-anchor")
    assert anchors.contains("old-anchor")


def test_parse_markdown_links():
    md = """# Sample

Check [Guide](docs/guide.md) and [Anchor](#sample).
Image: ![Logo](img/logo.png)
Reference: [Ref Link][my-ref]
HTML: <a href="about.md#team">Team</a>
HTML Img: <img src="icons/check.svg">

[my-ref]: docs/reference.md
"""
    doc = parse_markdown(md, Path("test.md"))
    assert len(doc.links) == 6

    # 1. Guide
    assert doc.links[0].text == "Guide"
    assert doc.links[0].file_path == "docs/guide.md"
    assert doc.links[0].link_type == LinkType.RELATIVE_FILE
    assert doc.links[0].line == 3

    # 2. Anchor
    assert doc.links[1].text == "Anchor"
    assert doc.links[1].anchor == "sample"
    assert doc.links[1].link_type == LinkType.SAME_FILE_ANCHOR

    # 3. Image
    assert doc.links[2].text == "Logo"
    assert doc.links[2].file_path == "img/logo.png"
    assert doc.links[2].link_type == LinkType.IMAGE
    assert doc.links[2].is_image is True

    # 4. Ref Link
    assert doc.links[3].text == "Ref Link"
    assert doc.links[3].file_path == "docs/reference.md"

    # 5. HTML link
    assert doc.links[4].file_path == "about.md"
    assert doc.links[4].anchor == "team"
    assert doc.links[4].link_type == LinkType.CROSS_FILE_ANCHOR

    # 6. HTML img
    assert doc.links[5].file_path == "icons/check.svg"
    assert doc.links[5].is_image is True
