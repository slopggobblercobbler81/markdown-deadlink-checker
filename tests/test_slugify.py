import pytest
from markdown_deadlink_checker.slugify import DocumentAnchors, slugify_heading, strip_markdown


def test_strip_markdown():
    assert strip_markdown("Plain text") == "Plain text"
    assert strip_markdown("**Bold** and *Italic*") == "Bold and Italic"
    assert strip_markdown("`code block` inside") == "code block inside"
    assert strip_markdown("[Link Text](http://example.com)") == "Link Text"
    assert strip_markdown("![Alt Image](pic.png) subtitle") == "Alt Image subtitle"
    assert strip_markdown("<span>HTML Tag</span>") == "HTML Tag"


def test_slugify_heading_basic():
    assert slugify_heading("Hello World") == "hello-world"
    assert slugify_heading("What's up?") == "whats-up"
    assert slugify_heading("Section 1.2.3") == "section-123"
    assert slugify_heading("C++ & C#") == "c--c"
    assert slugify_heading("Leading and Trailing   ") == "leading-and-trailing"


def test_slugify_heading_custom_id():
    assert slugify_heading("Overview {#intro-sec}") == "overview"
    assert slugify_heading("API Docs {#custom-api}   ") == "api-docs"


def test_slugify_disambiguation():
    counts = {}
    assert slugify_heading("Introduction", counts) == "introduction"
    assert slugify_heading("Introduction", counts) == "introduction-1"
    assert slugify_heading("Introduction", counts) == "introduction-2"
    assert slugify_heading("Details", counts) == "details"
    assert slugify_heading("Details", counts) == "details-1"


def test_document_anchors():
    doc = DocumentAnchors()
    s1 = doc.add_heading("Getting Started")
    assert s1 == "getting-started"
    assert doc.contains("getting-started")
    assert doc.contains("#getting-started")
    assert doc.contains("GETTING-STARTED")

    # Custom anchor
    doc.add_heading("Configuration {#config-opt}")
    assert doc.contains("config-opt")
    assert doc.contains("configuration")

    # Explicit HTML anchor
    doc.add_anchor("manual-anchor")
    assert doc.contains("manual-anchor")
    assert doc.contains("#manual-anchor")

    # URL encoded / unicode anchor
    doc.add_heading("Café & Food")
    assert doc.contains("cafe-food") or doc.contains("café-food") or doc.contains("café--food") or doc.contains("cafe--food")

    assert not doc.contains("non-existent-anchor")


def test_slugify_consecutive_symbols():
    assert slugify_heading('Foo -- Bar -> Baz') == 'foo----bar---baz'

