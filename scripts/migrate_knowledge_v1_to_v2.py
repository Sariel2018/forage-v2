#!/usr/bin/env python3
"""Migrate v1 knowledge (single file) to v2 format (individual .md files)."""

import re
import shutil
from pathlib import Path

UNIVERSAL_ENTRIES = {
    7: "connection_pool_avalanche",
    8: "retry_strategy",
    9: "prevent_system_sleep",
    15: "deduplication",
    17: "concurrent_workers",
    18: "thread_safe_io",
    19: "stagger_worker_startup",
    20: "incremental_runs",
    21: "jsonl_storage",
    22: "broad_filters",
    23: "unified_script",
    24: "log_decisions",
    25: "ssl_diagnose",
    26: "proxy_check",
    27: "connectivity_test",
}

WEB_SCRAPING_ENTRIES = {
    1: "archive_org_goldmine",
    2: "cdx_api_enumeration",
    3: "cdx_truncation",
    4: "cdx_timestamp_filter",
    5: "cdx_snapshot_fallback",
    6: "archive_rate_limit",
    10: "url_format_evolution",
    11: "url_deduplication_by_slug",
    12: "html_meta_dates_unreliable",
    13: "html_extraction_fallback",
    14: "boilerplate_removal",
    16: "date_recovery_multi_source",
}


def migrate():
    knowledge_dir = Path("knowledge")
    source = knowledge_dir / "web_scraping.md"

    if not source.is_file():
        print("knowledge/web_scraping.md not found")
        return

    # Backup original
    shutil.copy(source, source.with_suffix(".md.v1backup"))

    # Parse entries
    text = source.read_text()
    entries = re.split(r"\n(?=\d+\.\s\*\*)", text)
    header = entries[0]  # noqa: F841
    entries = entries[1:]

    print(f"Found {len(entries)} entries")

    # Create directories
    (knowledge_dir / "universal").mkdir(exist_ok=True)
    (knowledge_dir / "web_scraping").mkdir(exist_ok=True)
    (knowledge_dir / "api").mkdir(exist_ok=True)
    (knowledge_dir / "tasks").mkdir(exist_ok=True)

    for entry_text in entries:
        match = re.match(r"(\d+)\.\s\*\*(.*?)\*\*", entry_text)
        if not match:
            continue
        num = int(match.group(1))
        title = match.group(2).strip().rstrip(".")

        if num in UNIVERSAL_ENTRIES:
            scope = "universal"
            entry_id = UNIVERSAL_ENTRIES[num]
        elif num in WEB_SCRAPING_ENTRIES:
            scope = "web_scraping"
            entry_id = WEB_SCRAPING_ENTRIES[num]
        else:
            scope = "universal"
            entry_id = f"entry_{num}"

        summary = title

        content = (
            f"---\n"
            f"id: {entry_id}\n"
            f"scope: {scope}\n"
            f"type: advisory\n"
            f"verified: true\n"
            f"source_tasks: [fa_2018_2020, whitehouse_trump2]\n"
            f'summary: "{summary}"\n'
            f"---\n\n"
            f"# {title}\n\n"
            f"{entry_text.strip()}\n"
        )

        path = knowledge_dir / scope / f"{entry_id}.md"
        path.write_text(content)
        print(f"  [{scope}] {entry_id}.md")

    from forage.core.knowledge import regenerate_index
    regenerate_index(knowledge_dir)
    print(f"\nINDEX.md generated")
    print(f"Original backed up to {source.with_suffix('.md.v1backup')}")


if __name__ == "__main__":
    migrate()
