from markdown_deadlink_checker.checker import MARKDOWN_EXTENSIONS

def test_mdx_extension_supported():
    assert ".mdx" in MARKDOWN_EXTENSIONS
