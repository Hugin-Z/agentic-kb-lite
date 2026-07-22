# agentic-kb-lite

> 基于 ripgrep + LLM agent loop 的轻量个人/部门知识库。
> 核心判断:在个人/团队语料规模下,grep + 推理循环在成本、透明度、维护性上优于向量数据库 + Embedding + Rerank 的重型 RAG 栈。
> English: [README.en.md](./README.en.md) · License: [MIT](./LICENSE)

## 适合谁

- 你有一堆工作素材(方案/标书/纪要/调研/截图/录屏),想问"我以前是怎么做的/我们当时为什么这么决定"
- 你不想搭向量数据库 + Embedding + Rerank 的重型 RAG 栈
- 你已经在用 Claude Code / Codex 等 AI 编程助手,愿意让 AI 直接读你的素材文件

## 一次检索长什么样

(流程示意,非真实 log)

```text
你:帮我找一下之前技术标里国产化数据库适配是怎么写的

AI 编程助手(读本仓库 CLAUDE.md 契约后):
  第 1 轮  rg "国产化数据库适配"        → 0 命中
  第 2 轮  拆词扩展 rg "国产化|达梦|金仓" → 命中 3 个文件
  读正文  定位到《某项目技术标》§4.2,引用原文 + 文件路径

找不到就是找不到 —— 诚实降级是红线,严禁 AI 编造补全。
```

多轮迭代由 LLM 自主决策(扩词/收窄/换角度),3 轮硬上限、工具调用累计 ≤ 12 次。正文检索失败时按 4 级降级:正文 .md → 拆词模糊 → vision 转写文件 → stub 元数据,每级失败明确告知。

## 一次入库长什么样

(流程示意,非真实 log)

```text
你:把 D:\工作目录\智慧城市可视化平台 入库

AI:python scripts/ingest.py scan-only <src>     → 扫出文件清单
    读 CLAUDE.md 路由协议,逐个判断落位,产出 routing_plan.json:

      总体方案.docx      → 01-projects/智慧城市可视化平台/01-方案/
      需求调研纪要.md    → 01-projects/智慧城市可视化平台/04-调研/
      标准/GBT_xxx.pdf   → 03-resources/国标行标/     ← 脱钩:国标不属于任何单个项目
      已交付/2023老项目/ → 04-archives/               ← 默认不参与检索

你:看一眼 plan,确认(或在 path_map.yaml 加一条 explicit_mappings 兜底)

AI:python scripts/ingest.py execute-plan <plan>  → 落地 + 注入 frontmatter
```

## 为什么入库这一步是关键

本项目不做向量化,检索靠 ripgrep 字面匹配 —— 而字面匹配本身没有语义。**语义是在入库时由 AI 判断一次,固化成两样东西**:

- **目录位置**:文件放在哪,本身就是它的分类。这让检索可以先按 scope 收窄(只搜在做的项目 / 只搜参考资料 / 全库盘点),而不是在全量语料里撞运气
- **frontmatter**:入库时注入 `type / date / project / tags` 等结构化字段,让"2026 Q1 的方案"这类条件可以字面命中

代价是入库时要花一次 AI 判断,收益是此后每次检索都不需要 embedding 服务、不需要重建索引、结果可解释到具体文件路径。**换句话说:结构承担了向量库的职责。**

判断由 AI 做但决定权在你 —— `scan-only` 与 `execute-plan` 分两步,中间的 routing_plan.json 是可读可改的纯文本。判断不理想时在 path_map.yaml 的 `explicit_mappings` 加一条用户偏好兜底,而不是去调提示词。

物理落位细节(PARA 四层完整定义、tier 分层、`.shelved/` 排除规则)见 [docs/structure.md](docs/structure.md);routing_plan.json 完整 schema 见 [scripts/README.md](scripts/README.md)。

## 逻辑住在文本契约里,不在 Python 里

`scripts/` 下的脚本是刻意做薄的:`search.py` 是 ripgrep 的包装,`ingest.py` 负责格式转换和落盘。**真正的判断逻辑 —— PARA 路由协议、检索行为识别、4 级降级 —— 写在 [CLAUDE.md](CLAUDE.md) 里,由你正在用的 AI 编程助手读取并执行。**

这么切有三个后果:

- **不需要另调模型**。推理发生在你已经在跑的助手里,所以本仓库代码层面真的不调任何外部 API(边界见下方隐私说明)
- **换助手就能用**。Claude Code / Codex 语义等价,因为契约是纯文本而不是绑定某家 API 的代码
- **策略可读可改**。不满意降级行为就改 CLAUDE.md 的一段话,不用改代码、不用理解调用栈

代价是行为依赖助手的指令遵循能力,所以 [corpus/.fixtures/](corpus/.fixtures/) 下有可复现的回归场景来锁住它。

## 检索之外还有什么

- **scope × behavior 双轴**:**scope** 决定去哪儿找,由 PARA 结构给出(只搜在做的项目 / 只搜参考资料 / 全库盘点);**behavior** 决定怎么整合答案,按提问类型分岔(单点定位 / 盘点 / 决策溯源 / 模糊探索)。两轴由助手读契约后各自判定、正交组合,**你不会被问任何选择题**
- **tier 分层**:材料按 tier 分成主知识与过程稿 / 旧版本 / 原始素材,后三类落到 `.shelved/` 并默认排除出检索 —— 解决"旧材料不想删、但不该污染日常检索"的问题;追溯时加 `--deep` 一次性捞回。细节见 [docs/structure.md](docs/structure.md)
- **多模态**:图为主 PPT / 扫描 PDF / 视频由 AI 编程助手内置 vision 能力转写(ffmpeg 抽帧 / poppler 渲染),docx/pptx/pdf 经 markitdown 轻量转 .md
- **可评估**:10 个 agent loop fixture + 7 个多模态 fixture,可复现回归

## 隐私边界(政企用户必读)

- **本项目代码自身不调用任何外部 API**,不上传文件,仅做本机 ripgrep 扫描 + markitdown 本机转换
- **但 AI 编程助手层面**:Claude Code / Codex / Cursor 等会按各自产品机制把文件内容送入模型上下文(通常是云端推理),这层不在本项目控制范围
- 涉密/政企内部材料:改用本地模型助手(如 ollama + 本地模型),或入库前脱敏/子集化,或在隔离环境运行

## Quick Start

前置:Python 3.10-3.12 + 任一 AI 编程助手(Claude Code / Codex)。

```powershell
# Windows
git clone <repo-url> && cd agentic-kb-lite
install.bat                  # 依赖 + bundled rg.exe(v15.1.0)+ smoke test,约 3 分钟
setup_system_tools.bat       # 可选:检测 ffmpeg / poppler(仅多模态素材需要)
```

```bash
# macOS / Linux(best effort,无一键安装)
git clone <repo-url> && cd agentic-kb-lite
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./setup_system_tools.sh      # rg 需系统装,脚本会给 brew/apt 命令
```

然后用 AI 编程助手打开仓库,说:"先读 README 和 CLAUDE.md,然后把 D:\我的资料 入库"。入库完成即可开始提问。

验证环境:`python scripts/smoke_test.py`(17 个 assert,任一失败说明环境有缺)。

## 不在范围

- 不做 Web UI(定位是 AI 编程助手内的契约文档 + 脚本)
- 不做向量化/切分/Rerank
- 不做实时监听源目录同步(增量 ingest 为手动触发)
- 不重组现有文件结构、不改文件名
- 不替使用者预调脏文档 recipe 参数(baseline 骨架 + experimental 定位,真实语料调参由使用者完成)

具体格式的支持边界(xmind / shp / vsdx / odf 等)见 [docs/格式支持边界.md](docs/格式支持边界.md)。

## 深入阅读

| 文档 | 内容 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | AI 编程助手运行时契约(每次会话必读) |
| [docs/试用指南.md](docs/试用指南.md) | 装机 / 推荐试用问题 / 边界 |
| [docs/structure.md](docs/structure.md) | 完整目录结构说明 |
| [scripts/README.md](scripts/README.md) | ingest / search 脚本详解 |
| [corpus/.fixtures/README.md](corpus/.fixtures/README.md) | fixture 设计原则 + 场景表 |
| [docs/v0.1-to-v0.2-migration.md](docs/v0.1-to-v0.2-migration.md) | v0.1 → v0.2 升级说明(PARA 四层 / AI 语义路由 / 双轴检索) |
| [docs/v0.2-to-v0.3-migration.md](docs/v0.2-to-v0.3-migration.md) | v0.2 → v0.3 升级说明(tier 5 类 / `.shelved/` / `--deep`) |
| [Releases](https://github.com/Hugin-Z/agentic-kb-lite/releases) | 各版本发布说明与已知限制 |

## License + 反馈

MIT · GitHub Issues / Discussions
