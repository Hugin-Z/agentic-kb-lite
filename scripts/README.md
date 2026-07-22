# scripts/

> 本目录是检索 + ingest pipeline 的代码区,严格控量。v0.2 范式切换:
>
> - **ingest** 拆 `python ingest.py scan-only <src>` + `execute-plan <plan>` 两步,AI 在对话层产 routing_plan.json(详见 [CLAUDE.md §6 PARA 路由协议](../CLAUDE.md))
> - **path_map.yaml** 退化为 `buckets` 语义 + `hint_subdir_keywords` + `explicit_mappings` 兜底,**`path_mappings` / `prefix_rules` 字段已废弃**
> - **search.py** `--scope projects/areas/resources/archives/all` + `--project <名>`
> - **新增 `archive_check.py`** 归档候选扫描 + **`smoke_test.py`(v0.2.1)** 最小自动化测试

**架构边界**:`search.py` 是 ripgrep 的低层包装器(单次扫描 / 文件 scope 过滤 / 正则模式开关),**不实现 agent loop**。完整 agent loop(4 级降级 / 文件名扫描 / 轮间迭代 / 状态段判定 / 实质变化判定)由 AI 编程助手(Claude Code / Codex 等)按 [CLAUDE.md](../CLAUDE.md) 契约在对话层执行,每轮调用 `search.py` 做一次 ripgrep。`search.py` 本身无"轮次"概念。

---

## search.py(主检索脚本,200 行)

### 用法

```bash
# 限定 PARA scope 搜索(v0.2 起 --scene → --scope;projects/areas/resources/archives/all)
.venv\Scripts\python.exe scripts/search.py --scope projects --terms "关键词1,关键词2"

# 跨 corpus 搜索(默认不含 archives;P+A+R)
.venv\Scripts\python.exe scripts/search.py --scope all --terms "人名,主题词"

# 限定到单个项目(v0.2 新增 --project,自动隐含 scope=projects)
.venv\Scripts\python.exe scripts/search.py --project 智慧城市可视化平台 --terms "数据库选型"

# 排除 stub,只搜正文(R1/R2 边界对比测试用)
.venv\Scripts\python.exe scripts/search.py --scope resources --terms "人名,主题词" --no-stub

# 自定 context / max-files
.venv\Scripts\python.exe scripts/search.py --scope projects --terms "告警" --context 10 --max-files 5

# 正则模式(默认 fixed-strings 字面匹配,正则需显式开)
.venv\Scripts\python.exe scripts/search.py --scope projects --terms "原型-V[0-9]+" --regex

# 追溯过程材料 / 旧版本 / 素材(v0.3 新增 --deep)
.venv\Scripts\python.exe scripts/search.py --scope all --terms "之前的 build 脚本" --deep
```

### `--deep`:追溯 `.shelved/` 与 `.archive/`(v0.3 新增)

默认 `search.py` **不搜 `.shelved/` 与 `.archive/` 内容**(噪声分离 —— 过程脚本 / 旧版本 / 大素材不污染日常检索)。追溯时加 `--deep`:它同时去掉 glob 排除**并给 rg 加 `--hidden`**(真扫隐藏目录;v0.3.0 阶段 4A W-v0.3-阶段3-W1 修 —— 阶段 3 只去 glob 没加 `--hidden`,导致隐藏目录实际仍扫不到)。

用户问法含"之前 / 历史 / 草稿 / 版本 / 旧 / 过程 / 脚本"等关键词时,LLM 倾向加 `--deep`;常规检索问法默认不加。tier ↔ `.shelved/` 落位对照见 [docs/structure.md §2](../docs/structure.md),阈值规则见 [CLAUDE.md §5.6.4](../CLAUDE.md)。

**匹配模式**:默认走 `--fixed-strings` 字面匹配,**含正则特殊字符的检索词(括号 / 星号 / 方括号 / `+` / `?` / `.` 等)安全**——例如 `Kingbase(` / `CIM*` / `[CIM]` 都按字面查,不会触发 rg 正则错误。需要正则模式显式加 `--regex`;此模式下检索词若语法错误,rg 会报错停(returncode ≥ 2),search.py 会原样抛出 stderr 不再静默吞错。

### 工作流分工(对应 CLAUDE.md 第 2 节)

| 步骤 | 谁做 | 实现 |
|---|---|---|
| 1. 解析意图,匹配场景 | Claude Code 会话 | 看场景路由速查表 + 提示词 |
| 2. 生成 3-5 组同义检索词 | Claude Code 会话 | 看 CLAUDE.md 第 6 节同义词库 |
| 3. ripgrep 并行扫描 | **search.py** | subprocess 调 rg --json |
| 4. 读取命中行 ± 20 行 | **search.py** | rg `-C 20` + per-file ≤ 200 行截断 |
| 5. 整合答案 + 引用 | Claude Code 会话 | 看 search.py 输出的 markdown |
| 6. 回退判断 | Claude Code 会话 | 第一轮命中=0 → 生成更宽泛词 → 再调 |

### 三态输出格式

输出包含三个 H2 区:

- **一、正文命中**:`.md` / `.html` / `.txt` 等可检索正文文件
- **二、stub 命中**:进一步分两种:
  - **G16 配套元数据**(三件共存,正文在同目录 `<同名>.md`):stub 仅作元数据索引,**不触发 R2/stub 禁令**;LLM 优先读 .md 正文
  - **G15 / G18 正文未入库**(扫描件 0 字节 / R4-A 结构性稀薄):**触发 stub 禁令**,LLM 严禁推断正文,只可指引用户打开源路径
- **三、未命中检索词**:逐词显示命中分布;全 0 命中触发 CLAUDE.md 步骤 6 回退建议

```
# 检索结果
- 场景 / 检索词(匹配模式: fixed-strings|regex)/ rg 路径 / 命中文件总数

## 一、正文命中(N 份)
### corpus/<场景>/<项目>/<前缀>-<文件>.md
(N 处命中[,已截断:前 3 + 后 2,中间省略 X])
```代码块:行号 + match marker (>>>) + 上下文```

## 二、stub 命中(N 份:配套元数据 G16 共 X + 正文未入库 G15/G18/其他 共 Y)
### corpus/.../<G16 stub>.stub.md
**配套元数据**(三件共存,正文在同目录 .md),命中行号: [...]
完整 stub 元数据(含"源路径"字段 + LLM 处理规则段)

### corpus/.../<G15-G18 stub>.stub.md
⚠ **正文未入库**(stub),命中行号: [...]
完整 stub 元数据(供 LLM 推理"该问题相关有 docx/pdf,请打开源路径")

## 三、未命中检索词
(逐词命中数;全 0 命中: 已尝试 / 搜索范围 / 回退建议)

## ⚠ stub 命中处理规则(LLM 必读)
强制硬编码到输出末尾,见 LLM_RULES 常量;按"状态"字段区分 G16 vs G15/G18 处理路径
```

### 关键设计(由 G 规则驱动)

- **stub 识别**(G1):文件名以 `.stub.md` 结尾自动归 stub 区
- **跳过文件**(G14):`.references.md` 用 `--glob !.references.md`
- **per-file 命中数 truncation**:per-file 命中 > 5 时,只显示前 3 处 + 后 2 处,中间用 `... (省略 N 处命中) ...` 占位。理由:单文件多处命中容易触发 LLM 上下文过载
- **max-files 上限**(默认 8)对应 CLAUDE.md 红线第 6 条;超出仅截断 + 提示,不阻断
- **LLM 禁令文本**(R2 风险护栏):硬编码到 stdout 末尾。即使会话上下文压缩、多轮检索后 LLM 忘记规则,提示行依然在 stdout 里——硬约束 + 软提醒双层保险

---

## ripgrep 路径解析 `resolve_rg_path()`

仓库自带 `tools/rg.exe`(ripgrep 15.1.0,4.07 MB,从官方 GitHub release 下的 windows-msvc x86_64 单文件),`scripts/search.py` 的 `resolve_rg_path()` 二态查找:

```python
def resolve_rg_path():
    """优先仓库内 tools/rg.exe(bundled),fallback 系统 PATH,都没有报错。
    返回 (path, source) — source 为 'bundled' 或 'system PATH'。"""
    repo_rg = REPO / "tools" / "rg.exe"
    if repo_rg.is_file():
        return str(repo_rg), "bundled"
    sys_rg = shutil.which("rg")
    if sys_rg:
        return sys_rg, "system PATH"
    sys.stderr.write("ERROR: 未找到 ripgrep。\n")
    sys.stderr.write("  优先位置:tools/rg.exe(仓库自带,推荐)\n")
    sys.stderr.write("  fallback:系统 PATH 中的 rg\n")
    sys.stderr.write("  请确保两者之一存在。如果是首次试用,执行 install.bat 或 install.ps1 验证仓库完整性。\n")
    sys.exit(2)
```

search.py 输出 header 会显示当前命中:`(来源: bundled)` 或 `(来源: system PATH)`,便于确认环境。

### 设计取舍

- **bundled 优先**:固定版本可复现(试用者机器无论装没装系统 ripgrep 都用同一份),不会被本地 rg 版本差异搞奇怪行为
- **fallback 系统 PATH**:开发者本机若已有系统 rg,临时把 `tools/rg.exe` 改名也能跑
- **不再硬编码绝对路径列表**:旧版本曾有 `RG_BUNDLED` 列表(指向 VSCode chatgpt 插件 / Gemini CLI bundle 等位置),现已删除,完全靠仓库自带 `tools/rg.exe` 兜底

### 换机器时的处理

1. **正常情况**:重新解压完整仓库 → `tools/rg.exe` 自带 → 无需任何操作
2. **`tools/rg.exe` 缺失**(zip 解压不全 / 杀毒删了 / 误删):重新下载完整仓库,或从 <https://github.com/BurntSushi/ripgrep/releases> 下 windows-msvc 版手动放到 `tools/rg.exe`
3. **想用系统 rg**(版本不同 / 想用更新版):删 `tools/rg.exe` → fallback 自动接管,确保 `rg --version` 在 PATH 里能跑

---

## 不要做的事

- ❌ Web UI
- ❌ 向量化 / 切分 / rerank
- ✅ 素材自动入库脚本:见下方 `ingest.py 使用` 一节
- ❌ 并发 / 缓存 / 异步优化(百份级素材 ripgrep 几秒就跑完)
- ✅ docx / xlsx → md 转换基建:markitdown 已装,G16 走文本主导分流
- ⚠ PDF 文本提取:文本可选 PDF 走 G16,扫描 PDF 走 G15 永久 stub(无 OCR)

---

## ingest.py 使用(v0.2 拆 scan-only + execute-plan 两步)

### 用法

```bash
# Step 1: 扫源目录 → routing_request.json(不做任何路由判断)
.venv\Scripts\python.exe scripts/ingest.py scan-only "C:\Users\xxx\工作目录\某项目"
# → 输出 logs/routing_request.json

# Step 2(由 AI 编程助手在对话层做):
#   Read logs/routing_request.json + path_map.yaml + CLAUDE.md §6 PARA 路由协议
#   → 写出 logs/routing_plan.json(AI 判断每个文件落到 corpus 哪个 PARA bucket + 子目录)

# Step 3: 按 AI 给的 routing_plan.json 执行迁移 + frontmatter 注入
.venv\Scripts\python.exe scripts/ingest.py execute-plan logs/routing_plan.json

# 干跑(只看 plan 会做什么,不写盘)
.venv\Scripts\python.exe scripts/ingest.py execute-plan logs/routing_plan.json --dry-run
```

**典型工作流**:用户对 Claude Code 说"把 D:/工作目录/某项目 入库",Claude Code 自动跑 scan-only → 产 routing_plan → 展示给用户过目 → 跑 execute-plan,一气呵成不打扰用户。详见 [CLAUDE.md §6 PARA 路由协议](../CLAUDE.md)。

### routing_plan.json 样例(AI 产出格式参考)

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

**说明**:每个 item 的 `src_abs` / `target_bucket` / `target_subdir` / `target_filename` / `frontmatter` / `ai_reason` 必填(P0-2 路径边界校验 + v0.2.2 C-1 schema 必填集);`target_project` 仅在 `target_bucket = 01-projects` 时必填,其他 bucket(02-areas / 03-resources / 04-archives)允许为 null。`frontmatter.project` 在非 projects 类落地时应为 null。

**v0.3 起**:plan 顶层可加 `"plan_schema_version": "v0.3"`,此时每个 item 必填 `tier`(`canonical / normal / working / versions / assets`),`tier = versions` 时另必填 `family_key`(不可含 Windows 非法字符)。无 `plan_schema_version` 的 v0.2 旧 plan 完全兼容,缺 `tier` 自动按 `normal` 处理。schema 完整字段见 [CLAUDE.md §6.3](../CLAUDE.md) + [docs/v0.2-plan.md §5.3 步骤 2.3](../docs/v0.2-plan.md);tier 判定协议见 [CLAUDE.md §6.2 Step E](../CLAUDE.md)。

### 工作流(v0.2 G14-G18 沿用 v0.1,target 路径由 plan 外部给定)

| 步骤 | 实现 | 报错停于此步? |
|---|---|---|
| 0. 路径边界校验(v0.2.1 P0-2):bucket 白名单 + 拒 .. / 绝对路径 / 路径分隔符 | `_validate_plan_item_paths()` | ✅ ERROR_INVALID_PLAN_ITEM |
| 1. 临时 / 锁 / 隐藏文件早期跳过 | `is_temp_or_hidden()` | — |
| 2. v0.5 增量判定:同 src_abs + size + mtime → 跳过 | `is_already_ingested()` | — |
| 3. target_dir 从 plan item 构造 + Path.resolve().relative_to(CORPUS) 二次校验 | `_build_target_dir()` | ✅ ValueError |
| 4. 同名冲突:字节+mtime 一致跳过 / 不同报错停 | `files_equal()` | ✅ ERROR_TARGET_CONFLICT |
| 5. G2 超大守门:> 50 MB 跳过 cp + 仅 stub | — | — |
| 6. binary(.docx/.doc/.xlsx/.pptx/.pdf):markitdown 转 md → 字符密度分流 G15(0)/G16(≥5%)/G18(<5%);**v0.2 阶段 4 docx 还自动嵌入图三闸 + 嵌入表 python-docx 抽取** | — | ✅ ERROR_MARKITDOWN_FAILED |
| 7. text(.html/.txt/.md/.json):`shutil.copy2` + 可选 frontmatter 注入 | — | — |
| 8. 图像 / 视频:cp + vision-pending stub | — | — |
| 9. vsdx:LibreOffice headless 转 PDF → 现有 binary 路径;不可用降级 stub | `process_vsdx_to_pdf()` | — |
| 10. frontmatter 注入:type / date / project / tags 4 字段;resources 类 project=null | `inject_frontmatter()` | — |
| 11. 写一行 JSON 到 `logs/ingest_log.jsonl` + 单独 `logs/ingest_executed_<ts>.jsonl` | `log_action()` | — |

### path_map.yaml 维护方法(v0.2 重新设计)

v0.2 起 path_map.yaml 不再是规则匹配表,**退化为语义说明 + hints + explicit_mappings 兜底**:

- `buckets`:4 个 PARA 一级目录的语义描述(供 AI 参考)
- `hint_subdir_keywords`:`resources_hint` / `areas_hint` / `archives_hint` 三类关键词,辅助 AI 判断
- `project_subdirs`:projects 内部 5 固定子目录(`01-方案` 等)+ `99-其他`
- `explicit_mappings`:**用户偏好覆盖**(默认空 list),AI 看到 source 路径匹配则跳过常规判断

**通常不需要改 path_map.yaml** — AI 看子目录名一眼就能判断。**仅当 AI 路由不理想时**,在 `explicit_mappings` 加一条偏好兜底:

```yaml
explicit_mappings:
  - source: "C:/某客户合同包"
    target: "02-areas/合同档案/"
    reason: "目录虽含项目名,但内容是合同文档,归 areas 更合适"
```

### 报错停的几种情形 + 处理

| 错误 | 含义 | 处理 |
|---|---|---|
| **ERROR_INVALID_PLAN_ITEM**(v0.2.1)| plan items[i] 路径边界校验失败(.. / 绝对路径 / 非白名单 bucket / filename 含路径分隔符)| AI 重写 plan 该 item |
| **ERROR_TARGET_CONFLICT** | corpus 目标位置已有同名文件,但字节 / mtime 不一致 | 走 G3-G9 人工判定;手动 mv corpus 中旧版到 `.archive/` 或重命名后再跑 |
| **ERROR_MARKITDOWN_FAILED** | markitdown 转换异常(如 markitdown 缺 [docx] extra → mammoth 缺失) | `pip install markitdown[docx]` 后重跑 |
| **ERROR_UNSUPPORTED_EXT** | 扩展名不在 BINARY/TEXT/IMAGE/VIDEO/VSDX 集合内 | 罕见;具体情况具体分析 |
| **ERROR_SRC_MISSING** | plan item 指向的源文件不存在 | 检查 routing_plan.json src_abs |

### log 文件位置 + 字段

主日志:`logs/ingest_log.jsonl`(JSON Lines,追加写)
单次执行明细:`logs/ingest_executed_<timestamp>.jsonl`(execute-plan 每次跑一份)

每行一个 record:

```json
{
  "timestamp": "<ISO 8601 时间戳>",
  "source_abs_path": "C:/Users/xxx/工作目录/.../某文件.docx",
  "target_rel_path": "corpus/01-projects/某项目/03-纪要/纪要-某文件.docx",
  "action": "INGESTED_MD",
  "rule_applied": "G16",
  "byte_size_src": 38693,
  "byte_size_tgt": 28818,
  "char_density": 0.7449,
  "src_mtime": 1717340400,
  "notes": "三件共存,密度 74.5%,frontmatter=injected_new"
}
```

`action` 枚举:`INGESTED_TEXT` / `INGESTED_MD` / `STUB_ONLY_G2` / `STUB_ONLY_G15` / `STUB_ONLY_G18` / `STUB_ONLY_VSDX_NO_LIBREOFFICE` / `VISION_PENDING_IMAGE` / `VISION_PENDING_VIDEO` / `SKIPPED_DUP` / `SKIPPED_INCREMENTAL` / `SKIPPED_TEMP` / `ERROR_INVALID_PLAN_ITEM` / `ERROR_TARGET_CONFLICT` / `ERROR_MARKITDOWN_FAILED` / `ERROR_UNSUPPORTED_EXT` / `ERROR_SRC_MISSING` / `DRY_RUN_*`

`rule_applied` 引用 G 规则编号(G2 超大 / G14 前缀 [v0.2 已废] / G15 扫描 / G16 文本主导 / G18 结构性稀薄 / V_PENDING_IMAGE / V_PENDING_VIDEO / v0.2-plan-routed / vsdx+G15/G16 / v0.5-incremental)

### --dry-run 用法

`execute-plan --dry-run` 不写盘、不调 markitdown、不写 log,只打印 plan 计划的动作,用于二次确认 AI 产的 plan 是否合理。

---

## recipes/ 脏文档预处理 recipe 层(v0.4 新增)

ingest 在 G16 文本主导分流确定后、frontmatter 注入前,把 markitdown 的“半脏”输出过一道 recipe 加工,使其更适合 ripgrep 字面检索。recipe 失败 → fallback markitdown 原版(诚实降级,不阻断 ingest)。

### 接口(`scripts/recipes/__init__.py`)

- `Recipe`(抽象基类):`applicable(src_path, markitdown_text) -> bool` + `process(src_path, markitdown_text) -> RecipeResult`
- `RecipeResult`(dataclass):`text`(加工后文本)/ `applied`(是否真加工)/ `recipe_name` / `notes`(动作摘要,写 ingest_log)
- `get_recipe(name="baseline") -> Recipe`:registry 入口(写死 dict,默认 baseline;惰性 import 实现类。**不引入动态加载 / 配置驱动 / CLI 注册参数**)

### baseline(`scripts/recipes/baseline.py`,零新依赖纯 stdlib)

5 项字面后处理:

1. **孤立行合并**(保守:相邻非结构行、上行行尾无标点才合;CJK 衔接不加空格)
2. **重复空白行压缩**(连续 ≥3 空行 → 2 空行)
3. **表格行 padding**(块内列数不齐 → 按本块最大列数补空单元格)
4. **控制字符清理**(NBSP / 全角空格 → 普通空格;零宽字符 → 删除)
5. **跨页表合并**(最保守一档:相邻两表列数相同 + 下表首行重复表头 + 上表末行非汇总行,全满足才合并、删下表重复表头;判不准就不合 —— 宁可漏合不可误合)

baseline **不做**:语义级清洗 / 字段抽取 / 表头语义识别 / 跨 3+ 表连续合并 / 列数不等对齐猜测 / 表头模糊匹配 —— experimental 骨架,真实语料检索增益验证 / 调参由使用者用自有语料完成。

### ingest 接入 + frontmatter 标记

- hook **只在 G16 binary `.md` 路径**(text / image / video / G15 / G18 分支不经 recipe)
- G16 `.md` frontmatter 加 `recipe_applied`:`baseline`(已加工)/ `none`(透传未改)/ `failed`(异常 → fallback markitdown 原版)
- ingest_log 的 `INGESTED_MD` notes 附 `recipe=<状态>(动作摘要)`

### 测试

`python scripts/recipes/test_baseline.py` —— 5 能力确定性单测(合成输入 → 人工写定预期),退出码 0 = 5/5 全过。详见 `tests/查询记录.md` C 系段。

---

## archive_check.py(v0.2 新增)

```bash
.venv\Scripts\python.exe scripts/archive_check.py
# → 扫 01-projects/ 下 6 个月以上无新文件的项目作为归档候选
# → 输出 logs/archive_candidates_<date>.txt
# → 只展示候选,不自动 mv(项目可能只是暂停 ≠ 已归档)
```

阈值调整:直改 `scripts/archive_check.py` 顶部 `ARCHIVE_THRESHOLD_DAYS = 180`(轻量原则,不引入 CLI 参数)。

---

## smoke_test.py(v0.2.1 新增)

```bash
.venv\Scripts\python.exe scripts/smoke_test.py
# → 17 个核心 assert(install 调用参数 / scan-only / plan schema 三层校验 /
#   失败降级 stub / tier 路由 / search --deep / recipe 接口 等)
```

详见文件顶部注释。

### 第一版边界(留给第二版)

- ❌ 不做版本族(G3-G9)自动检测——多个 v1/v2/v3 文件目前会逐个落到 corpus,版本族压缩仍依赖人工 + G9 规则后补
- ❌ 不调 LLM —— 纯规则驱动,prefix_rules 跑不到的全走 default 或报错
- ❌ 不处理删除同步 —— 增量 only,删源不会同步删 corpus
- ❌ 不动 search.py —— 检索栈不变,corpus 怎么排都能搜
