# tests/test_knowledge.py
import tempfile
from pathlib import Path
from forage.core.knowledge import generate_index, parse_frontmatter, write_knowledge_entry


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


# --- Append-only tests ------------------------------------------------


def test_append_only_first_write():
    """First write with a given id creates <id>.md."""
    with tempfile.TemporaryDirectory() as d:
        kd = Path(d)
        entry = {
            "id": "foo",
            "scope": "universal",
            "summary": "v1 observation",
            "content": "Content version 1",
        }
        p = write_knowledge_entry(kd, entry)
        assert p.name == "foo.md"
        assert (kd / "universal" / "foo.md").is_file()
        assert "Content version 1" in p.read_text()


def test_append_only_auto_versions_on_collision():
    """Same id writes DO NOT overwrite — auto-versioned to _v2, _v3, ..."""
    with tempfile.TemporaryDirectory() as d:
        kd = Path(d)
        entry = {"id": "foo", "scope": "universal", "summary": "s", "content": "v1"}

        p1 = write_knowledge_entry(kd, entry)
        assert p1.name == "foo.md"

        entry["content"] = "v2"
        p2 = write_knowledge_entry(kd, entry)
        assert p2.name == "foo_v2.md"

        entry["content"] = "v3"
        p3 = write_knowledge_entry(kd, entry)
        assert p3.name == "foo_v3.md"

        # All three files coexist
        assert p1.is_file() and p2.is_file() and p3.is_file()
        # Original content preserved (no overwrite)
        assert "v1" in p1.read_text()
        assert "v2" in p2.read_text()
        assert "v3" in p3.read_text()


def test_append_only_frontmatter_reflects_version():
    """Versioned entries have their id in frontmatter updated to the versioned form."""
    with tempfile.TemporaryDirectory() as d:
        kd = Path(d)
        entry = {"id": "foo", "scope": "universal", "summary": "s", "content": "c"}

        write_knowledge_entry(kd, entry)
        p2 = write_knowledge_entry(kd, entry)

        fm = parse_frontmatter(p2.read_text())
        assert fm["id"] == "foo_v2"


def test_append_only_different_scopes_dont_collide():
    """Same id in different scopes coexist without versioning (scope-namespaced)."""
    with tempfile.TemporaryDirectory() as d:
        kd = Path(d)
        e_univ = {"id": "foo", "scope": "universal", "summary": "s", "content": "universal content"}
        e_api = {"id": "foo", "scope": "api", "summary": "s", "content": "api content"}

        p1 = write_knowledge_entry(kd, e_univ)
        p2 = write_knowledge_entry(kd, e_api)

        # Both write as <scope>/foo.md (no versioning needed)
        assert p1.name == "foo.md"
        assert p2.name == "foo.md"
        assert p1.parent.name == "universal"
        assert p2.parent.name == "api"
