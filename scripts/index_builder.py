"""
Index Builder - Deterministic utility to rebuild knowledge/index.md from articles.

Scans all articles in knowledge/, parses frontmatter, and rebuilds the index.
No LLM calls, idempotent, can be run anytime.

Usage:
    uv run python index_builder.py              # rebuild index.md
    uv run python index_builder.py --dry-run    # preview what would be built
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

from config import KNOWLEDGE_DIR, ROOT_DIR, now_iso
from utils import list_wiki_articles


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from article content.

    Returns dict with keys: title, summary, created, updated, etc.
    """
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    frontmatter_text = match.group(1)
    parsed = {}
    current_key = None
    list_values: list[str] = []

    for line in frontmatter_text.split("\n"):
        if line.startswith("  - "):
            # List item under current key
            if current_key:
                list_values.append(line.strip("- ").strip().strip('"\''))
            continue

        if ":" in line and not line.startswith(" "):
            # Save previous list key if any
            if current_key and list_values:
                parsed[current_key] = ", ".join(list_values)
                list_values = []

            key, value = line.split(":", 1)
            current_key = key.strip().lower()
            value = value.strip().strip('"\'')
            if value:
                parsed[current_key] = value
                current_key = None  # Not expecting a list

    # Save last list key if any
    if current_key and list_values:
        parsed[current_key] = ", ".join(list_values)

    return parsed


def extract_title_from_content(content: str) -> Optional[str]:
    """Extract title from article (first H1 heading)."""
    match = re.search(r"^# (.+)$", content, re.MULTILINE)
    return match.group(1) if match else None


def extract_summary(frontmatter: dict, content: str, title: str) -> str:
    """Extract or generate summary for index entry."""
    # Prefer frontmatter summary if available
    if "summary" in frontmatter:
        return frontmatter["summary"]

    # Otherwise, use first paragraph after H1 (max 80 chars)
    lines = content.split("\n")
    in_summary = False
    summary_lines = []

    for line in lines:
        # Skip header and frontmatter
        if line.startswith("---") or line.startswith("#"):
            if line.startswith("# "):
                in_summary = True
            continue

        if in_summary and line.strip():
            summary_lines.append(line.strip())
            if len("\n".join(summary_lines)) > 80:
                break

    summary = "\n".join(summary_lines)
    if len(summary) > 80:
        summary = summary[:77] + "..."

    return summary or "[No summary available]"


def get_article_path_for_index(article_path: Path) -> str:
    """Convert article path to wikilink format for index.

    Example: knowledge/concepts/foo.md -> concepts/foo
    """
    rel = article_path.relative_to(KNOWLEDGE_DIR)
    return str(rel).replace(".md", "").replace("\\", "/")


def build_index() -> list[dict]:
    """Scan knowledge/ and build list of index entries.

    Returns list of dicts with keys: path, title, summary, updated
    """
    articles = list_wiki_articles()
    entries = []

    for article_path in articles:
        try:
            content = article_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)
            title = frontmatter.get("title") or extract_title_from_content(content)

            if not title:
                print(f"  Warning: No title found in {article_path.relative_to(KNOWLEDGE_DIR)}")
                continue

            summary = extract_summary(frontmatter, content, title)
            updated = frontmatter.get("updated", "unknown")
            sources = frontmatter.get("sources", "—")
            wikilink_path = get_article_path_for_index(article_path)

            entries.append({
                "path": wikilink_path,
                "title": title,
                "summary": summary,
                "sources": sources,
                "updated": updated,
            })
        except Exception as e:
            print(f"  Error processing {article_path.relative_to(KNOWLEDGE_DIR)}: {e}")
            continue

    # Sort by category, then by name
    # Preserve order: concepts, entities, connections, sources, notes, qa
    category_order = {"concepts": 0, "entities": 1, "connections": 2, "sources": 3, "notes": 4, "qa": 5}

    def sort_key(entry: dict) -> tuple:
        path = entry["path"]
        category = path.split("/")[0] if "/" in path else "other"
        order = category_order.get(category, 999)
        return (order, path)

    entries.sort(key=sort_key)
    return entries


def write_index(entries: list[dict]) -> str:
    """Write index entries to markdown table format."""
    timestamp = now_iso()

    lines = [
        "# Knowledge Base Index",
        "",
        "| Article | Summary | Compiled From | Updated |",
        "|---------|---------|---------------|---------|",
    ]

    for entry in entries:
        path_link = f"[[{entry['path']}]]"
        summary = entry["summary"].replace("|", "\\|")
        sources = entry.get("sources", "—")
        updated = entry["updated"]

        lines.append(f"| {path_link} | {summary} | {sources} | {updated} |")

    lines.extend([
        "",
        f"_Index last rebuilt: {timestamp}_",
        "",
    ])

    return "\n".join(lines)


def rebuild_index(dry_run: bool = False) -> None:
    """Scan knowledge/ and rebuild knowledge/index.md."""
    index_path = KNOWLEDGE_DIR / "index.md"

    print("Building index...")
    entries = build_index()

    if not entries:
        print("  No articles found to index.")
        return

    index_content = write_index(entries)

    if dry_run:
        print(f"\n[DRY RUN] Would write {index_path.relative_to(ROOT_DIR)} with {len(entries)} entries:")
        print(index_content)
    else:
        index_path.write_text(index_content, encoding="utf-8")
        print(f"  Wrote {index_path.relative_to(ROOT_DIR)} with {len(entries)} entries")


def main():
    parser = argparse.ArgumentParser(description="Rebuild knowledge base index deterministically")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    rebuild_index(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
