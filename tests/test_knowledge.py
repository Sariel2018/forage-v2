# tests/test_knowledge.py
import tempfile
from pathlib import Path
from forage.core.knowledge import generate_index, parse_frontmatter


def test_generate_index_empty():
    """Empty knowledge dir produces empty index."""
    with tempfile.TemporaryDirectory() as d:
        index = generate_index(Path(d))
        assert "0 entries" in index or "(empty)" in index


def test_generate_index_with_files():
    """Index lists all .md files with summaries."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "universal").mkdir()
        (p / "universal" / "proxy_check.md").write_text(
            "---\nid: proxy_check\nscope: universal\nsummary: Check HTTPS_PROXY\n---\nContent here."
        )
        index = generate_index(p)
        assert "proxy_check" in index
        assert "Check HTTPS_PROXY" in index
        assert "Universal" in index


def test_parse_frontmatter():
    """Frontmatter is correctly parsed from .md files."""
    text = "---\nid: test\nscope: universal\nsummary: A test\n---\nBody."
    fm = parse_frontmatter(text)
    assert fm["id"] == "test"
    assert fm["scope"] == "universal"
    assert fm["summary"] == "A test"
