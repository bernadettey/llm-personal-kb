"""
Wiki Builder - Convert raw source files to structured knowledge articles.

Reads .txt and .md files from raw/, generates knowledge/sources/ articles,
then uses LLM to extract concepts, entities, and connections.

Usage:
    uv run python wiki_builder.py              # process all raw files
    uv run python wiki_builder.py --file raw/papers/xxx.md  # process specific file
    uv run python wiki_builder.py --dry-run    # show what would be processed
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime

from config import AGENTS_FILE, RAW_DIR, SOURCES_DIR, KNOWLEDGE_DIR, now_iso
from utils import (
    file_hash,
    list_wiki_articles,
    load_state,
    read_wiki_index,
    save_state,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def slugify(name: str) -> str:
    """Convert filename to slug."""
    return name.lower().replace(" ", "-").replace(".md", "").replace(".txt", "")


def generate_source_article(raw_file: Path) -> str:
    """Generate a knowledge/sources/ article from a raw file."""
    content = raw_file.read_text(encoding="utf-8")
    slug = slugify(raw_file.name)
    timestamp = now_iso()

    # Infer source type from content or filename
    source_type = "article"
    if "paper" in raw_file.parent.name.lower():
        source_type = "paper"
    elif "book" in raw_file.parent.name.lower():
        source_type = "book"
    elif "doc" in raw_file.parent.name.lower():
        source_type = "documentation"

    article = f"""---
title: "Source: {raw_file.stem}"
source_type: "{source_type}"
raw_file: "raw/{raw_file.relative_to(RAW_DIR)}"
extracted_from: "{timestamp}"
---

# {raw_file.stem}

## Original Content

{content}

## Extracted Knowledge

(To be filled by LLM - concepts, entities, connections)

## Related Articles

(To be updated as connections are discovered)
"""
    return article


async def process_raw_file(raw_file: Path, state: dict) -> float:
    """Process a single raw file: generate source, then extract knowledge."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    slug = slugify(raw_file.name)
    source_path = SOURCES_DIR / f"{slug}.md"

    # Step 1: Generate source article
    source_article = generate_source_article(raw_file)
    source_path.write_text(source_article, encoding="utf-8")
    print(f"  Generated: {source_path.relative_to(ROOT_DIR)}")

    # Step 2: LLM extracts knowledge from source
    schema = AGENTS_FILE.read_text(encoding="utf-8")
    wiki_index = read_wiki_index()

    prompt = f"""You are a knowledge extractor. Read this source article and extract:
1. Key CONCEPTS (3-5 atomic pieces of knowledge)
2. Relevant ENTITIES (people, organizations, tools mentioned)
3. CONNECTIONS between concepts (if any)

## Schema (from AGENTS.md)

{schema}

## Current Wiki Index

{wiki_index}

## Source Article to Process

File: raw/{raw_file.relative_to(RAW_DIR)}

{source_article}

## Your Task

1. Read the source article carefully
2. Extract 3-5 key concepts - create articles in knowledge/concepts/
3. Extract any entities mentioned - create articles in knowledge/entities/
4. Identify connections between 2+ concepts - create articles in knowledge/connections/
5. Update the "Extracted Knowledge" section in {source_path}
6. Update knowledge/index.md with new entries
7. Append to knowledge/log.md with what was extracted

Use the exact formats from AGENTS.md. Include proper YAML frontmatter and wikilinks.
"""

    cost = 0.0
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(ROOT_DIR),
                system_prompt={"type": "preset", "preset": "claude_code"},
                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep"],
                permission_mode="acceptEdits",
                max_turns=20,
            ),
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        pass
            elif isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0.0
                print(f"  Cost: ${cost:.4f}")
    except Exception as e:
        print(f"  Error: {e}")
        return 0.0

    # Update state
    rel_path = f"raw/{raw_file.relative_to(RAW_DIR)}"
    state.setdefault("raw_ingested", {})[rel_path] = {
        "hash": file_hash(raw_file),
        "source_file": str(source_path.relative_to(ROOT_DIR)),
        "processed_at": now_iso(),
        "cost_usd": cost,
    }
    state["total_cost"] = state.get("total_cost", 0.0) + cost
    save_state(state)

    return cost


def list_raw_files(target: Path | None = None) -> list[Path]:
    """List all .txt and .md files in raw/ recursively."""
    if target:
        return [target] if target.is_file() else []

    if not RAW_DIR.exists():
        return []

    files = []
    for suffix in [".txt", ".md"]:
        files.extend(RAW_DIR.rglob(f"*{suffix}"))
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description="Convert raw files to wiki knowledge")
    parser.add_argument("--file", type=str, help="Process specific raw file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    args = parser.parse_args()

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    # Determine which files to process
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = RAW_DIR / target.name
        if not target.exists():
            target = ROOT_DIR / args.file
        if not target.exists():
            print(f"Error: {args.file} not found")
            sys.exit(1)
        to_process = [target]
    else:
        all_raw = list_raw_files()
        to_process = []
        for raw_file in all_raw:
            rel = f"raw/{raw_file.relative_to(RAW_DIR)}"
            prev = state.get("raw_ingested", {}).get(rel, {})
            if not prev or prev.get("hash") != file_hash(raw_file):
                to_process.append(raw_file)

    if not to_process:
        print("Nothing to process - all raw files are up to date.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Files to process ({len(to_process)}):")
    for f in to_process:
        print(f"  - {f.relative_to(RAW_DIR)}")

    if args.dry_run:
        return

    # Process each file sequentially
    total_cost = 0.0
    for i, raw_file in enumerate(to_process, 1):
        print(f"\n[{i}/{len(to_process)}] Processing {raw_file.relative_to(RAW_DIR)}...")
        cost = asyncio.run(process_raw_file(raw_file, state))
        total_cost += cost
        print(f"  Done.")

    articles = list_wiki_articles()
    print(f"\nWiki build complete. Total cost: ${total_cost:.2f}")
    print(f"Knowledge base: {len(articles)} articles")


if __name__ == "__main__":
    main()
