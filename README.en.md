# Lightweight Knowledge Base (agentic-kb-lite)

> A lightweight personal/team knowledge base built on ripgrep + LLM: no semantic vector indexing, no intrusive restructuring; only lightweight format conversion (markitdown) and metadata cards (`.stub.md` / `.vision.md`).
> 中文版本: [README.md](./README.md) · License: [MIT](./LICENSE)

> **Terminology note**: this English version mirrors the Chinese authoritative source ([README.md](./README.md)) section-by-section. Domain terms (agent loop, vision, fixture, stub, ingest, four-level fallback, etc.) are kept in English throughout to avoid translation drift.

---

## 1. What this is / why it might be for you

This setup may fit you if any of the following apply:

- You have a pile of personal or team work materials (proposals, bids, meeting notes, research, screenshots, screen recordings) and want to ask questions like *"how did I do this before / what did we use / what did we discuss"*
- You **don't want to set up a heavy RAG stack** (vector DB + embeddings + rerank)
- You **don't want to upload materials to a third-party SaaS**, but you also **don't want to deploy a local LLM**
- You're already using Claude Code / Codex / another AI coding assistant, and are willing to let the AI read your files directly

What makes this different:

- **The only external model dependency is the LLM built into the AI coding assistant** (e.g., Claude inside Claude Code); no external API calls, no local model weights deployed
- **The only external tool dependencies are ripgrep + optional ffmpeg + optional poppler** (the last two only for multimodal scenarios)
- Retrieval uses ripgrep + an LLM-driven multi-round agent loop; visual transcription uses the AI coding assistant's built-in vision capability reading images directly
- **No semantic vector indexing, no chunking, no intrusive restructuring**; lightweight format conversion (markitdown converts docx/pptx/pdf to markdown) + metadata cards (`.stub.md` / `.vision.md`) let the LLM read directly

## 2. Core features

| Feature | Description |
|---|---|
| **Multi-round agent loop retrieval** | LLM iterates retrieval terms (expand / narrow / shift angle); hard cap of 3 rounds, ≤ 12 total tool calls |
| **Four-level fallback retrieval** | Body `.md` → tokenized fuzzy → vision transcription → stub metadata; each level falls back honestly on failure (L1/L2/L2.5/L3 scope-exclusive; **executed by the AI coding assistant in the CLAUDE.md state-segment workflow**, not embedded in `search.py`)|
| **Multimodal integration** | Image-heavy PPT / scanned PDF / video — all read by the AI coding assistant's built-in vision; videos go through ffmpeg frame extraction |
| **Incremental ingest** | `python ingest.py <path>` defaults to incremental (skips already-ingested unchanged files); `--full` forces a full pass |
| **Honest-fallback red line** | If nothing is found, say so; never fabricate. Scanned PDF / image-heavy PPT fall back to stub when toolchain is incomplete |
| **Lightweight fixture evaluation** | E1–E7 agent loop scenarios + V1–V4 vision/video scenarios — reproducible regression tests |
| **Zero external API / zero local model** | No remote model API calls, no local LLM deployment; all inference happens inside the AI coding assistant |

## 3. Quick Start

This repo is designed to work with **AI coding assistants like Claude Code / Codex**. The flow below **uses Claude Code as an example**; Codex and other assistants are semantically equivalent.

### Overview (6 steps)

```text
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   1. git clone <repo>  &&  cd agentic-kb-lite                    │
│                              │                                   │
│                              ▼                                   │
│   2. install.bat / manual    (Win: dbl-click;mac/Linux: venv)   │
│                              │                                   │
│                              ▼                                   │
│   3. setup_system_tools.bat  (optional: detect ffmpeg/poppler)   │
│                              │                                   │
│                              ▼                                   │
│   4. Edit path_map.yaml      (point 1-2 source paths)            │
│                              │                                   │
│                              ▼                                   │
│   5. Open repo in AI helper  ("read README + CLAUDE.md first")   │
│                              │                                   │
│                              ▼                                   │
│   6. AI: ingest D:\my\stuff  +  ask "how did I do X before?"     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.1 Prerequisites

- **Python 3.10–3.12**
- **An AI coding assistant** (pick one):
  - Claude Code: <https://claude.com/claude-code>
  - Codex: <https://openai.com/codex>
- **System tools** (optional, can skip entirely if you only use text materials):
  - `ffmpeg` (video frame extraction)
  - `poppler` (scanned PDF → PNG rendering)
  - Run `setup_system_tools.bat` to detect and get install hints

### 3.2 Install

**Windows**:

```powershell
git clone <repo-url>
cd agentic-kb-lite
install.bat                  # Python deps + bundled rg.exe + smoke test (~3 min)
setup_system_tools.bat       # optional: detect ffmpeg / poppler / system rg
```

**macOS / Linux** (best effort):

```bash
git clone <repo-url>
cd agentic-kb-lite

# macOS / Linux has no one-shot installer yet; install Python venv + deps manually:
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
# rg must be installed system-wide (see setup_system_tools.sh for brew / apt commands)

./setup_system_tools.sh      # detect rg / ffmpeg / poppler (optional)
```

### 3.3 Configure path_map.yaml (1–2 sources)

Edit `path_map.yaml` at the repo root, uncomment a placeholder, point it at your local materials directory:

```yaml
path_mappings:
  - source: "D:/my-project-materials"      # absolute path on your machine
    target: "01-历史方案/some-project"      # where it lands inside corpus/
```

### 3.4 Run it with the AI coding assistant

Open the AI coding assistant (Claude Code as an example) in the repo root and ask:

```text
Please read README.md, CLAUDE.md, and docs/试用指南.md first
to understand how this knowledge base works.

Then:
1. Ingest the files under D:/my-project-materials (dry-run first; confirm before applying)
2. Run a query: "How did I design the architecture for a previous project?"
```

The AI will follow the [CLAUDE.md](CLAUDE.md) workflow: ingest with G14/G15/G16/G18 routing, then the 4-level agent-loop retrieval with proper citations.

**You'll see output roughly like this**:

````text
[ingest dry-run]
Scanning D:/my-project-materials → 42 files matched
- 27 .md / .txt → G16 three-file coexistence
- 8 .docx → markitdown → .md + G14 naming convention
- 5 .pptx → G18 image-heavy routing + vision_pending: YES
- 2 .pdf → markitdown text extraction + G16
Proceed with actual ingest? (y/n)

[Query: How did I design the architecture for a previous project?]
[Round 1] Retrieval terms: ["system architecture", "project proposal", "technical architecture"]
[L1] rg hits corpus/01-历史方案/some-project-2025/proposal-XX.md (line 15-42)
[L2] filename scan hits corpus/01-历史方案/2024Q3-base-architecture.md
[Synthesis] Based on 2 body-text evidence pieces:
- Project A used X architecture, with core being ... (see corpus/01-历史方案/...:15-42)
- Project B used Y pattern, because ... (see corpus/01-历史方案/2024Q3-...)

Tool calls: 2 / 12 budget.
````

Output format is executed by the AI coding assistant per CLAUDE.md state-segment rules; specific details vary with the scenario.

> **Architectural boundary**: `scripts/search.py` is a low-level wrapper around ripgrep — it does file scanning only. **The full agent loop** (4-level fallback / filename scan / cross-round iteration / state-segment judgment / substantive-change detection) **is executed by the AI coding assistant (Claude Code / Codex / etc.) following the [CLAUDE.md](CLAUDE.md) contract**, not embedded inside `search.py`. `search.py` has no notion of "rounds"; the LLM invokes it for single ripgrep scans per round.

### 3.5 Example queries (anonymized, industry-style)

Queries that suit this repo (substitute with your own domain / projects):

```text
- "Any similar projects in the XX industry before? Focus on system architecture and data governance."
- "Find how localized-database adaptation was written in past technical bids."
- "Did we discuss why this project didn't use PostgreSQL? Find the original notes."
- "Any data-governance proposals from Q1 2026?"
```

## 4. Project structure

```text
agentic-kb-lite/
├── README.md / README.en.md          # this doc (Chinese / English)
├── CLAUDE.md                         # AI coding assistant runtime contract (mandatory pre-read)
├── LICENSE                           # MIT
├── install.bat / install.ps1         # Windows main installer
├── setup_system_tools.bat / .ps1     # system-tool (ffmpeg / poppler / rg) detection guide
├── setup_system_tools.sh             # macOS / Linux best effort
├── path_map.yaml                     # source dir → corpus subdir mapping
├── requirements.txt                  # Python deps
├── .gitignore                        # covers logs/ / .assets/ / .frames/ / private tests/
│
├── corpus/                           # materials main tree
│   ├── 01-历史方案/                  # project proposals / prototypes / tech docs
│   ├── 02-投标章节/                  # bid technical sections / tender docs
│   ├── 03-技术决策/                  # ADRs / selection comparisons
│   ├── 04-个人记忆/                  # notes / meeting minutes / research
│   └── .fixtures/                    # reproducible evaluation fixtures (tracked)
│       ├── E1_simple/                # agent loop simple single-round
│       ├── E2_expand/                # 0-hit expand
│       ├── E3_narrow/                # too-many-hits narrow
│       ├── E4_stub/                  # stub fallback
│       ├── E5_degenerate/            # invalid iteration → degenerate
│       ├── E6_filename_only/         # filename-only hit (v0.6)
│       ├── E7_filename_misleading/   # filename misleading (v0.6)
│       ├── V1_image_ppt/             # image-heavy PPT vision (anonymized synthetic)
│       ├── V2_scan_pdf/              # scanned PDF vision-failure fallback (stub form)
│       ├── V3_short_video/           # short-video frame extraction + vision
│       ├── V4_medium_video/          # medium video two-layer extraction logic
│       └── README.md                 # fixture design principles + scenario table
│
├── docs/
│   └── 试用指南.md                   # install guide / recommended trial queries / boundaries
│
├── prompts/                          # 4 scenario-specific prompts
│   ├── 场景1-历史方案查询.md         # scenario 1: historical-proposal lookup
│   ├── 场景2-投标章节复用.md         # scenario 2: bid-section reuse
│   ├── 场景3-技术决策溯源.md         # scenario 3: tech-decision tracing
│   └── 场景4-个人工作记忆.md         # scenario 4: personal work memory
│
├── scripts/
│   ├── ingest.py                     # ingest pipeline (G14/G15/G16/G18 routing + vision_pending)
│   ├── search.py                     # retrieval entry (ripgrep wrapper, supports --regex)
│   └── README.md                     # script details
│
├── tests/
│   └── 查询记录.md                   # evaluation evidence (E/V) + governance (R/G/J/F/P/W)
│
└── tools/
    ├── rg.exe                        # bundled ripgrep (Windows; v15.1.0, tracked in repo)
    ├── README.md                     # rg.exe source + version + MIT redistribution notice
    └── LICENSE-ripgrep                # upstream ripgrep MIT (byte-faithful)
```

## 5. Out of scope

- **No Web UI** (this repo lives inside the AI coding assistant as contract docs + scripts)
- **No vectorization / chunking / rerank** (violates the "lightweight" design premise)
- **No real-time delete-source sync** in the ingest pipeline (incremental ingest exists, but is manually triggered)
- **No restructuring of existing files / no renaming** (except governance rule G14 prefixes)
- **No parsing of PPT / video non-visual parts** (entered as AI-coding-assistant vision-transcribed text)

## 6. Full documentation

| Document | Purpose |
|---|---|
| [CLAUDE.md](CLAUDE.md) | AI coding assistant runtime contract — retrieval flow / synonyms / citation / red lines; **mandatory pre-read** per session |
| [docs/试用指南.md](docs/试用指南.md) | Install guide / 7 recommended trial queries (3 categories) / boundaries |
| [scripts/README.md](scripts/README.md) | `scripts/ingest.py` + `scripts/search.py` deep details (regex mode / smoke test) |
| [tests/查询记录.md](tests/查询记录.md) | Evaluation evidence (E1–E7 + V1–V4) + governance records (R/G/J/F/P/W) |
| [corpus/.fixtures/README.md](corpus/.fixtures/README.md) | Fixture design principles + 11 scenario subdirs ↔ scenario mapping |

## 7. License + feedback

**LICENSE**: MIT — see [LICENSE](LICENSE)

**Feedback**: GitHub Issues / Discussions
