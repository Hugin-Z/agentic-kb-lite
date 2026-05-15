# 轻量知识库(knowledge-ripgrep+LLM)

> 基于 ripgrep + LLM 的轻量个人/部门知识库,不向量化、不切分、不预处理。
> English version: [README.en.md](./README.en.md) · License: [MIT](./LICENSE)

---

## 1. 这是什么 / 跟我有什么关系

如果你符合以下任一情况,这套方案可能适合你:

- 你有一堆个人或团队工作素材(方案 / 标书 / 纪要 / 调研 / 截图 / 录屏),想问"我以前是怎么做的 / 我们用了什么 / 我之前讨论过什么"
- 你**不想搭一套向量数据库 + Embedding + Rerank 的重型 RAG 栈**
- 你**不想把素材传第三方 SaaS**,但又**懒得本地部署 LLM**
- 你已经在用 Claude Code / Codex / 其他 AI 编程助手,愿意让 AI 直接读你的素材文件

差异化:

- **唯一外部模型依赖是 AI 编程助手内置 LLM**(以 Claude Code 为例,即其内置 Claude 模型),不调外部 API、不本地部署模型权重
- **唯一外部工具依赖是 ripgrep + 可选 ffmpeg + 可选 poppler**(后两者只在多模态场景需要)
- 检索靠 ripgrep + LLM 多轮 agent loop;视觉转写靠 AI 编程助手内置的 vision 能力直接读图
- 不向量化、不切分、不预处理 — 素材进 corpus 时**怎么放就怎么存**

## 2. 核心特性

| 特性 | 描述 |
|---|---|
| **agent loop 多轮检索** | LLM 自动迭代检索词(扩展 / 收窄 / 换角度),3 轮硬上限,工具调用累计 ≤ 12 次 |
| **4 级降级检索** | 正文 .md → 拆词模糊 → vision 转写文件 → stub 元数据,每级失败诚实降级(L1/L2/L2.5/L3 scope 排他,**由 AI 编程助手在 CLAUDE.md 状态段执行**,非 `search.py` 内嵌)|
| **多模态接入** | 图为主 PPT / 扫描 PDF / 视频均由 AI 编程助手内置 vision 能力直接读;视频走 ffmpeg 抽帧 |
| **增量 ingest** | `python ingest.py <path>` 默认增量,跳过已 ingest 且未变文件;`--full` 强制全量 |
| **诚实降级红线** | 找不到就说找不到,严禁补全;扫描 PDF / 图为主 PPT 工具链不全时走 stub 兜底 + 提示 |
| **轻量 fixture 评估** | E1-E7 agent loop 场景 + V1-V4 vision/视频场景,可复现回归测试 |
| **零外部 API / 零本地模型** | 不调任何远程模型 API,不本地部署 LLM,所有推理由 AI 编程助手内置完成 |

## 3. Quick Start

本仓库适配 **Claude Code / Codex 等 AI 编程助手**。以下流程**以 Claude Code 为例**,Codex 等其他助手语义等价。

### 流程总览(6 步)

```text
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   1. git clone <repo>  &&  cd knowledge-ripgrep+LLM(...)         │
│                              │                                   │
│                              ▼                                   │
│   2. install.bat / manual    (Windows 双击;mac/Linux 手动 venv) │
│                              │                                   │
│                              ▼                                   │
│   3. setup_system_tools.bat  (可选:检测 ffmpeg / poppler)        │
│                              │                                   │
│                              ▼                                   │
│   4. 编辑 path_map.yaml      (改 1-2 条 source 路径)              │
│                              │                                   │
│                              ▼                                   │
│   5. AI 编程助手打开仓库     ("先读 README + CLAUDE.md")          │
│                              │                                   │
│                              ▼                                   │
│   6. AI:把 D:\我的资料 入库 + 问"以前怎么做的"                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.1 系统前置

- **Python 3.10-3.12**
- **AI 编程助手**(任选其一):
  - Claude Code:<https://claude.com/claude-code>
  - Codex:<https://openai.com/codex>
- **系统工具**(可选,只用文本类素材可全跳):
  - `ffmpeg`(视频抽帧)
  - `poppler`(扫描 PDF → PNG 渲染)
  - 走 `setup_system_tools.bat` 自动检测 + 给安装提示

### 3.2 安装

**Windows**:

```powershell
git clone <repo-url>
cd knowledge-ripgrep+LLM(...)
install.bat                  # 装 Python 依赖 + bundled rg.exe + smoke test(~3 分钟)
setup_system_tools.bat       # 可选:检测 ffmpeg / poppler / 系统 rg
```

**macOS / Linux**(best effort):

```bash
git clone <repo-url>
cd "knowledge-ripgrep+LLM(...)"

# macOS / Linux 暂不支持一键安装,需手动安装 Python venv + 依赖:
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
# rg 需系统装(参考 setup_system_tools.sh 给的 brew / apt 命令)

./setup_system_tools.sh      # 检测 rg / ffmpeg / poppler(可选)
```

### 3.3 配 path_map.yaml(1-2 条 source)

编辑仓库根 `path_map.yaml`,去掉占位注释,改成你本机资料目录:

```yaml
path_mappings:
  - source: "D:/我的项目资料"          # 你本机资料目录绝对路径
    target: "01-历史方案/某项目"        # 落到 corpus/ 哪个场景子目录
```

### 3.4 用 AI 编程助手跑一次

打开 AI 编程助手(以 Claude Code 为例),在仓库根目录提问:

```text
先读 README.md、CLAUDE.md 和 docs/试用指南.md,理解知识库使用规则。

然后:
1. 把 D:/我的项目资料 下的文件入库(先 dry-run,确认后再正式)
2. 跑一条查询:"我以前的某个项目是怎么做架构的?"
```

AI 会按 [CLAUDE.md](CLAUDE.md) 工作流跑 ingest(G14/G15/G16/G18 分流)+ agent loop 4 级降级检索 + 引用规范输出。

> **架构边界说明**:`scripts/search.py` 是 ripgrep 的低层包装器,负责文件扫描。**完整 agent loop**(4 级降级 / 文件名扫描 / 轮间迭代 / 状态段判定 / 实质变化判定)**由 AI 编程助手(Claude Code / Codex 等)按 [CLAUDE.md](CLAUDE.md) 契约执行**,不是 `search.py` 内嵌的功能。`search.py` 不知道"轮次"概念,LLM 在每轮调用它做单次 ripgrep 扫描。

### 3.5 示例查询(脱敏行业举例)

适合本仓库的查询类型(可改成你的具体行业 / 项目):

```text
- "以前有没有类似的 XX 行业项目方案?重点看系统架构和数据治理部分。"
- "帮我找一下之前技术标里关于国产化数据库适配是怎么写的。"
- "我们之前讨论过这个项目为什么不用 PostgreSQL 吗?帮我找出处。"
- "2026Q1 有没有跟数据治理相关的方案?"
```

## 4. 项目结构

```text
knowledge-ripgrep+LLM(...)
├── README.md / README.en.md          # 本文档(中文 / 英文)
├── CLAUDE.md                         # AI 编程助手运行时契约(每次会话必读)
├── LICENSE                           # MIT
├── install.bat / install.ps1         # Windows 主安装脚本
├── setup_system_tools.bat / .ps1     # 系统工具(ffmpeg / poppler / rg)检测引导
├── setup_system_tools.sh             # 同上跨平台(macOS / Linux best effort)
├── path_map.yaml                     # 源目录 → corpus 子目录映射
├── requirements.txt                  # Python 依赖
├── .gitignore                        # 含 logs/ / .assets/ / .frames/ / tests 私有素材
│
├── corpus/                           # 素材主目录
│   ├── 01-历史方案/                  # 项目方案 / 原型 / 技术文档
│   ├── 02-投标章节/                  # 投标技术章节 / 招标文件
│   ├── 03-技术决策/                  # ADR / 选型对比
│   ├── 04-个人记忆/                  # 笔记 / 纪要 / 调研
│   └── .fixtures/                    # 可跑评估场景 fixtures(开源仓 track,可复现)
│       ├── E1_simple/                # agent loop 简单单轮
│       ├── E2_expand/                # 0 命中扩词
│       ├── E3_narrow/                # 命中过多收窄
│       ├── E4_stub/                  # stub 兜底
│       ├── E5_degenerate/            # 无效迭代退化
│       ├── E6_filename_only/         # 纯文件名命中(v0.6)
│       ├── E7_filename_misleading/   # 文件名误导(v0.6)
│       ├── V1_image_ppt/             # 图为主 PPT vision(合成脱敏)
│       ├── V2_scan_pdf/              # 扫描 PDF vision 失败降级(stub 形式,实际 PDF 本地保留)
│       ├── V3_short_video/           # 短视频抽帧 vision
│       ├── V4_medium_video/          # 中等视频双层抽帧逻辑
│       └── README.md                 # fixture 设计原则 + 场景表
│
├── docs/
│   └── 试用指南.md                   # 装机 / 推荐试用问题 / 边界
│
├── prompts/                          # 4 个场景的差异化提示词
│   ├── 场景1-历史方案查询.md
│   ├── 场景2-投标章节复用.md
│   ├── 场景3-技术决策溯源.md
│   └── 场景4-个人工作记忆.md
│
├── scripts/
│   ├── ingest.py                     # 入库主流程(G14/G15/G16/G18 分流 + vision pending)
│   ├── search.py                     # 检索主入口(ripgrep 包装,可正则)
│   └── README.md                     # 脚本详细说明
│
├── tests/
│   └── 查询记录.md                   # 评估证据(E/V 系)+ 治理记录(R/G/J/F/P/W)
│
└── tools/
    └── rg.exe                        # bundled ripgrep(Windows;.gitignore,setup 脚本检测)
```

## 5. 不在范围

- **不做 Web UI**(本仓库定位是 AI 编程助手内打开的契约文档 + 脚本)
- **不做向量化 / 切分 / Rerank**(违反"轻量"设计前提)
- **不做素材自动入库 pipeline 的"实时监听删源同步"**(增量 ingest 已做,但增量是手动触发)
- **不重组现有文件结构 / 不改文件名**(治理规则 G14 命名规范除外)
- **不解析 PPT / 视频的非视觉部分**(以 AI 编程助手内置 vision 转写文本入库)

## 6. 完整文档导航

| 文档 | 用途 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | AI 编程助手运行时契约 — 检索流程 / 同义词 / 引用规范 / 红线;**每次会话必读** |
| [docs/试用指南.md](docs/试用指南.md) | 装机指南 / 推荐试用问题(7 个,3 类)/ 边界说明 |
| [scripts/README.md](scripts/README.md) | scripts/ingest.py + scripts/search.py 详细说明(含正则模式 / smoke test) |
| [tests/查询记录.md](tests/查询记录.md) | 评估证据(E1-E7 + V1-V4)+ 治理记录(R/G/J/F/P/W) |
| [corpus/.fixtures/README.md](corpus/.fixtures/README.md) | 评估 fixtures 设计原则 + 11 个场景子目录↔场景表 |

## 7. License + 反馈

**LICENSE**: MIT — 详见 [LICENSE](LICENSE)

**反馈**: GitHub Issues / Discussions
