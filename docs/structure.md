# 目录结构说明

> 本文档是 agentic-kb-lite 的完整目录结构参考(从 README §4 外移)。
> 另含 **tier 5 类分层 ↔ 物理落位** 对照(原 README §3.7)与**完整文档索引**(原 README §6)。

---

## 1. 仓库目录树

```text
agentic-kb-lite/
├── README.md / README.en.md          # 项目说明(中文 / 英文)
├── CLAUDE.md                         # AI 编程助手运行时契约(每次会话必读)
├── LICENSE                           # MIT
├── RELEASE_NOTES_v0.3.0.md           # 版本发布说明
├── RELEASE_NOTES_v0.4.0.md
├── install.bat / install.ps1         # Windows 主安装脚本
├── setup_system_tools.bat / .ps1     # 系统工具(ffmpeg / poppler / rg)检测引导
├── setup_system_tools.sh             # 同上跨平台(macOS / Linux best effort)
├── path_map.yaml                     # buckets 语义 + hint 关键词 + explicit_mappings 兜底
├── requirements.txt                  # Python 依赖
├── .gitignore                        # 含 logs/ / .assets/ / .frames/ / tests 私有素材
├── .github/workflows/smoke.yml       # CI:Windows 上跑 smoke_test.py
│
├── corpus/                           # 素材主目录(v0.2 起 PARA 四层;实际内容不入 git)
│   ├── 01-projects/                  # 在做的具体项目;内部 5 固定子目录
│   │                                 #   (01-方案 / 02-章节 / 03-纪要 / 04-调研 / 05-附图)+ 99-其他
│   ├── 02-areas/                     # 长期维护的责任领域
│   │                                 #   (产品方案库 / 行业解决方案 / 投标章节模板 / 技术方法论)
│   ├── 03-resources/                 # 参考资料(国标行标 / 行业研究 / 竞品资料 / 培训与调研)
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
│       ├── E11_tier_routing/         # tier 4 类路由(v0.3;E10 为纯 CLI 场景,无 fixture 目录)
│       ├── V1_image_ppt/             # 图为主 PPT vision(合成脱敏)
│       ├── V2_scan_pdf/              # 扫描 PDF vision 失败降级(stub 形式,PDF 本地保留不 track)
│       ├── V3_short_video/           # 短视频抽帧 vision
│       ├── V4_medium_video/          # 中等视频双层抽帧逻辑
│       ├── V5_embedded_image/        # docx 嵌入图 vision(v0.2 阶段 4)
│       ├── V6_embedded_table/        # docx 嵌入表 python-docx 抽取(v0.2 阶段 4)
│       ├── V7_vsdx/                  # vsdx LibreOffice 降级路径(v0.2 阶段 4)
│       └── README.md                 # fixture 设计原则 + 场景表
│
├── docs/
│   ├── 试用指南.md                   # 装机 / 推荐试用问题 / 边界
│   ├── structure.md                  # 本文档:目录结构 + tier 落位 + 文档索引
│   ├── 格式支持边界.md               # xmind / shp / vsdx / odf 等格式的处置说明
│   ├── v0.1-to-v0.2-migration.md     # v0.1 → v0.2 迁移指南
│   ├── v0.2-to-v0.3-migration.md     # v0.2 → v0.3 迁移指南
│   ├── v0.2-plan.md                  # v0.2 升级实施计划(PER 协议)
│   └── v0.3-plan.md                  # v0.3 升级实施计划(PER 协议)
│
├── prompts/                          # 4 个 PARA scope 差异化提示词(v0.2)
│   ├── 场景-projects.md
│   ├── 场景-areas.md
│   ├── 场景-resources.md
│   └── 场景-跨corpus盘点.md
│
├── scripts/
│   ├── ingest.py                     # 入库主流程(scan-only + execute-plan;G14/G15/G16/G18 分流)
│   ├── search.py                     # 检索主入口(ripgrep 包装;--scope / --project / --deep)
│   ├── archive_check.py              # 归档候选扫描(6 个月无新文件的项目)
│   ├── smoke_test.py                 # 最小自动化 smoke test
│   ├── migrate_v01_to_v02.py         # v0.1 → v0.2 corpus 重组脚本
│   ├── migrate_v023_to_v030.py       # v0.2.3 → v0.3.0 tier 候选 dry-run helper(不自动 mv)
│   ├── recipes/                      # 脏文档预处理 recipe 层(v0.4)
│   │   ├── __init__.py               # Recipe 抽象基类 + RecipeResult + get_recipe registry
│   │   ├── baseline.py               # baseline recipe(5 项字面清理,零新依赖)
│   │   └── test_baseline.py          # baseline 5 能力确定性单测
│   └── README.md                     # 脚本详细说明
│
├── tests/
│   ├── 查询记录.md                   # 评估证据(E/V/C 系)+ 治理记录(R/G/J/F/P/W)
│   ├── v0.2-plan-progress.md         # v0.2 各阶段执行进度 + W 系裁决
│   ├── v0.2.1-hotfix-progress.md
│   ├── v0.2.2-hotfix-progress.md
│   ├── v0.2.3-hotfix-progress.md
│   ├── v0.3-plan-progress.md         # v0.3 各阶段执行进度 + W 系裁决
│   └── v0.1-prompts-archive/         # v0.1 4 个场景提示词备份
│
└── tools/
    ├── rg.exe                        # bundled ripgrep(Windows;v15.1.0,纳入仓库)
    ├── README.md                     # rg.exe 来源 + 版本 + MIT 分发声明
    └── LICENSE-ripgrep               # ripgrep 上游 MIT 原文(字节级一致)
```

**说明**:`corpus/` 下 PARA 四个一级目录的**实际素材内容不入 git**(`.gitignore` 排除),首次 ingest 时按需创建;开源仓中只 track `corpus/.fixtures/`。

---

## 2. tier 5 类分层与物理落位(v0.3 新增)

入库时 AI 在 routing_plan 阶段为每个文件判定 `tier`,5 类:

| tier | 语义 | 默认是否参与检索 | 物理落位 |
|---|---|---|---|
| `canonical` | 主知识 / 最终交付物(总体方案 / 实施方案 / 需求说明书等) | ✅ 参与 | 现有 5 子目录(`01-方案/` 等) |
| `normal` | 项目内一般材料(**默认值**) | ✅ 参与 | 现有 5 子目录 |
| `working` | 过程脚本 / 临时材料(`build_*` / `dump_*` / `temp_*` 等) | ❌ 不参与 | `.shelved/working/<subdir>/` |
| `versions` | 旧版本追溯(同 baseline 多份,如 `v1.docx / v2.docx`) | ❌ 不参与 | `.shelved/versions/<family_key>/` |
| `assets` | 大图片 / 视频 / GIS 原始素材(`.shp/.mp4` 大量堆放) | ❌ 不参与 | `.shelved/assets/<subdir>/` |

`tier = working / versions / assets` 落到所在 bucket 的 `.shelved/<tier>/` 子目录,`search.py` 默认排除;`04-archives` 已是 PARA 归档层,不再分 tier。

- 判定协议(Step A–E):[CLAUDE.md §6 PARA 路由协议](../CLAUDE.md)
- 追溯 `.shelved/` 内容的 `--deep` 用法:[scripts/README.md](../scripts/README.md) + [CLAUDE.md §5.6.4](../CLAUDE.md)
- 存量材料迁移:[v0.2-to-v0.3-migration.md §2.2](v0.2-to-v0.3-migration.md)

---

## 3. 完整文档索引

| 文档 | 用途 |
|---|---|
| [README.md](../README.md) / [README.en.md](../README.en.md) | 项目说明(中文 / 英文) |
| [CLAUDE.md](../CLAUDE.md) | AI 编程助手运行时契约 — 双轴检索(scope × behavior)/ PARA 路由协议 / 引用规范 / 红线;**每次会话必读** |
| [docs/试用指南.md](试用指南.md) | 装机指南 / 推荐试用问题 / 边界说明 |
| [docs/structure.md](structure.md) | 本文档:目录结构 + tier 落位 + 文档索引 |
| [docs/格式支持边界.md](格式支持边界.md) | xmind / shp / vsdx / odf 等格式的处置说明 |
| [docs/v0.1-to-v0.2-migration.md](v0.1-to-v0.2-migration.md) | **v0.1 → v0.2 迁移指南**(v0.2.0 release 起) |
| [docs/v0.2-to-v0.3-migration.md](v0.2-to-v0.3-migration.md) | **v0.2 → v0.3 迁移指南**(v0.3.0 release 起;tier 5 类 + `.shelved/` + `--deep`) |
| [docs/v0.2-plan.md](v0.2-plan.md) | v0.2 升级实施计划(PER 协议;阶段 1-6 全部审定 v1.2) |
| [docs/v0.3-plan.md](v0.3-plan.md) | v0.3 升级实施计划(PER 协议;阶段 0-4 全部 PASS) |
| [scripts/README.md](../scripts/README.md) | ingest.py(scan-only + execute-plan)/ search.py / archive_check.py / recipes 说明 |
| [tests/查询记录.md](../tests/查询记录.md) | 评估证据(E1-E11 + V1-V7 + C 系)+ 治理记录(R/G/J/F/P/W) |
| [tests/v0.2-plan-progress.md](../tests/v0.2-plan-progress.md) | v0.2 升级各阶段执行进度 + W 系裁决 |
| [tests/v0.3-plan-progress.md](../tests/v0.3-plan-progress.md) | v0.3 升级各阶段执行进度 + W 系裁决 |
| [corpus/.fixtures/README.md](../corpus/.fixtures/README.md) | 评估 fixtures 设计原则 + 场景子目录 ↔ 场景表 |
| [tools/README.md](../tools/README.md) | bundled rg.exe 来源 / 版本 / MIT 分发声明 |
| [Releases](https://github.com/Hugin-Z/agentic-kb-lite/releases) | 版本发布说明与各版本已知限制 |
