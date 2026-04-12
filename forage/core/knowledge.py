# forage/core/knowledge.py
"""Knowledge base management: INDEX generation, frontmatter parsing, file I/O."""

import re
from collections import defaultdict
from pathlib import Path


def parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def generate_index(knowledge_dir: Path) -> str:
    """Generate INDEX.md from all .md files in knowledge_dir.

    Pure function: same input files -> same output string.
    """
    by_scope = defaultdict(list)

    for scope_dir in sorted(knowledge_dir.iterdir()):
        if not scope_dir.is_dir() or scope_dir.name.startswith("."):
            continue
        for f in sorted(scope_dir.glob("*.md")):
            text = f.read_text()
            fm = parse_frontmatter(text)
            by_scope[scope_dir.name].append({
                "id": fm.get("id", f.stem),
                "path": f"{scope_dir.name}/{f.name}",
                "summary": fm.get("summary", "(no summary)"),
            })

    lines = [
        "# Knowledge Base Index\n",
        "This is the catalog of accumulated experience.",
        "To read details, use the Read tool on the file path.\n",
    ]

    if not by_scope:
        lines.append("(empty)\n")
        return "\n".join(lines)

    for scope in sorted(by_scope.keys()):
        entries = by_scope[scope]
        lines.append(f"## {scope.replace('_', ' ').title()} ({len(entries)} entries)\n")
        for entry in entries:
            lines.append(f"- [{entry['id']}]({entry['path']}) -- {entry['summary']}")
        lines.append("")

    return "\n".join(lines)


def write_knowledge_entry(
    knowledge_dir: Path,
    entry: dict,
) -> Path:
    """Write a single knowledge entry as a .md file.

    entry should have: id, scope, type, summary, content, source_tasks
    Returns the path of the written file.
    """
    scope = entry.get("scope", "universal")
    scope_dir = knowledge_dir / scope
    scope_dir.mkdir(parents=True, exist_ok=True)

    file_id = entry["id"]
    path = scope_dir / f"{file_id}.md"

    frontmatter = (
        f"---\n"
        f"id: {file_id}\n"
        f"scope: {scope}\n"
        f"type: {entry.get('type', 'advisory')}\n"
        f"verified: false\n"
        f"source_tasks: {entry.get('source_tasks', [])}\n"
        f"summary: \"{entry.get('summary', '')}\"\n"
        f"---\n\n"
    )

    path.write_text(frontmatter + entry.get("content", ""))
    return path


def regenerate_index(knowledge_dir: Path) -> Path:
    """Regenerate INDEX.md in the knowledge directory."""
    index_content = generate_index(knowledge_dir)
    index_path = knowledge_dir / "INDEX.md"
    index_path.write_text(index_content)
    return index_path
