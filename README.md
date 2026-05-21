# 轻量知识库(agentic-kb-lite)

> 基于 ripgrep + LLM 的轻量个人/部门知识库:不做语义向量化索引,不做侵入式重组;只做轻量格式转换(markitdown)和元数据卡片(.stub.md / .vision.md)。
> English version: [README.en.md](./README.en.md) · License: [MIT](./LICENSE)

---

## 1. 这是什么 / 跟我有什么关系

如果你符合以下任一情况,这套方案可能适合你:

- 你有一堆个人或团队工作素材(方案 / 标书 / 纪要 / 调研 / 截图 / 录屏),想问"我以前是怎么做的 / 我们用了什么 / 我之前讨论过什么"
- 你**不想搭一套向量数据库 + Embedding + Rerank 的重型 RAG 栈**
- 你**不想搭一套向量数据库 + Embedding + Rerank 的重型 RAG 栈**
- 你已经在用 Claude Code / Codex / 其他 AI 编程助手,愿意让 AI 直接读你的素材文件

差异化:

- **本项目自身不额外调用任何外部模型 API**,所有推理由你正在用的 AI 编程助手完成 ⚠ **见下方"隐私边界"段**
- **唯一外部工具依赖是 ripgrep + 可选 ffmpeg + 可选 poppler**(后两者只在多模态场景需要)
- 检索靠 ripgrep + LLM 多轮 agent loop;视觉转写靠 AI 编程助手内置的 vision 能力直接读图
- **不做语义向量化索引,不做切分,不做侵入式重组**;轻量格式转换(markitdown 把 docx/pptx/pdf 转 markdown)+ 元数据卡片(`.stub.md` / `.vision.md`)让 LLM 能直接读

### 隐私边界(v0.2.1 修订:必读)

> v0.2.0 之前的 README 措辞"零外部 API / 零本地模型 / 不调远程"可能让政企用户误判为完全离线。**实际边界是**:

- **本项目代码自身**:不调用任何外部 API,不上传文件,仅做本机 ripgrep 扫描 + markitdown 本机转换。这部分**完全本地**
- **但 AI 编程助手层面**:若使用 Claude Code / Codex / Cursor 等助手,**文件内容会按对应助手的产品机制进入模型上下文**(可能涉及上传到 Anthropic / OpenAI / 其他服务商的云端推理)。这层不在本项目控制范围
- **涉密 / 政企内部材料**:请**用本地模型助手**(如 [ollama](https://ollama.com) + 本地 CodeLlama / Qwen),或自行评估所用助手的合规边界 / DPA(数据处理协议)
- **不确定时**:入库材料前做**脱敏 / 子集化**处理,或在**隔离环境**(虚拟机 / 沙箱目录)中运行,避免误把敏感素材传到云

## 2. 核心特性

| 特性 | 描述 |
|---|---|
| **agent loop 多轮检索** | LLM 自动迭代检索词(扩展 / 收窄 / 换角度),3 轮硬上限,工具调用累计 ≤ 12 次 |
| **4 级降级检索** | 正文 .md → 拆词模糊 → vision 转写文件 → stub 元数据,每级失败诚实降级(L1/L2/L2.5/L3 scope 排他,**由 AI 编程助手在 CLAUDE.md 状态段执行**,非 `search.py` 内嵌)|
| **多模态接入** | 图为主 PPT / 扫描 PDF / 视频均由 AI 编程助手内置 vision 能力直接读;视频走 ffmpeg 抽帧 |
| **增量 ingest** | `python ingest.py <path>` 默认增量,跳过已 ingest 且未变文件;`--full` 强制全量 |
| **诚实降级红线** | 找不到就说找不到,严禁补全;扫描 PDF / 图为主 PPT 工具链不全时走 stub 兜底 + 提示 |
| **轻量 fixture 评估** | E1-E7 agent loop 场景 + V1-V4 vision/视频场景,可复现回归测试 |
| **本项目自身不调外部 API** | 本仓库代码层面**不调任何外部 API**,所有推理由你正在用的 AI 编程助手完成;**注意**:助手层面是否上传文件到云端推理,取决于具体助手的产品机制,**见 §1 隐私边界**|

## 3. Quick Start

本仓库适配 **Claude Code / Codex 等 AI 编程助手**。以下流程**以 Claude Code 为例**,Codex 等其他助手语义等价。

### 流程总览(6 步)

```text
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   1. git clone <repo>  &&  cd agentic-kb-lite                   │
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
cd agentic-kb-lite
install.bat                  # 装 Python 依赖 + bundled rg.exe + smoke test(~3 分钟)
setup_system_tools.bat       # 可选:检测 ffmpeg / poppler / 系统 rg
```

**macOS / Linux**(best effort):

```bash
git clone <repo-url>
cd agentic-kb-lite

# macOS / Linux 暂不支持一键安装,需手动安装 Python venv + 依赖:
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
# rg 需系统装(参考 setup_system_tools.sh 给的 brew / apt 命令)

./setup_system_tools.sh      # 检测 rg / ffmpeg / poppler(可选)
```

### 3.3 配 path_map.yaml(v0.2 起 AI 语义路由)

v0.2 起 **path_map.yaml 退化为语义说明 + hints + explicit_mappings 兜底**;AI 在 ingest 时自动按 [CLAUDE.md 第 6 节"PARA 路由协议"](CLAUDE.md) 判断目标位置(`01-projects/` / `02-areas/` / `03-resources/` / `04-archives/`)。**通常不需要改 path_map.yaml** — AI 看到子目录"标准/"就知道脱钩到 resources/国标行标,看到"纪要/"就知道留在项目内 03-纪要。

只有 AI 判断不理想时,在 `path_map.yaml` 的 `explicit_mappings` 字段加一条用户偏好兜底:

```yaml
explicit_mappings:
  - source: "D:/某客户合同包/"
    target: "02-areas/合同档案/"
    reason: "目录虽含项目名,但内容是合同文档,归 areas 更合适"
```

#### routing_plan.json 样例(AI 产出格式参考)

AI 跑完 `scan-only` 后产出的 `routing_plan.json` 长这样(5 items 简化示例,覆盖典型场景):

```json
{
  "src_root": "D:/工作目录/智慧城市可视化平台",
  "plan_timestamp": "2026-05-22T10:00:00",
  "ai_judgment_summary": "顶层判为 01-projects;标准/ 脱钩到 03-resources/国标行标 + 项目前缀消歧;纪要/ 留在项目内 03-纪要/;已交付/ 进 04-archives;explicit_mappings 命中覆盖 1 条",
  "items": [
    {
      "src_abs": "D:/工作目录/智慧城市可视化平台/总体方案.docx",
      "target_bucket": "01-projects",
      "target_project": "智慧城市可视化平台",
      "target_subdir": "01-方案",
      "target_filename": "总体方案.docx",
      "frontmatter": {"type": "方案", "date": "2026-03-15", "project": "智慧城市可视化平台", "tags": []},
      "ai_reason": "Step D:文件名含'方案' + 项目顶层 → 01-方案/"
    },
    {
      "src_abs": "D:/工作目录/智慧城市可视化平台/标准/CIM技术规范.pdf",
      "target_bucket": "03-resources",
      "target_project": null,
      "target_subdir": "国标行标",
      "target_filename": "智慧城市可视化平台_CIM技术规范.pdf",
      "frontmatter": {"type": "国标", "date": "2024-12-01", "project": null, "tags": ["CIM"]},
      "ai_reason": "Step C:标准/ 子目录 = 跨项目可复用 → 脱钩到 03-resources/国标行标/;target_filename 加项目前缀消歧"
    },
    {
      "src_abs": "D:/工作目录/智慧城市可视化平台/纪要/2026-03-10客户沟通.docx",
      "target_bucket": "01-projects",
      "target_project": "智慧城市可视化平台",
      "target_subdir": "03-纪要",
      "target_filename": "2026-03-10客户沟通.docx",
      "frontmatter": {"type": "纪要", "date": "2026-03-10", "project": "智慧城市可视化平台", "tags": []},
      "ai_reason": "Step D:父目录'纪要/' + 文件名含日期 → 03-纪要/(date 取文件名)"
    },
    {
      "src_abs": "D:/工作目录/智慧城市可视化平台/已交付/初验报告.pdf",
      "target_bucket": "04-archives",
      "target_project": null,
      "target_subdir": "智慧城市可视化平台",
      "target_filename": "初验报告.pdf",
      "frontmatter": {"type": "验收", "date": "2025-12-20", "project": "智慧城市可视化平台", "tags": ["已交付"]},
      "ai_reason": "Step B:父目录名含'已交付' → 04-archives/(archives_hint 命中)"
    },
    {
      "src_abs": "D:/工作目录/智慧城市可视化平台/合同/某合同.pdf",
      "target_bucket": "02-areas",
      "target_project": null,
      "target_subdir": "合同档案",
      "target_filename": "智慧城市可视化平台_某合同.pdf",
      "frontmatter": {"type": "合同", "date": "2026-01-15", "project": null, "tags": ["合同档案"]},
      "ai_reason": "Step A:explicit_mappings 命中('某客户合同包' → 02-areas/合同档案/);跳过 Step B-D 常规判断"
    }
  ]
}
```

**说明**:每个 item 的 `src_abs` / `target_bucket` / `target_filename` 必填(P0-2 路径边界校验);`target_project` 仅 01-projects 必填;`frontmatter.project` 在非 projects 类落地时应为 null。schema 完整字段见 [CLAUDE.md §6.3](CLAUDE.md) + [docs/v0.2-plan.md §5.3 步骤 2.3](docs/v0.2-plan.md)。

### 3.4 用 AI 编程助手跑一次

打开 AI 编程助手(以 Claude Code 为例),在仓库根目录提问:

```text
先读 README.md、CLAUDE.md 和 docs/试用指南.md,理解知识库使用规则。

然后:
1. 把 D:/我的项目资料 下的文件入库(先 dry-run,确认后再正式)
2. 跑一条查询:"我以前的某个项目是怎么做架构的?"
```

AI 会按 [CLAUDE.md](CLAUDE.md) 工作流跑 ingest(G14/G15/G16/G18 分流)+ agent loop 4 级降级检索 + 引用规范输出。

**你大概会看到这样的输出**:

````text
[ingest dry-run]
扫描 D:/我的项目资料 → 命中 42 个文件
- 27 个 .md / .txt → G16 三件共存
- 8 个 .docx → markitdown 转 .md + G14 命名规范
- 5 个 .pptx → G18 图为主分流 + vision_pending: YES
- 2 个 .pdf → markitdown 提取文本 + G16
确认正式入库?(y/n)

[查询:我以前的某个项目是怎么做架构的?]
[轮 1 状态段]
  检索行为: 模糊探索(只主题词,无指向词)
  默认 scope: corpus/01-projects/(命中"项目")
[L1] rg 命中 corpus/01-projects/某项目-2025/01-方案/总体方案.md (line 15-42)
[L2] 文件名扫命中 corpus/01-projects/某客户A-2024Q3/01-方案/基础架构设计.md
[整合] 基于 2 份正文证据:
- 项目 A 采用 X 架构,核心是 ...(详见 corpus/01-projects/某项目-2025/...:15-42)
- 项目 B 用了 Y 模式,因为 ...(详见 corpus/01-projects/某客户A-2024Q3/...)

工具调用:2 次 / 12 上限。
````

输出格式由 AI 编程助手按 CLAUDE.md 状态段执行,具体细节随场景变化。

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
agentic-kb-lite/
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
├── corpus/                           # 素材主目录(v0.2 起 PARA 四层)
│   ├── 01-projects/                  # 在做的具体项目;内部 5 固定子目录(01-方案/02-章节/03-纪要/04-调研/05-附图)+ 99-其他
│   ├── 02-areas/                     # 长期维护的责任领域(产品方案库/行业解决方案/投标章节模板/技术方法论)
│   ├── 03-resources/                 # 参考资料(国标行标/行业研究/竞品资料/培训与调研)
│   ├── 04-archives/                  # 已交付且不会再用的老项目(默认不在 P+A+R 全扫 scope)
│   └── .fixtures/                    # 可跑评估场景 fixtures(开源仓 track,可复现)
│       ├── E1_simple/                # agent loop 简单单轮
│       ├── E2_expand/                # 0 命中扩词
│       ├── E3_narrow/                # 命中过多收窄
│       ├── E4_stub/                  # stub 兜底
│       ├── E5_degenerate/            # 无效迭代退化
│       ├── E6_filename_only/         # 纯文件名命中(v0.6)
│       ├── E7_filename_misleading/   # 文件名误导(v0.6)
│       ├── E8_scope_routing/         # scope 路由(v0.2 阶段 5)
│       ├── E9_behavior/              # 行为识别 4 + 2 mixed(v0.2 阶段 5)
│       ├── V1_image_ppt/             # 图为主 PPT vision(合成脱敏)
│       ├── V2_scan_pdf/              # 扫描 PDF vision 失败降级(stub 形式,实际 PDF 本地保留)
│       ├── V3_short_video/           # 短视频抽帧 vision
│       ├── V4_medium_video/          # 中等视频双层抽帧逻辑
│       ├── V5_embedded_image/        # docx 嵌入图 vision(v0.2 阶段 4)
│       ├── V6_embedded_table/        # docx 嵌入表 python-docx 抽取(v0.2 阶段 4)
│       ├── V7_vsdx/                  # vsdx LibreOffice 降级路径(v0.2 阶段 4)
│       └── README.md                 # fixture 设计原则 + 场景表
│
├── docs/
│   └── 试用指南.md                   # 装机 / 推荐试用问题 / 边界
│
├── prompts/                          # 4 个 PARA scope 差异化提示词(v0.2)
│   ├── 场景-projects.md
│   ├── 场景-areas.md
│   ├── 场景-resources.md
│   └── 场景-跨corpus盘点.md
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
    ├── rg.exe                        # bundled ripgrep(Windows;v15.1.0,纳入仓库)
    ├── README.md                     # rg.exe 来源 + 版本 + MIT 分发声明
    └── LICENSE-ripgrep                # ripgrep 上游 MIT 原文(字节级一致)
```

## 5. 不在范围

- **不做 Web UI**(本仓库定位是 AI 编程助手内打开的契约文档 + 脚本)
- **不做向量化 / 切分 / Rerank**(违反"轻量"设计前提)
- **不做素材自动入库 pipeline 的"实时监听删源同步"**(增量 ingest 已做,但增量是手动触发)
- **不重组现有文件结构 / 不改文件名**(治理规则 G14 命名规范除外)
- **不解析 PPT / 视频的非视觉部分**(以 AI 编程助手内置 vision 转写文本入库)

### 5.1 部分格式的处置说明(v0.2 阶段 4)

- **xmind(思维导图)**:不直接支持。请先在 XMind 桌面端**导出为 PNG 或 PDF**,再 ingest 导出文件。导出的 PNG 会走 vision 路径 A(图为主文件)转写,实现内容检索。
- **shp(GIS 空间数据)**:`.shp/.shx/.dbf/.prj` 等空间数据文件**不在本仓库检索范围**。如果需要"项目用过什么投影 / 字段名"等元数据级检索,请用 GIS 工具(QGIS / ArcGIS)导出 `.prj` 投影信息和 `.dbf` 字段名为 `.txt`,再 ingest。
- **vsdx(Visio)**:走 LibreOffice headless 转 PDF 后接 binary 路径。**LibreOffice 不可用时永久 stub 标 `failed_no_libreoffice`**(降级,不阻塞)。安装 LibreOffice 后重跑 ingest 自动转换。**v0.2.0 release 时本机未装 LibreOffice,正向路径未实证;v0.2.1 计划回归**。
- **odf(OpenDocument)**:`.odt/.ods/.odp` 经 markitdown 处理。**v0.2.0 版本下 markitdown 0.1.5 不带 ODF converter,实际走 G15 永久 stub + `odf_status: failed_markitdown_no_odf_converter` 标记**;需正文检索请先用 LibreOffice 转 .docx 后再入库(已有完整 docx G16 路径)。markitdown 后续版本支持 ODF 时自动生效无需改代码。

## 6. 完整文档导航

| 文档 | 用途 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | AI 编程助手运行时契约 — 双轴检索(scope × behavior)/ PARA 路由协议 / 引用规范 / 红线;**每次会话必读** |
| [docs/试用指南.md](docs/试用指南.md) | 装机指南 / 推荐试用问题 / 边界说明 |
| [docs/v0.1-to-v0.2-migration.md](docs/v0.1-to-v0.2-migration.md) | **v0.1 → v0.2 迁移指南**(v0.2.0 release 起) |
| [docs/v0.2-plan.md](docs/v0.2-plan.md) | v0.2 升级实施计划(PER 协议;阶段 1-6 全部审定 v1.2) |
| [scripts/README.md](scripts/README.md) | scripts/ingest.py(scan-only + execute-plan) + search.py + archive_check.py 说明 |
| [tests/查询记录.md](tests/查询记录.md) | 评估证据(E1-E10 + V1-V7)+ 治理记录(R/G/J/F/P/W) |
| [tests/v0.2-plan-progress.md](tests/v0.2-plan-progress.md) | v0.2 升级各阶段执行进度 + W 系裁决 |
| [corpus/.fixtures/README.md](corpus/.fixtures/README.md) | 评估 fixtures 设计原则 + 16 个场景子目录↔场景表 |

## 7. v0.2 升级说明(v0.2.0 release 起)

如你正从 v0.1.0 升级到 v0.2.0,先读 [docs/v0.1-to-v0.2-migration.md](docs/v0.1-to-v0.2-migration.md)。

主要变更:

- **corpus 结构** 扁平 4 目录 → PARA 四层(`01-projects` / `02-areas` / `03-resources` / `04-archives`)
- **ingest 范式** 规则路由 → AI 语义路由(`scan-only` + `execute-plan` 两步,由 AI 在 agent loop 中读 routing_request.json + 应用 CLAUDE.md §6 PARA 路由协议)
- **检索体系** 4 素材场景 → scope × behavior 双轴(scope = PARA;behavior = 单点定位 / 盘点 / 决策溯源 / 模糊探索)
- **新格式支持** docx 嵌入图 + 嵌入表 + vsdx 降级 + odf 降级
- **frontmatter 注入** ingest 时自动给 .md / .stub.md 注入 4 字段 frontmatter(type / date / project / tags)

**v0.2.0 已知限制**:见 [release notes](https://github.com/Hugin-Z/agentic-kb-lite/releases/tag/v0.2.0)。

## 8. License + 反馈

**LICENSE**: MIT — 详见 [LICENSE](LICENSE)

**反馈**: GitHub Issues / Discussions
