# agentic-kb-lite

> A lightweight personal/team knowledge base built on ripgrep + an LLM agent loop.
> The core bet: at personal/team corpus scale, grep + a reasoning loop beats a heavy RAG stack (vector DB + embeddings + rerank) on cost, transparency, and maintenance.
> 中文: [README.md](./README.md) · License: [MIT](./LICENSE)

> **Terminology note**: domain terms (agent loop, vision, fixture, stub, ingest, four-level fallback, tier, etc.) are kept in English throughout to avoid drift against the Chinese source.

## Who it's for

- You have a pile of work materials (proposals, bids, meeting notes, research, screenshots, screen recordings) and want to ask "how did I do this before / why did we decide that at the time"
- You don't want to stand up a vector DB + embeddings + rerank RAG stack
- You already use Claude Code / Codex or a similar AI coding assistant, and are fine letting it read your files directly

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

## What an ingest looks like

(illustrative flow — not a real log)

```text
You: ingest D:\work\smart-city-viz-platform

AI: python scripts/ingest.py scan-only <src>     → enumerates the files
    reads the routing protocol in CLAUDE.md, decides where each one lands,
    emits routing_plan.json:

      overall-design.docx    → 01-projects/smart-city-viz-platform/01-方案/
      requirements-notes.md  → 01-projects/smart-city-viz-platform/04-调研/
      standards/GBT_xxx.pdf  → 03-resources/国标行标/   ← detached: a national
                                                          standard belongs to no
                                                          single project
      delivered/2023-old/    → 04-archives/             ← excluded from search
                                                          by default

You: skim the plan, approve it (or add one explicit_mappings entry to path_map.yaml)

AI: python scripts/ingest.py execute-plan <plan>  → lands files + injects frontmatter
```

## Why ingest is the load-bearing step

There is no vectorization here; retrieval is ripgrep doing literal matching — and literal matching carries no semantics of its own. **The semantics are decided once, by the AI, at ingest time, and frozen into two things**:

- **Directory position**: where a file sits *is* its classification. That lets a query narrow by scope first (only active projects / only reference material / sweep everything) instead of gambling against the whole corpus
- **frontmatter**: structured fields (`type / date / project / tags`, among others) injected at ingest, so conditions like "proposals from Q1 2026" become literally matchable

The cost is one AI judgment per file at ingest. The payoff is that every later query needs no embedding service, no index rebuild, and every result is explainable down to a concrete file path. **Put differently: the structure does the job a vector store would have done.**

The AI judges, but you decide — `scan-only` and `execute-plan` are two separate steps, and the `routing_plan.json` between them is plain text you can read and edit. When a judgment is off, add an `explicit_mappings` entry to `path_map.yaml` rather than tuning a prompt.

Physical placement details (the full PARA definitions, tier layering, `.shelved/` exclusion rules) live in [docs/structure.md](docs/structure.md); the complete `routing_plan.json` schema is in [scripts/README.md](scripts/README.md).

## The logic lives in a text contract, not in Python

The scripts under `scripts/` are deliberately thin: `search.py` wraps ripgrep, `ingest.py` handles format conversion and landing files. **The actual decision logic — the PARA routing protocol, retrieval-behavior identification, the 4-level fallback — is written in [CLAUDE.md](CLAUDE.md) and executed by whichever AI coding assistant you're already running.**

Three consequences follow from that split:

- **No second model to call.** Inference happens inside the assistant you already have open, which is why this repo's own code genuinely calls no external API (see the privacy boundary below for where that ends)
- **Portable across assistants.** Claude Code and Codex are semantically equivalent here, because the contract is prose rather than code bound to one vendor's API
- **The policy is readable and editable.** Unhappy with the fallback behavior? Edit a paragraph in CLAUDE.md — no code change, no call stack to trace

The cost is that behavior depends on how well your assistant follows instructions, which is why [corpus/.fixtures/](corpus/.fixtures/) holds reproducible regression scenarios to pin it down.

## Beyond retrieval

- **Two axes: scope × behavior**. **scope** decides *where to look* and comes from the PARA structure (only active projects / only reference material / sweep everything); **behavior** decides *how to assemble the answer* and branches on the kind of question (pinpoint lookup / inventory / decision archaeology / open-ended exploration). The assistant infers both from the contract and combines them orthogonally — **you are never asked to pick from a menu**
- **tier layering**: material is split into primary knowledge versus working drafts / old versions / raw assets; the latter three land under `.shelved/` and are excluded from search by default — which solves "I don't want to delete the old stuff, but it shouldn't pollute everyday retrieval". Add `--deep` to sweep them back in. Details in [docs/structure.md](docs/structure.md)
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
