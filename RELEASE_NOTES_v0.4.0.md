# v0.4.0 —— 脏文档预处理 recipe 层(可插拔 + baseline 5 能力)

## 版本范围

本 release = **v0.4.0 单一功能**:在 ingest pipeline 的 G16 文本主导分流之后、frontmatter 注入之前,加一个可插拔的脏文档预处理层(recipe),把 markitdown 的“半脏”输出加工成更适合 ripgrep 字面检索的干净结构化文本。

起因:vision(v0.3)已兜住 G15/G18(扫描件 / 图为主),但 G16 “半脏”文本无人管 —— 解析问题在上游、检索问题在下游,recipe 是这条分界线的代码化。

---

## 主要功能

### 可插拔 recipe 接口 + registry

`scripts/recipes/__init__.py`:

- `Recipe`(抽象基类):`applicable(src_path, markitdown_text) -> bool` + `process(...) -> RecipeResult`
- `RecipeResult`(dataclass):`text` / `applied` / `recipe_name` / `notes`
- `get_recipe(name="baseline") -> Recipe`:registry 入口(**写死 dict,默认只注册 baseline,惰性 import 实现类**)

tool-agnostic 落点:接口稳定,实现内部可 wrap 任何工具(subprocess / 其他 binary / 纯 Python)。**不引入动态加载 / 配置驱动 / CLI 注册参数**(不做插件框架,留下个 minor+)。

### baseline recipe 5 能力(`scripts/recipes/baseline.py`,零新依赖)

纯 stdlib,对 markitdown 半脏输出做 5 项字面后处理:

1. **孤立行合并** —— 跨页表 / 跨页段被拆成的碎行,保守回接(相邻非结构行、上行行尾无标点才合;CJK 衔接不加空格)
2. **重复空白行压缩** —— 连续 ≥3 空行 → 2 空行
3. **表格行 padding** —— 合并单元格拍扁后列数不齐的 `|` 表格行,按本块最大列数补空单元格
4. **控制字符清理** —— NBSP / 全角空格 → 普通空格;零宽字符(ZWSP / ZWNBSP)→ 删除
5. **跨页表合并**(最保守一档)—— 相邻两表 **列数相同 + 下表首行重复表头 + 上表末行非汇总行(合计/总计/小计)**,全满足才合并、删下表重复表头;判不准就不合(宁可漏合不可误合)。不做 3+ 表连续合并 / 列数不等对齐猜测 / 表头模糊匹配 / 任何语义判断。

### G16 binary `.md` 路径接入 + `recipe_applied` frontmatter 字段

- recipe hook **只在 G16 binary `.md` 路径**(markitdown 转出正文那一份)。**text / image / video / G15 / G18 分支不经 recipe,frontmatter 不加 `recipe_applied` 字段**(无 schema 污染)。
- G16 `.md` frontmatter 新增 `recipe_applied`:`baseline`(已加工)/ `none`(透传未改)/ `failed`(异常)。
- recipe 只动 markitdown 正文;其后 append 的 `.docx` 嵌入表 / 嵌入图段不经 recipe(它们是 python-docx / vision 另一条产物)。
- `INGESTED_MD` 的 ingest_log notes 附 `recipe=<状态>(动作摘要)`,便于追溯做了哪几项。

### recipe fail → fallback markitdown 原版(诚实降级)

recipe 抛任何异常 → ingest 捕获 → 用 markitdown 原版写盘(整段逐字保留,不阻断 ingest)+ frontmatter `recipe_applied: failed` + log 记降级原因。控制流保证:`md_text` 仅在加工成功时才被替换,异常路径下保持 markitdown 原值。

---

## experimental 定位(诚实 caveat,不是缺陷)

recipe 接口提供**能力齐全的 baseline 骨架**;**真实语料的检索增益验证 / 调参,由实际使用者用自有语料完成,不由本特性预先调好**。这是沿仓库 experimental 定位的诚实 caveat。

- 本 release 只保证**能力级字面变换正确性**:5 能力各有确定性合成单测(合成输入 → 人工写定预期,预期值独立于实现 → 不违反 fixture-first 反自指)。
- 不编任何“真实文档识别率 / 检索增益百分比”数字。
- 真要做语义级精细化(字段抽取 / 表头语义识别 / 复杂跨页表),是未来另写独立 recipe,不撑大 baseline。

---

## 测试

- `python scripts/recipes/test_baseline.py` —— **5 能力确定性单测,5/5 全过**。每能力 ≥1 正向(该变换)+ ≥1 负向(不该动,断言原样);能力 5 含 3 个“不该合”负向(列数不同 / 有汇总行 / 表头不重复)+ 非相邻负向 + 3 表 disjoint 边界。
- `python scripts/smoke_test.py` —— 既有 16 assert + v0.4 recipe assert(#17:接口 import + baseline 可调用)= **17/17 全过**,无回归。
- 评估记录见 `tests/查询记录.md` C 系段(C1-C5 = 能力 1-5 变换正确性)。

---

## 已知限制

### 真实语料表现待使用者验证

baseline 5 能力的变换正确性由确定性合成单测锁定,但**真实脏文档上的检索增益 / 误伤率,本 release 不提供数据**——留实际使用者用自有语料验证 + 调参。recipe 是 experimental 骨架,不预调参。

### 能力 5 markdown 分隔行残留

源表含 markdown 分隔行(`| --- |`)时,跨页表合并只删下表重复表头行,下表的重复分隔行会作为内容空行残留(对 ripgrep 检索无害)。彻底清理留未来独立 recipe。

### 能力 1 / 能力 5 是启发式

孤立行合并、跨页表合并是保守启发式,真实语料边界 case 可能漏合(by design:宁可漏合不可误合)。漏合只是没优化,不破坏数据。

---

## 向后兼容

- ingest 行为变化仅限 G16 binary `.md`:正文经 recipe 加工(默认 baseline)+ frontmatter 多一个 `recipe_applied` 字段。
- text / image / video / G15 / G18 / stub 分支**行为完全不变**,不加 `recipe_applied` 字段。
- `search.py` 检索栈、CLAUDE.md 的 LLM 4 级降级行为契约**完全不动**(`.md` 还是 `.md`,scope 不变)。
- v0.3.x 已入库材料无需任何操作;重跑 ingest 时 G16 `.md` 会经 recipe(幂等:已干净文本 `applied=False` 透传)。

---

## 致谢

- **Hugin** 拍板:recipe 同步跑(ingest 阶段)/ 替代 markitdown 输出模式 / 不动 LLM 契约 / 能力 5 最保守一档钉死 / C 系评估 = 能力变换正确性(不预调真实语料参)。
- **节奏**:PER 5 阶段;Phase 2 落盘前先跑 grep 矩阵与 plan 假设对账(冲突即停),Phase 2.5 字节级 review patch 放行,Codex 外审 no blockers 才 tag。

---

## 工作流定义(再次重申)

本项目实行 **“Codex 外审通过 = release 门禁”**:不强行收尾;找问题就修,修完再审;直到 “no blockers”。
