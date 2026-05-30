# LLM Personal Knowledge Base

**Your AI conversations compile themselves into a searchable knowledge base.**

Adapted from [Karpathy's LLM Knowledge Base](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) architecture. Knowledge accumulates from two sources: your Claude Code conversations (automatic) and external materials you drop into `raw/` (manual). Both flows extract structured articles into a multi-layer knowledge base — concepts, entities, connections, sources, notes — with a deterministic index rebuilt by code, not LLM. Retrieval uses a simple index file instead of RAG - no vector database, no embeddings, just markdown.

Anthropic has clarified that personal use of the Claude Agent SDK is covered under your existing Claude subscription (Max, Team, or Enterprise) - no separate API credits needed. Unlike OpenClaw, which requires API billing for its memory flush, this runs on your subscription.

## Quick Start

Tell your AI coding agent:

> "Clone https://github.com/coleam00/claude-memory-compiler into this project. Set up the Claude Code hooks so my conversations automatically get captured into daily logs, compiled into a knowledge base, and injected back into future sessions. Read the AGENTS.md for the full technical reference on how everything works."

The agent will:
1. Clone the repo and run `uv sync` to install dependencies
2. Copy `.claude/settings.json` into your project (or merge the hooks into your existing settings)
3. The hooks activate automatically next time you open Claude Code

From there, your conversations start accumulating. After 6 PM local time, the next session flush automatically triggers compilation of that day's logs into knowledge articles. You can also run `uv run python scripts/compile.py` manually at any time.

## How It Works

**Two parallel data flows:**

**Flow 1: Automatic (from conversations)**
```
Conversation -> SessionEnd/PreCompact hooks -> flush.py extracts knowledge
    -> daily/YYYY-MM-DD.md -> compile.py -> knowledge/concepts/, entities/, connections/
```

**Flow 2: Manual (from external sources)**
```
raw/*.md (papers, articles, notes) -> wiki_builder.py -> knowledge/sources/
    -> LLM extracts -> knowledge/concepts/, entities/, connections/
```

- **Hooks** capture conversations automatically (session end + pre-compaction safety net)
- **flush.py** calls the Claude Agent SDK to decide what's worth saving
- **compile.py** turns daily logs into concepts, entities, connections, notes
- **wiki_builder.py** ingests `raw/` files (papers, docs, notes) into the same knowledge layers
- **index_builder.py** deterministically rebuilds `knowledge/index.md` by scanning articles — no LLM
- **query.py** answers questions using index-guided retrieval (no RAG needed)
- **lint.py** runs 7 health checks (broken links, orphans, contradictions, staleness)
- **SessionStart hook** injects knowledge index into every session for context

## Key Commands

```bash
# Automatic flow (from conversations)
uv run python scripts/compile.py                     # compile new daily logs
uv run python scripts/compile.py --all               # recompile everything

# Manual flow (from external sources)
uv run python scripts/wiki_builder.py                # ingest raw/ files
uv run python scripts/wiki_builder.py --dry-run      # preview what would happen

# Index
uv run python scripts/index_builder.py               # rebuild index.md from articles
uv run python scripts/index_builder.py --dry-run     # preview index without writing

# Query & maintain
uv run python scripts/query.py "question"             # ask the knowledge base
uv run python scripts/query.py "question" --file-back # ask + save answer
uv run python scripts/lint.py                         # run health checks
uv run python scripts/lint.py --structural-only       # skip LLM checks
```

## Why No RAG?

Karpathy's insight: at personal scale (50-500 articles), the LLM reading a structured `index.md` outperforms vector similarity. The LLM understands what you're really asking; cosine similarity just finds similar words. RAG becomes necessary at ~2,000+ articles when the index exceeds the context window.

## Technical Reference

See **[AGENTS.md](AGENTS.md)** for the complete technical reference: article formats, hook architecture, script internals, cross-platform details, costs, and customization options. AGENTS.md is designed to give an AI agent everything it needs to understand, modify, or rebuild the system.
