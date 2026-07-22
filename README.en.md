# agentic-kb-lite

> A lightweight personal/team knowledge base built on ripgrep + an LLM agent loop.
> The core bet: at personal/team corpus scale, grep + a reasoning loop beats a heavy RAG stack (vector DB + embeddings + rerank) on cost, transparency, and maintenance.
> 中文: [README.md](./README.md) · License: [MIT](./LICENSE)

> **Terminology note**: domain terms (agent loop, vision, fixture, stub, ingest, four-level fallback, tier, etc.) are kept in English throughout to avoid drift against the Chinese source.

## What a query looks like

(illustrative flow — not a real log)

```text
You: find how we wrote the domestic-database migration section in an earlier bid

AI coding assistant (after reading this repo's CLAUDE.md contract):
  Round 1  rg "domestic database migration"      → 0 hits
  Round 2  tokenized expansion rg "localization|Dameng|Kingbase" → 3 files hit
  Read body → lands on "Project X Technical Bid" §4.2, quotes the passage + file path

If it isn't there, it says so — honest fallback is a red line; the AI must never fabricate.
```

The LLM drives the iteration itself (expand / narrow / shift angle), capped at 3 rounds and ≤ 12 total tool calls. When body search fails it degrades through 4 levels — body `.md` → tokenized fuzzy → vision transcription → stub metadata — announcing each failure explicitly.

## Who it's for

- You have a pile of work materials (proposals, bids, meeting notes, research, screenshots, screen recordings) and want to ask "how did I do this before / why did we decide that at the time"
- You don't want to stand up a vector DB + embeddings + rerank RAG stack
- You already use Claude Code / Codex or a similar AI coding assistant, and are fine letting it read your files directly

## How it works

- **Retrieval**: ripgrep full-text scan + a multi-round LLM agent loop — no vectorization, no chunking, no intrusive restructuring
- **Ingest**: AI semantic routing — `scan-only` scans the source dir → the AI produces `routing_plan.json` → `execute-plan` lands the files; re-runs skip unchanged files incrementally
- **Multimodal**: image-heavy PPT / scanned PDF / video are transcribed by the assistant's built-in vision (ffmpeg frame extraction / poppler rendering); docx/pptx/pdf go through markitdown for a lightweight `.md` conversion
- **Evaluable**: 10 agent-loop fixtures + 7 multimodal fixtures for reproducible regression runs

## Privacy boundary (read this if you handle regulated material)

- **This project's own code calls no external API**, uploads nothing, and only does local ripgrep scanning + local markitdown conversion
- **But at the assistant layer**: Claude Code / Codex / Cursor and friends put file contents into the model context per their own product mechanisms (usually cloud inference). That layer is outside this project's control
- For classified or internal enterprise material: switch to a local-model assistant (e.g. ollama + a local model), anonymize/subset before ingest, or run in an isolated environment

## Quick Start

Prerequisites: Python 3.10-3.12 plus any AI coding assistant (Claude Code / Codex).

```powershell
# Windows
git clone <repo-url> && cd agentic-kb-lite
install.bat                  # deps + bundled rg.exe (v15.1.0) + smoke test, ~3 minutes
setup_system_tools.bat       # optional: detect ffmpeg / poppler (multimodal material only)
```

```bash
# macOS / Linux (best effort, no one-click installer)
git clone <repo-url> && cd agentic-kb-lite
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./setup_system_tools.sh      # rg must come from your package manager; the script prints brew/apt commands
```

Then open the repo in your AI coding assistant and say: "read the README and CLAUDE.md first, then ingest D:\my-materials". Once ingest finishes, start asking questions.

Verify your environment: `python scripts/smoke_test.py` (17 asserts — any failure means something is missing).

## Out of scope

- No web UI (this is a contract document + scripts, used from inside an AI coding assistant)
- No vectorization / chunking / rerank
- No live source-directory watching (incremental ingest is manually triggered)
- No restructuring of your existing files, no renaming
- No pre-tuned dirty-document recipe parameters (baseline skeleton, experimental by design — real-corpus tuning is yours)

Per-format support boundaries (xmind / shp / vsdx / odf, etc.) are documented in [docs/格式支持边界.md](docs/格式支持边界.md) (Format support boundaries).

## Further reading

| Document | Contents |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Runtime contract for the AI coding assistant (read at the start of every session) |
| [docs/试用指南.md](docs/试用指南.md) | Setup / suggested trial questions / boundaries |
| [docs/structure.md](docs/structure.md) | Full directory structure |
| [scripts/README.md](scripts/README.md) | ingest / search script reference |
| [corpus/.fixtures/README.md](corpus/.fixtures/README.md) | Fixture design principles + scenario table |
| [docs/v0.1-to-v0.2-migration.md](docs/v0.1-to-v0.2-migration.md) | v0.1 → v0.2 upgrade notes (PARA four layers / AI semantic routing / two-axis retrieval) |
| [docs/v0.2-to-v0.3-migration.md](docs/v0.2-to-v0.3-migration.md) | v0.2 → v0.3 upgrade notes (5 tiers / `.shelved/` / `--deep`) |
| [Releases](https://github.com/Hugin-Z/agentic-kb-lite/releases) | Per-release notes and known limitations |

## License + feedback

MIT · GitHub Issues / Discussions
