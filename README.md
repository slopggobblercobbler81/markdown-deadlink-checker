# markdown-deadlink-checker

[![CI](https://github.com/slopggobblercobbler81/markdown-deadlink-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/slopggobblercobbler81/markdown-deadlink-checker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)

> Production-grade, zero-dependency Markdown dead link and broken anchor validator for local development and CI/CD pipelines.

`markdown-deadlink-checker` scans your Markdown files and documentation to ensure all internal links stay healthy. It verifies:
- **Relative file paths** (e.g. `[Guide](docs/guide.md)`, `[Config](../config.json)`)
- **Image references** (e.g. `![Architecture](assets/arch.png)`, `<img src="...">`)
- **Same-file heading anchors** (e.g. `[Setup](#setup-instructions)`)
- **Cross-file heading anchors** (e.g. `[Prerequisites](install.md#prerequisites)`)
- **HTML anchors** (`<a id="...">`, `<a name="...">`, and element IDs)
- **Reference-style links** (`[link][ref]` and `[ref]: url`)
- **Optional external URL validation** (HTTP/HTTPS HEAD & GET checks)

---

## Features

- ⚡ **Zero External Dependencies**: Fast startup, runs on standard Python 3.8+.
- 🎯 **GitHub Flavored Markdown (GFM) Anchor Slugs**: Accurate heading slugification including punctuation stripping, unicode handling, and duplicate slug disambiguation (`#section`, `#section-1`).
- 🛡️ **Intelligent Code Masking**: Ignores code fences (```` ``` ````, `~~~`) and inline code (`` `...` ``) to prevent false positives.
- 🤖 **Native GitHub Actions Support**: Output format `github` automatically emits `::error file=...::` annotations directly onto your pull request diffs.
- ⚙️ **Configurable**: Ignore specific paths (`--ignore-path`) or URLs (`--ignore-url`), enforce exact case sensitivity, or configure via `pyproject.toml`.

---

## Installation

Install using `pip`:

```bash
pip install markdown-deadlink-checker
```

Or install in development mode from source:

```bash
git clone https://github.com/slopggobblercobbler81/markdown-deadlink-checker.git
cd markdown-deadlink-checker
pip install -e .
```

---

## Usage

### Quick Start

Scan the current directory recursively:

```bash
markdown-deadlink-checker
```

Scan specific files or folders:

```bash
markdown-deadlink-checker docs/ README.md CONTRIBUTING.md
```

### CLI Options

| Flag | Short | Description |
|---|---|---|
| `paths` | | One or more files or directories to scan (default: `.`) |
| `--base-dir` | `-b` | Base directory for absolute-style links starting with `/` |
| `--ignore-path` | | Glob pattern for files/directories to skip (e.g. `vendor/**`) |
| `--ignore-url` | | Regex pattern for link URLs to ignore (e.g. `^https?://localhost`) |
| `--check-external` | | Enable network checking for external HTTP/HTTPS links |
| `--external-timeout`| | Timeout in seconds for external requests (default: `5.0`) |
| `--no-dir-links` | | Disallow relative links pointing to folders without a file |
| `--require-exact-case` | | Enforce exact case matching on case-insensitive filesystems |
| `--format` | `-f` | Output format: `text` (default), `json`, or `github` |
| `--config` | `-c` | Path to custom `pyproject.toml` |
| `--verbose` | `-v` | Show detailed output including valid and skipped links |
| `--quiet` | `-q` | Suppress summary, outputting only dead link errors |
| `--version` | | Show program version and exit |

---

## Configuration via `pyproject.toml`

You can declare project-wide defaults in your repository's `pyproject.toml`:

```toml
[tool.markdown-deadlink-checker]
ignore-paths = [
    "docs/legacy/**",
    "vendor/**"
]
ignore-urls = [
    "^https?://localhost",
    "^https?://127\\.0\\.0\\.1",
    "^mailto:"
]
check-external = false
require-exact-case = true
```

---

## CI / GitHub Actions Integration

Add `markdown-deadlink-checker` to your GitHub Actions workflow for automated PR validation:

```yaml
name: Documentation Linting

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  check-links:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install checker
        run: pip install markdown-deadlink-checker

      - name: Validate Markdown Links
        run: markdown-deadlink-checker --format github .
```

When a dead link is detected in a pull request, GitHub Actions will annotate the exact file and line number:

```text
::error file=docs/setup.md,line=42,col=15::Dead link 'guides/faq.md#troubleshooting': Anchor '#troubleshooting' not found in faq.md
```

---

## Output Examples

### Human-readable Terminal Output

```text
=== Markdown Deadlink Checker ===

Found 1 dead link(s):

File: docs/setup.md
  [DEAD]   line 42:15 -> guides/faq.md#troubleshooting (FAQ Guide)
         Error: Anchor '#troubleshooting' not found in faq.md
         Available anchors: #overview, #installation, #faq-answers

--------------------------------------------------
Result: FAILURE
Files scanned:   18
Total links:     74
Valid links:     71
Dead links:      1
Ignored/Skipped: 2
--------------------------------------------------
```

### JSON Output (`--format json`)

```json
{
  "status": "failure",
  "summary": {
    "files_scanned": 18,
    "total_links": 74,
    "valid_links": 71,
    "dead_links": 1,
    "ignored_links": 2
  },
  "errors": [],
  "results": [
    {
      "source_file": "docs/setup.md",
      "line": 42,
      "column": 15,
      "target": "guides/faq.md#troubleshooting",
      "text": "FAQ Guide",
      "is_image": false,
      "status": "dead_anchor",
      "message": "Anchor '#troubleshooting' not found in faq.md",
      "resolved_path": "docs/guides/faq.md",
      "available_anchors": ["overview", "installation", "faq-answers"]
    }
  ]
}
```

---

## Local Development & Testing

Run tests with `pytest`:

```bash
pip install -e .[dev]
pytest
```

---

## License

This project is licensed under the [MIT License](LICENSE).
