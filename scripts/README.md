# scripts/

> 本目录是检索 pipeline 的代码区,严格控量。

**架构边界**:`search.py` 是 ripgrep 的低层包装器(单次扫描 / 文件 scope 过滤 / 正则模式开关),**不实现 agent loop**。完整 agent loop(4 级降级 / 文件名扫描 / 轮间迭代 / 状态段判定 / 实质变化判定)由 AI 编程助手(Claude Code / Codex 等)按 [CLAUDE.md](../CLAUDE.md) 契约在对话层执行,每轮调用 `search.py` 做一次 ripgrep。`search.py` 本身无"轮次"概念。

---

## search.py(主检索脚本,200 行)

### 用法

```bash
# 限定场景搜索(场景代号: 01/02/03/04/all)
.venv\Scripts\python.exe scripts/search.py --scene 01 --terms "关键词1,关键词2"

# 跨场景搜索
.venv\Scripts\python.exe scripts/search.py --scene all --terms "人名,主题词"

# 排除 stub,只搜正文(R1/R2 边界对比测试用)
.venv\Scripts\python.exe scripts/search.py --scene 04 --terms "人名,主题词" --no-stub

# 自定 context / max-files
.venv\Scripts\python.exe scripts/search.py --scene 01 --terms "告警" --context 10 --max-files 5

# 正则模式(默认 fixed-strings 字面匹配,正则需显式开)
.venv\Scripts\python.exe scripts/search.py --scene 01 --terms "原型-V[0-9]+" --regex
```

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

## ingest.py 使用

### 用法

```bash
# 单文件
.venv\Scripts\python.exe scripts/ingest.py "C:\Users\xxx\工作目录\某项目\某文件.docx"

# 目录(递归所有文件)
.venv\Scripts\python.exe scripts/ingest.py "C:\Users\xxx\工作目录\某项目"

# 干跑(首次 ingest 一个新目录的标准做法)
.venv\Scripts\python.exe scripts/ingest.py "C:\Users\xxx\工作目录\某项目" --dry-run
```

### 工作流(对应 G14-G18)

| 步骤 | 实现 | 报错停于此步? |
|---|---|---|
| 1. 查 path_map.yaml,最长前缀匹配源路径 → 得 corpus 目标二级目录 | `find_target_subdir()` | ✅ NO_MAPPING |
| 2. 按扩展名查 prefix_rules → 得 G14 前缀(`方案-` / `原型-` / ...) | `infer_prefix()` | ✅ NO_PREFIX |
| 3. 拼最终路径 = `corpus/<target>/<prefix><原文件名>` | — | — |
| 4. 同名冲突:字节+mtime 一致跳过 / 不同报错停(走 G3-G9 人工判定) | `files_equal()` | ✅ VERSION_CONFLICT |
| 5. binary(.docx/.doc/.xlsx/.pptx/.pdf):markitdown 转 md → 字符密度分流 G15(0)/G16(≥5%)/G18(<5%) | — | ✅ MARKITDOWN_FAILED |
| 6. text(.html/.txt/.md/.json):直接 `shutil.copy2` 保留 mtime | — | — |
| 7. 写一行 JSON 到 `logs/ingest_log.jsonl` | `log_action()` | — |

### path_map.yaml 维护方法

文件位置:`<repo>/path_map.yaml`(项目根)。增量维护,每次 ingest 报错时增补一条:

**遇 ERROR_NO_MAPPING**:在 `path_mappings` 加一条
```yaml
- source: "C:/Users/xxx/工作目录/某项目"  # 源绝对路径(/ 或 \\ 均可)
  target: "01-历史方案/某项目"            # corpus 二级目录(场景 + 项目名)
```

**遇 ERROR_NO_PREFIX**:在 `prefix_rules` 给该扩展名加 `default` 或 `keywords`
```yaml
".新扩展":
  default: "方案-"
```

修改 yaml 后无需重启,ingest.py 每次跑都重新读。

### 报错停的三种情形 + 处理

| 错误 | 含义 | 处理 |
|---|---|---|
| **ERROR_NO_MAPPING** | 源路径在 path_map.yaml 里没有匹配的前缀 | 在 path_mappings 加一条 source/target 后重跑 |
| **ERROR_NO_PREFIX** | 该扩展名在 prefix_rules 里没有对应规则 / 或 default 缺失 | 给 prefix_rules 补一组扩展名规则后重跑 |
| **ERROR_VERSION_CONFLICT** | corpus 目标位置已有同名文件,但字节 / mtime 不一致 | 走 G3-G9 人工判定;手动 mv corpus 中旧版到 `.archive/` 或重命名后再跑 |

(还有 ERROR_MARKITDOWN_FAILED / ERROR_UNSUPPORTED_EXT,前者是工具异常,后者是扩展名没在 BINARY/TEXT 集合内 — 都罕见)

### log 文件位置 + 字段

文件:`logs/ingest_log.jsonl`(JSON Lines)

每行一个 record:
```json
{
  "timestamp": "<ISO 8601 时间戳>",
  "source_abs_path": "C:/Users/xxx/工作目录/.../某文件.docx",
  "target_rel_path": "corpus/04-个人记忆/某项目专班/纪要-某文件.docx",
  "action": "INGESTED_MD",
  "rule_applied": "G16",
  "byte_size_src": 38693,
  "byte_size_tgt": 28818,
  "char_density": 0.7449,
  "notes": "三件共存:源 + stub + .md,字符密度 74.5%"
}
```

`action` 枚举:`INGESTED_TEXT` / `INGESTED_MD` / `STUB_ONLY_G15` / `STUB_ONLY_G18` / `SKIPPED_DUP` / `ERROR_NO_MAPPING` / `ERROR_NO_PREFIX` / `ERROR_VERSION_CONFLICT` / `ERROR_MARKITDOWN_FAILED` / `ERROR_UNSUPPORTED_EXT` / `DRY_RUN_BINARY` / `DRY_RUN_TEXT`

`rule_applied` 引用 G 规则编号(G14 前缀 / G15 扫描 stub / G16 文本主导 / G18 图形主导 stub)

### --dry-run 是首次 ingest 的标准做法

新目录第一次 ingest 前,**先 `--dry-run`** 看 ingest.py 会做什么:
- 是否把每个文件都路由到正确的 corpus 子目录(NO_MAPPING 提前暴露)
- 前缀推断对不对(NO_PREFIX 提前暴露)
- 是否会产生 VERSION_CONFLICT(对老目录二次 ingest 时常见)

dry-run 不写盘、不调 markitdown、不写 log,只打印计划动作。

### 第一版边界(留给第二版)

- ❌ 不做版本族(G3-G9)自动检测——多个 v1/v2/v3 文件目前会逐个落到 corpus,版本族压缩仍依赖人工 + G9 规则后补
- ❌ 不调 LLM —— 纯规则驱动,prefix_rules 跑不到的全走 default 或报错
- ❌ 不处理删除同步 —— 增量 only,删源不会同步删 corpus
- ❌ 不动 search.py —— 检索栈不变,corpus 怎么排都能搜
