# agentic-kb-lite

> 基于 ripgrep + LLM agent loop 的轻量个人/部门知识库。
> 核心判断:在个人/团队语料规模下,grep + 推理循环在成本、透明度、维护性上优于向量数据库 + Embedding + Rerank 的重型 RAG 栈。
> English: [README.en.md](./README.en.md) · License: [MIT](./LICENSE)

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

## 适合谁

- 你有一堆工作素材(方案/标书/纪要/调研/截图/录屏),想问"我以前是怎么做的/我们当时为什么这么决定"
- 你不想搭向量数据库 + Embedding + Rerank 的重型 RAG 栈
- 你已经在用 Claude Code / Codex 等 AI 编程助手,愿意让 AI 直接读你的素材文件

## 怎么工作

- **检索**:ripgrep 全文扫描 + LLM 多轮 agent loop,不做向量化、不做切分、不做侵入式重组
- **入库**:AI 语义路由 —— `scan-only` 扫源目录 → AI 产出 routing_plan.json → `execute-plan` 落地;重跑自动增量跳过
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
