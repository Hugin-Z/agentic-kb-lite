# CLAUDE.md

> 本文件是 Claude Code 在本仓库工作的运行时规则。每次会话启动时必读。
> 更改本文件即更改本知识库的检索行为契约,请慎重。

---

## 1. 本仓库定位

这是一个**轻量个人/部门知识库**,v0.2 起采用 **PARA 四层 corpus 组织** + **scope × behavior 双轴检索**:

### corpus 结构(PARA 四层)

| 一级目录 | 语义 | 典型场景 |
|---|---|---|
| `corpus/01-projects/` | 在做的具体项目(有客户、有合同、有 deadline);内部 5 固定子目录(01-方案 / 02-章节 / 03-纪要 / 04-调研 / 05-附图)+ 99-其他兜底 | "上次某客户那个项目怎么做的"、"项目 A 的方案在哪" |
| `corpus/02-areas/` | 长期维护的责任领域(产品方案库 / 行业解决方案 / 投标章节模板 / 技术方法论);跨项目复用 | "产品方案怎么写架构这章"、"GIS 交付方法论"|
| `corpus/03-resources/` | 参考资料(国标行标 / 行业研究 / 竞品资料 / 培训与调研);外部权威发布,只参考不维护 | "国标里地块编码字段是什么"、"CIM 国标的最新版" |
| `corpus/04-archives/` | 已交付且后续不会再用的老项目;**默认不在 P+A+R 全扫 scope**,用户明示"包括归档的"才扩入 | "之前那个老项目"、"已经交付的同类项目" |

### 检索的双轴

- **scope 维度(在哪找)**:由 LLM 在第 5 节按用户问法关键词自动路由到 PARA 一级目录
- **行为维度(怎么整合)**:由 LLM 在第 2.0 节(步骤 0)按用户问法关键词识别 4 类行为(单点定位 / 盘点 / 决策溯源 / 模糊探索),选对应整合方式

两轴正交,用户不被问任何选择题。

**底层用 ripgrep 做全库扫描,不向量化、不切分、不预处理。**

---

## 2.0 步骤 0:检索行为识别(v0.2 新增)

每次查询的第一件事是识别**检索行为模式**。这决定 LLM 后续步骤怎么整合答案 — 但**不决定**到哪儿找(scope 由第 5 节场景路由决定,行为与 scope 两轴独立)。

### 4 类行为定义

| 行为 | 触发词关键词(优先级从高到低) | 整合方式 |
|---|---|---|
| **单点定位** | "那个 / 某 / 上次 / 什么时候 / 谁 / 哪个文件" | 找最精确出处,完整引用 + 行号,单文件即可 |
| **盘点** | "哪些 / 几个 / 全部 / 列一下 / 都有什么" | 多源遍历,列表化输出 + 计数;跨项目盘点按项目分组 |
| **决策溯源** | "为什么 / 优劣 / 对比 / 选 X 不选 Y / 怎么决定的" | 多源按时间线 / 角度组织,带对比,引用要齐 |
| **模糊探索** | 问法宽泛,只有主题词没有指向词 | 给 3-5 个候选文件 + 简短摘要,让用户挑;**不要直接整合答案** |

### 触发词优先级冲突规则

- "为什么" + "某 / 那个 / 上次" → **单点定位**(指向词优先于决策词)
- "为什么" 单独出现 → 决策溯源
- "哪些" + "为什么" → **盘点**(盘点词优先于决策词)
- 无明显主导触发 → **模糊探索**(让用户挑比硬猜安全)

### 行为字段必须写入轮次状态段

第 1 轮状态段必须包含 `检索行为` 与 `行为判定依据` 两个字段(详见第 2 节步骤 2 状态段 schema)。例:

```markdown
**【轮次状态段 N=1】**
- 轮次号:1
- 检索行为:决策溯源
- 行为判定依据:"为什么"+"选 X 不选 Y" 双触发,无指向词
- 默认 scope:corpus/01-projects/(第 5 节场景路由)
- 本轮检索词:[Kingbase, 信创替代, 数据库选型]
- ...
```

### 行为稳定性

- 轮 1 写定行为,**后续轮次保持不切换**(行为决定整合方式,中途换会让答案半成品)
- 如轮 N 跑完发现行为判错(典型:判"单点定位"但命中数远超预期 → 用户实际在做盘点),轮 N+1 状态段第一行明示"**行为校正:单点定位 → 盘点,理由 XXX**",再继续

### 与 scope 路由(第 5 节)的关系

两轴正交:

- 行为(本节)决定"怎么整合答案"
- scope(第 5 节)决定"扫哪个 PARA 一级目录"
- 在 Projects 里可以做 4 类行为中任意一种,在 Areas / Resources 里也可以
- 用户**不被问任何选择题**,两轴都由 LLM 按问法关键词自动识别

---

## 2. 每次查询的 agent loop 标准工作流

> 本工作流是**有状态多轮流程**,不是单次流水线。每轮 LLM 都必须输出一个"轮次状态段",作为本轮决策的入参快照与下一轮判定的对照。
>
> **状态段时机(决策入参快照,非最终行为记录)**:LLM 在调 ripgrep 之前写完本轮状态段后,**状态段即锁**。工具结果回流后,如果实际决策与状态段所写不同(例:状态段写"继续 ripgrep",但工具结果显示 L1 命中已充分,实际应"进入答案整合"),**新决策放进下一轮状态段的第一行明示**,例如:"实际进入答案整合,上轮状态段为决策入参快照"。**状态段是决策入参的快照,不是最终行为记录;决策修正在下一轮状态段开头明示。**
>
> **硬上限**:检索词迭代 ≤ 3 轮;ripgrep 工具调用累计 ≤ 12 次(3 轮 × 4 级,v0.3 引入 L2.5 后从 9 上调)。

### 步骤 1:解析意图,匹配 PARA scope + 4 行为

按第 2.0 节(检索行为识别)+ 第 5 节(场景路由速查)双轴并行识别:

- **scope 维度**:用户问法关键词路由到 `corpus/01-projects/` / `02-areas/` / `03-resources/` / `04-archives/` 之一,或跨 corpus 盘点
- **行为维度**:单点定位 / 盘点 / 决策溯源 / 模糊探索 4 选 1

载入对应 `prompts/场景-{projects,areas,resources,跨corpus盘点}.md` 作为本次查询的场景化提示词。

判断不出来时,问用户一次;**不主动跨 scope 检索**(除非用户问法明显跨界,详见第 5 节"跨场景边界")。

### 步骤 2:第 1 轮检索词生成与状态初始化

**用户问题的措辞和文档措辞经常对不上**。这是轻量方案最大的失败模式。

第 1 轮必须先生成 **3-5 组同义/相关检索词**,覆盖业务术语和技术术语。检索词的起点粒度参考所载入的 `prompts/场景-*.md` 的"检索词层级偏好"(projects 偏主题词 + 项目锚;areas 偏章节名 / 方法名;resources 偏标准编号 + 字段词;跨corpus盘点偏技术名 / 行业大类)。

例如:

- 用户问"密码复杂度" → `["密码复杂度", "口令强度", "口令复杂度", "密码策略"]`
- 用户问"地块详情怎么展示" → `["地块详情", "地块属性", "宗地信息", "图斑详情"]`
- 用户问"数据库选型" → `["数据库选型", "数据库适配", "信创替代", "Kingbase", "达梦"]`

更多领域同义词见本文件第 6 节,持续补充。

**轮次状态段(进入步骤 3 之前必须输出,固定 schema)**:

```markdown
**【轮次状态段 N=1】**
- 轮次号:1
- 检索行为:单点定位 | 盘点 | 决策溯源 | 模糊探索      ← v0.2 新增,详见第 2.0 节
- 行为判定依据:(用户问题中含 XXX 关键词)             ← v0.2 新增
- 默认 scope:corpus/01-projects/ | 02-areas/ | ...    ← v0.2 新增,详见第 5 节
- 本轮检索词:[词1, 词2, 词3, ...]
- 上轮检索词:(本次为第 1 轮)
- 变化类型判定:(首轮,无判定)
- 判定依据:(首轮,无判定)
- 本轮决策:继续 ripgrep
```

**v0.2 新增 3 字段**(`检索行为` / `行为判定依据` / `默认 scope`)是 4 类行为 × PARA scope 双轴解耦的落地点。每轮状态段都要带,且**轮 1 写定后续不切换**(行为切换走"轮 N+1 状态段第一行明示行为校正"路径,详见第 2.0 节"行为稳定性")。

### 步骤 3:本轮检索调用(含四级降级)

> **实现边界**:以下 4 级降级工作流由 AI 编程助手(Claude Code / Codex 等)在状态段执行,通过组合调用 `scripts/search.py`(或直接调用 ripgrep)实现。`scripts/search.py` 本身是单次 ripgrep 调用的薄包装器,**不内嵌 agent loop 状态机**。本节定义的是 **LLM 行为契约**,不是 `search.py` 的功能说明。

每轮检索按 L1 → L2 → L2.5 → L3 顺序尝试,**中间任一级出现"非 noise 命中"即停止降级**,进入步骤 4 上下文取得 + 步骤 5 noise 判定与答案整合。

四级 scope 排他矩阵(应用 P1 教训:三轴显式):

| 级 | 工具(rg 模式) | 文件 scope(`-g` 参数) | 触发降级条件 |
|---|---|---|---|
| L1 | 字面匹配 | `-g '!*.stub.md' -g '!*.vision.md'`(只扫人工正文 .md) | 全空 / 全 noise → L2 |
| L2 | `-i` + 拆词模糊 | 同 L1(排除 stub 和 vision) | 全空 / 全 noise → L2.5 |
| L2.5 | 字面 + `-i`(同 L2 检索词) | `-g '*.vision.md'`(只扫 vision 转写) | 全空 / 全 noise → L3 |
| L3 | 字面(聚焦 stub 字段) | `-g '*.stub.md'`(只扫 stub 元数据) | 全空 / 全 noise → 步骤 6/7 |

**L1 — 人工正文 .md 字面匹配 + 文件名扫描(默认起点)**

v0.6 起 L1 同时扫"文件内容"与"文件名",**两条 rg 串行,工具预算计 1 次**(L1 内嵌的能力增强,非两次独立工具调用)。文件名命中合并到 L1 命中集合,无需 `(filename)` 后缀(引用文件路径本身已含文件名信息)。

参考命令:
```bash
# L1.a 内容扫(沿用 v0.5)
rg --json -e "关键词1" -e "关键词2" -e "关键词3" -g "!*.stub.md" -g "!*.vision.md" corpus/01-projects/
# L1.b 文件名扫(v0.6 新增,关键词管道过滤后给 LLM,避免全清单 context 占用)
rg --files corpus/01-projects/ | rg -i "关键词1|关键词2|关键词3"
```

**L2 — 人工正文 .md 拆词模糊**

把多字符词拆为单字/双字片段,并用 `-i` 大小写不敏感重试。**同 L1 排除 `*.stub.md` 与 `*.vision.md`**。

参考命令:
```bash
rg --json -i -e "告警|阈值|规则" -g "!*.stub.md" -g "!*.vision.md" corpus/01-projects/
```

**L2.5(v0.3 新增)— vision 转写文件扫描**

**只在 `*.vision.md` 文件中搜检索词**。vision 是 LLM 转写产物(图为主文件 / 视频抽帧),**置信度介于人工正文与 stub 元数据之间**——比 stub 含更多内容,但比人工正文多一层 OCR/识别误差。

参考命令:
```bash
rg --json -e "关键词1" -g "*.vision.md" corpus/01-projects/
```

**L3 — stub 元数据扫描**

**只在 `*.stub.md` 文件中搜检索词**,聚焦关键词、与会人、日期等元数据字段。

参考命令:
```bash
rg --json -e "关键词1" -g "*.stub.md" corpus/01-projects/
```

L3 全空或全 noise → 进入步骤 6 / 步骤 7,决定是否进入下一轮检索词迭代或承认未找到。

**fallback 与多轮 retrieval 的交互(选项 X)**:每一轮内部走完 L1→L2→L2.5→L3 四级,**3 轮上限指"检索词迭代"3 次**,工具调用预算 = 3 × 4 = 12 次。**stub 与 vision 都不允许前置使用**——L1/L2 失败才降到 L2.5,L2.5 失败才降到 L3。

**单次查询命中文件总数控制在 8 以内**。命中过多说明检索词太宽泛,需要收窄(触发步骤 6 的反向回退)。

### 步骤 4:读取上下文(按级别)

- **L1 / L2 命中文件**(人工正文 .md):读取 **命中行 ± 20 行** 作为上下文,**单文件不超过 200 行**。如果命中行数本身超过 200 行(罕见,通常意味着命中过多无效片段),需要先二次筛选检索词,触发步骤 6 反向回退。
- **L2.5 命中文件**(.vision.md):读取 **命中行 ± 30 行**(略大于 L1/L2,因 vision 转写按帧/页分节,上下文跨度更大),**单文件不超过 300 行**。**禁止基于 vision 推断图中未明文出现的细节**(详见独立的"vision 告知规则与禁令"节);需读 .vision.md 中"不确定部分"字段,若答案依赖的片段属于"不确定部分"指出的范围,引用时需告知用户。
- **L3 stub 命中文件**:stub 文件通常 ≤ 30 行,**整文件读**;但**禁止从 stub 推断正文内容**(stub 是元数据索引,G11 stub 禁令的延续),答案中必须明确标"基于 stub 元数据,原文件未入库正文,建议打开原文件"。

### 步骤 5:整合答案,必须带引用

基于读到的内容回答。**每条结论必须附引用**,格式:

```
[相对路径:起止行号]
```

例如:

> 该项目使用 Kingbase V8R6 作为信创替代数据库,空间扩展通过 KingbaseGIS 实现 [corpus/01-projects/A项目/01-方案/A项目-数据库选型.md:15-22]

**L2.5 vision 命中**:引用末加 `(vision)` 后缀,如 `[corpus/01-projects/某图.pptx.vision.md:23-30 (vision)]`,提醒答案该部分基于 LLM 转写(中等置信度)而非人工正文。

**L3 stub 命中**:引用末加 `(stub)` 后缀,如 `[corpus/01-projects/某文件.docx.stub.md:5-12 (stub)]`,提醒答案该部分基于元数据而非正文。

#### 步骤 5 补充:noise 命中的处理

ripgrep 命中是字面匹配,不是主题匹配。同一关键词可能在完全无关的语境出现(如"数据集"既出现在"研究报告国内外研究现状",也出现在"边坡 GIS demo 数据集列表")。

LLM 整合答案前必须做主题对齐判断:

1. 命中片段的上下文是否回应用户问题的主题?
2. 若命中文件的整体语境(目录路径 + 文件名前缀 + 上下文段落)与问题主题不一致,主动标注"该命中文件主题不相关,已过滤",不要混入答案
3. 过滤决策**要可追溯**——答案末尾列"已过滤的不相关命中:[文件 + 1 句理由]",让用户能回头检查 LLM 是否过度过滤
4. **全部命中都判为 noise** 时,等同于"未找到"处理,触发步骤 6 / 步骤 7 回退判断

典型应用见 `tests/查询记录.md` W1 已知脆弱点(L2 拆词 noise 副作用)与 E5 退化场景对 noise 主题对齐判定的实证。

### 步骤 6:轮间迭代评估(触发下一轮)

本轮 ripgrep(含 L1/L2/L3)结束后,若结果出现以下任一情况,作为**触发下一轮检索词迭代**的判定输入,回到步骤 2 进入第 N+1 轮——**不再是单次重试,而是进入 agent loop 下一轮**:

**6a. 命中过少(0 命中)**

- 本轮已尝试 L1→L2→L2.5→L3 四级降级,L3 仍 0 命中 → 触发轮 N+1,要求**更宽泛的同义词扩展**
- 已达硬上限(轮 = 3 或工具调用累计 = 12)且仍 0 命中,明确告知"未找到相关内容",**禁止编造**
- 给出建议:可能需要扩展素材库,或者用户的问题需要重新表述

**6b. 命中过多 + truncation 藏住关键信息**(反向回退)

- 当 ripgrep 命中文件 ≥ max-files,且 per-file truncation 把答案关键片段省略到中间区段时 → 触发轮 N+1,要求**收窄**检索词
- 收窄方向:从泛化词("段")→ 具体词("段号"),从主题词("告警")→ 字段词("告警阈值")
- 收窄后命中数应显著下降,关键信息应直接出现在前 3 处命中中
- 典型应用:第一轮检索因命中过多被 truncation 藏住关键片段时,把检索词从泛化词收窄到具体字段词,通常 1-2 处命中就能直接看到答案

**6c. 命中虽多但全是 noise**(已在步骤 5 noise 处理规则中定义)

- 全部命中文件主题与问题不一致时,等同 0 命中处理(走 6a 触发轮 N+1)
- 第二轮可换检索词维度(如从内容词换为元数据词)

### 步骤 7:轮间实质变化判定与终止

进入轮 N+1(N ≥ 1)前,LLM 必须输出第 N+1 轮的轮次状态段,并对"本轮检索词相对上轮"作**实质变化判定**。

**功能性三问**:

- **Q1**:本轮检索词是否会命中上轮命中不到的文件?
- **Q2**:本轮检索词是否会让命中文件数显著下降(收窄)?
- **Q3**:本轮检索词是否大概率命中和上轮完全相同的文件?
- **折算规则**:外文词、纯英文术语、半角缩写等"在中文素材库中默认 0 命中"的词,**不计入有效新词**

**判定表**:

| Q1  | Q2  | Q3  | 判定                  | 行为                                                                            |
| --- | --- | --- | --------------------- | ------------------------------------------------------------------------------- |
| Yes | —   | —   | 实质变化(扩展或换角度) | 允许继续,发起本轮 ripgrep                                                       |
| —   | Yes | —   | 实质变化(收窄)        | 允许继续,发起本轮 ripgrep                                                       |
| No  | No  | Yes | **实质相同 → 退化**     | **不发起本轮工具调用**;若历史轮已有命中,走答案整合;若全程 0 命中,承认"未找到" |

**判定锚点示例**(写入第 N+1 轮状态段的"判定依据"字段时可参照):

- 第 1 轮 `["告警", "报警"]` → 第 2 轮 `["告警阈值", "告警规则", "告警配置"]`:Q1=Yes(从主题词到字段词,可命中更具体段落)→ **收窄,允许继续**
- 第 1 轮 `["告警", "报警"]` → 第 2 轮 `["告警", "alert", "warning"]`:外文词折算后 0 贡献,Q1=No / Q2=No / Q3=Yes → **实质相同,退化为单轮**
- 第 1 轮 `["告警"]` → 第 2 轮 `["阈值", "规则", "通知"]`:Q1=Yes(可命中不含"告警"字样的段)→ **换角度,允许继续**

**硬上限**:

- 检索词迭代:**≤ 3 轮**;第 4 轮起强制终止,转答案整合或承认"未找到"
- 工具调用:**≤ 12 次**(3 轮 × 4 级,v0.3 引入 L2.5 后从 9 上调至 12);累计达 12 次后强制终止,不再发起 ripgrep

---

## 2.5 vision 工作流(v0.3 多模态接入)

> 唯一 vision 引擎是 Claude Code 内置 Claude 模型的原生 vision 能力(不调外部 API,不本地部署模型)。唯一外部依赖是 ffmpeg(命令行工具,跟 ripgrep 同性质)。音频转写不在本阶段(留阶段 3)。

### 2.5.1 触发判定与询问机制

`ingest.py` 跑完正常分流后,将以下 4 类文件标 vision-pending 并输出到 `logs/vision_pending_*.txt`:

- `STUB_ONLY_G15`:扫描类 PDF(markitdown 0 字符)
- `STUB_ONLY_G18`:结构性稀薄文档(密度 < 5% 且字符数 < 2000,常为图为主 PPT)
- `VISION_PENDING_IMAGE`:纯图像(`.png/.jpg/.jpeg/.gif/.bmp/.webp`)
- `VISION_PENDING_VIDEO`:视频(`.mp4/.mov/.avi/.mkv/.wmv/.flv/.webm/.m4v/.mpg/.mpeg`)

Claude Code 对话层读取该清单 → 询问用户(支持 `Y` / `N` / 行号筛选 / 类型筛选) → 按用户选择对每个文件调起对应路径转写。

用户拒绝时,在同目录 .stub.md 追加 `vision_status: skipped @YYYY-MM-DD`,避免下次 ingest 重复询问。

### 2.5.2 路径 A — 图为主文件 vision 转写

| 文件类型 | Claude Code 读取方式 |
|---|---|
| `.png/.jpg/.jpeg/.gif/.bmp/.webp` | Read 工具直接读图像 |
| `.pdf`(扫描件 G15) | Read 工具支持 PDF;大文件需 `pages` 参数分页(详见 Step 3 实证结果) |
| `.pptx`(图为主 G18,v0.4+) | **ingest.py 自动 zipfile 解嵌入图**(详见下"v0.4 .pptx 自动解嵌入图")|
| `.docx`(G16 嵌入图,v0.2 阶段 4) | **ingest.py 自动 zipfile 解嵌入图**(沿用 .pptx 三闸 + zip-slip);**vision 转写注入到原 .md 末尾 `## 嵌入图 vision 转写` 段,不单建 .vision.md**(plan §7.3 假设 6) |
| `.vsdx`(v0.2 阶段 4) | **LibreOffice headless 转 PDF → 走现有 binary 路径**;LibreOffice 不可用时永久 stub 标 `failed_no_libreoffice`(`scripts/ingest.py` `process_vsdx_to_pdf`) |
| `.ppt`(老格式) | **不支持直接读** — 用户先手动导出为 PDF / PNG 序列,再走对应路径 |

**特例 — .docx 嵌入图 vision 转写位置**(v0.2 阶段 4 新增):

不同于其他图为主文件 vision 转写产物入 `.vision.md`,.docx 嵌入图 vision 转写**直接 inject 到 G16 主 .md 末尾的 `## 嵌入图 vision 转写` 段**。理由:嵌入图是 .docx 正文的组成部分,分开存破坏阅读流。引用规范保持现有 `(vision)` 后缀机制(引用 .docx.md 中 vision 段时末加 `(vision)`)。

转写步骤(其他类型):Claude Read 读图 → 按 .vision.md schema(6 必填字段)输出 → 写入同目录 `<原文件名>.<原扩展名>.vision.md` → 同目录 .stub.md 追加 `vision_done: YYYY-MM-DD`(保持 stub 与 vision 共存)。

**v0.4 .pptx 自动解嵌入图**:`.pptx` 触发 G18 时,`ingest.py` 自动 zipfile 解 `ppt/media/*.png/jpg/jpeg/gif/bmp/webp`(**三闸过滤**:体积 ≥ 30KB + 上限 20 张 + 文件名黑名单 thumbnail/hyperlink + **zip-slip 防御**),解出图临时存放在同目录 `<带前缀 pptx 文件名>.assets/`,Claude 读图完成 vision 转写后该子目录立即删除;**.pptx 不再需要用户手动导出 PDF/PNG**。解图结果通过 stub schema 的 `vision_assets_extraction` / `vision_assets` / `vision_assets_raw_count` 三字段告知 Claude Code 对话层(4 状态:`success` / `filtered_to_zero` / `no_media_in_zip` / `failed`)。

**已知边界 — 扫描 PDF 工具链依赖**:扫描 PDF 走 vision 路径需要前置 PDF→PNG 工具(推荐 poppler,`winget install poppler`)。未安装时扫描 PDF 自动降级到 L3 stub 兜底,`vision_status` 字段记 `failed_no_pdf_converter`。

### 2.5.3 路径 B — 视频抽帧 + vision 转写

依赖检测:`ffmpeg -version` 探测。缺失则视频整批跳过(`vision_status: skipped_no_ffmpeg`),路径 A 不受影响(软依赖降级)。

抽帧密度算法(双层:scene + 上限):

```
duration = ffprobe(video)
if duration < 30s:    策略 = "极短-全帧"(每秒 1 帧,上限隐式 = 30)
elif duration < 5min:  上限 = 20
elif duration < 30min: 上限 = 50
elif duration < 60min: 上限 = 80
else:                  上限 = 100

ffmpeg scene-detect 抽到 frames_dir/(阈值 0.3)
actual = count(frames_dir)
if actual > 上限:
    每 (actual // 上限) 张保留 1 张,其余删除
```

0 帧降级链(修订 3):scene 0.3 → scene 0.1 → 按时长上限均匀采样(复用上述上限值) → 仍 0 帧标 `vision_status: failed_no_frames`。

合并:逐帧 vision → 单份 .vision.md,**叙事段(200-500 字)+ 帧明细列表(每帧带 `[MM:SS]` / `[HH:MM:SS]` 时间戳)两段并存**。

抽帧子目录 `<视频名>.<扩展名>.frames/` 在 vision 完成 + .vision.md 写入磁盘验证后**立即删除**;失败回滚时保留以便用户手动重试。

### 2.5.4 .vision.md schema(6 必填字段)

| 字段 | 语义 |
|---|---|
| 元数据头 | 文件名、类型、源相对路径、vision_ingest 时间、模型版本;路径 B 多 `时长 / 抽帧总数 / 抽帧策略` 子字段 |
| 整体描述 | 200-500 字;路径 B 额外含"帧序列叙事"子段 |
| 关键元素清单 | ≤ 20 项,每项 1 行;路径 B 按帧组织 |
| 文字识别(OCR) | 图中明文文字段,**只摘字面,不加描述** |
| 关系/流向 | 架构图/流程图节点连接;非示意类填"非示意类,无关系图" |
| 不确定部分 | Claude 自检的"看不清/识别可能误读/无法判断"部分,必填可为空 — **质量自检字段,类比阶段 1 状态段判定依据** |

**LLM 引用规则不在 schema 内**(避免双源漂移,只写在 3.5 节)。

---

## 3. 引用规范

- 路径用相对路径(相对仓库根),不用绝对路径
- 行号用 `起-止` 格式,例如 `:15-22`;单行用 `:15`
- 一个回答可以引用多个出处,不要把多处证据揉成一段不分的引用
- **L2.5 vision 命中**:引用末加 `(vision)` 后缀(如 `[corpus/01-projects/某图.pptx.vision.md:23-30 (vision)]`),提醒来源是 LLM 转写产物(中等置信度,详见独立的"vision 告知规则与禁令"节)
- **L3 stub 命中**:引用末加 `(stub)` 后缀(如 `[corpus/01-projects/某文件.docx.stub.md:5-12 (stub)]`),提醒来源类型
- 找不到出处的内容**不许写出来**——这是轻量知识库的可信度命门
- **对外发表前的脱敏责任**:agent loop transcript 中的引用与 stub / vision 元数据可能含本地绝对路径、客户名、与会人姓名等敏感字段。**transcript 直接对外发表(知乎/小红书/技术分享)前,必须由用户人工脱敏源路径字段及其他敏感元数据**;LLM 不主动脱敏(自用语境是 feature,误脱敏会丢失追溯能力)

---

## 3.5 vision 告知规则与禁令(v0.3 新增,类比 G11 stub 禁令)

> .vision.md 是 LLM(Claude Code 内置 vision 能力)对图为主文件 / 视频抽帧做的转写产物。**置信度介于人工正文(.md)与 stub 元数据(.stub.md)之间**——比 stub 含更多内容,但比人工正文多一层 OCR/识别误差。

引用 .vision.md 时必须遵守:

1. **引用末加 `(vision)` 后缀**(沿用 `(stub)` 后缀的设计,提醒来源类型)
2. **严禁基于 .vision.md 推断图中未明文出现的细节**——只能复述 .vision.md 已明文写出的内容,不可"由 vision 描述脑补图中应该有但 vision 没写的细节"
3. **必须读 .vision.md 的"不确定部分"字段**——若答案依赖的片段属于该字段指出的范围,引用时需告知用户该部分的不确定性
4. **若 .vision.md 同目录 .stub.md 含 `vision_quality: low` 标记**,答案需额外提示"该 vision 转写质量低,建议打开原文件验证"
5. **视频抽帧的 .vision.md**:答案引用时若提到具体时间点,**保留 .vision.md 中的 `[MM:SS]` / `[HH:MM:SS]` 时间戳**(短视频 / 长视频对应格式),不要省略 — 时间戳是视频引用的核心精度

---

## 4. 红线(不可违反)

- ❌ 找不到就说找不到,**禁止用模型自身知识补全**
- ❌ 不要试图改文件结构、不要重组语料、不要切分文档
- ❌ 不要主动引入向量化、rerank、切分等"RAG 优化"——这违反本知识库的设计前提
- ❌ 不要为了"答得漂亮"而省略引用
- ❌ 不要把 `corpus/` 下的内容当作可修改的(知识库是只读的,所有变更走素材入库流程)
- ❌ 单次查询读取超过 8 个文件需要先和用户确认
- ❌ **单次查询 ripgrep 工具调用累计 ≤ 12 次**(v0.3:3 轮检索词迭代 × 4 级降级,从 v0.2 的 9 次上调),累计达上限后强制终止
- ❌ **检索词迭代 ≤ 3 轮**,第 4 轮起强制终止,转答案整合或承认"未找到"
- ❌ **严禁基于 `.vision.md` 编造图中未明文出现的细节**(v0.3,vision 版的"禁止从 stub 推断正文")

---

## 5. 场景路由速查(v0.2 重写为 PARA 关键词路由)

LLM 根据用户问题关键词,自动选择默认 **corpus scope**(PARA 一级目录),并载入对应 prompt。这是双轴之一(scope 维度),与第 2.0 节的行为维度**独立**。

| 问题关键词特征 | 默认 scope | 对应 prompts |
|---|---|---|
| "上次某客户" / "那个项目" / "XX 系统" / 项目名直接出现 | `corpus/01-projects/` | `prompts/场景-projects.md` |
| "产品方案" / "标准章节" / "方法论" / "handbook" / "投标模板" | `corpus/02-areas/` | `prompts/场景-areas.md` |
| "国标" / "行标" / "行业研究" / "培训" / "调研报告" / "竞品" | `corpus/03-resources/` | `prompts/场景-resources.md` |
| "之前那个老项目" / "已经交付的" / "归档的" | `corpus/04-archives/`(**显式打开**,默认不扫) | 复用 `场景-projects.md` |
| "哪些项目" / "跨项目盘点" / "全部历史" / "都做过哪些" | 全扫 `01-projects/ + 02-areas/ + 03-resources/`(**默认不含 04-archives**) | `prompts/场景-跨corpus盘点.md` |

边界模糊时**询问用户一次**(沿用 v0.1 原则),不要默认猜。

### scope 路由 ≠ 行为识别

- **scope 路由**(本节)决定"扫哪个目录"
- **行为识别**(第 2.0 节)决定"怎么整合答案"
- 两者**独立判断**,不互相替代

例:用户问"为什么 XX 项目当时选 Kingbase 不选 PostgreSQL"
- scope = `corpus/01-projects/`(命中"XX 项目"→ projects 表)
- 行为 = 决策溯源("为什么 / 选 X 不选 Y" 触发,无指向词)
- 两轴各自落到轮 1 状态段的对应字段

### 跨场景边界

当用户问题明显跨 scope 时(如"那个项目用了什么国标"),LLM 在 agent loop 内自行扩展(从 projects 检索到引用,再到 resources 找标准原文),**不需要切换 prompts**。每个 prompts 文件末尾的"跨场景边界"段会给出该 scope 的常见跨界路径。

---

## 5.5 agent loop 评估场景的 fixtures 路径约定

> 本节为 v0.2 引入的新增契约表面,配合 `corpus/.fixtures/` 与 `tests/查询记录.md` 的 E 系 / V 系评估场景使用。v0.3 追加 V 系(vision)评估场景路径。

`tests/查询记录.md` 中 E 系评估场景(E1-E5,agent loop)与 V 系评估场景(V1-V4,vision)的本地回归测试使用 `corpus/.fixtures/<场景目录>/` 作为 ripgrep 路径,**不扫主 corpus**(`corpus/01-projects/` 等 PARA 四个一级目录)。

评估时 LLM 必须**显式把 ripgrep 路径传 `corpus/.fixtures/<场景目录>/`**,且**按四级 scope 显式排他**(v0.3),例如:

```bash
# L1.a 内容扫(只扫人工正文 .md)
rg --json -e "关键词" -g '!*.stub.md' -g '!*.vision.md' corpus/.fixtures/V1_image_ppt/

# L1.b 文件名扫(v0.6 新增,与 L1.a 串行,工具预算合并算 1 次)
rg --files corpus/.fixtures/V1_image_ppt/ | rg -i "关键词"

# L2(同 L1 排除,拆词 -i)
rg --json -i -e "关键词" -g '!*.stub.md' -g '!*.vision.md' corpus/.fixtures/V1_image_ppt/

# L2.5(只扫 .vision.md)
rg --json -e "关键词" -g '*.vision.md' corpus/.fixtures/V1_image_ppt/

# L3(只扫 .stub.md)
rg --json -e "关键词" -g '*.stub.md' corpus/.fixtures/V1_image_ppt/
```

主 corpus 与 `.fixtures/` 在物理上分离,确保:

1. fixtures 数据不污染真实素材入库后的查询结果
2. E / V 系评估可复现(fixtures 内容固定)
3. 真实素材入库不影响 E / V 系评估的判定基线

详见 `corpus/.fixtures/README.md`。

---

## 5.6 运维操作速查

> 本节为 d 小阶段引入。沉淀两类高频运维场景的速查 — LLM 在对话层遇到对应用户提问时直接套用。

### 5.6.1 索引状态查询

用户问 corpus 总览类问题(多少 .md / 多少 .vision.md / 多少 vision_pending / .assets/ 残留)时,LLM 跑下列 bash 命令生成总览,**不要靠记忆或推断**:

```bash
# 全 .md 文件计数(含 stub / vision / 正文)
find corpus -type f -name "*.md" | wc -l

# vision / stub 分类计数
find corpus -type f -name "*.vision.md" | wc -l
find corpus -type f -name "*.stub.md" | wc -l

# vision_pending 计数(stub 含 vision_pending: YES 的)
rg -c "vision_pending: YES" corpus/ -g "*.stub.md" | wc -l

# .assets/ 残留检查(预期 0;vision 转完即删,>0 提示中途失败)
find corpus -type d -name "*.assets" | wc -l

# .frames/ 残留检查(同上,视频抽帧目录,vision 转完即删)
find corpus -type d -name "*.frames" | wc -l
```

边界:LLM 跑命令前确认用户意图,避免对超大 corpus 跑无意义全扫;若 corpus 已知体量大,先在子目录上跑试试再扩展。

### 5.6.2 阈值调参

用户想调阈值时,**直接 Edit `scripts/ingest.py` 顶部常量,不引入新 CLI 参数 / 新配置文件**(轻量原则,常量直改 < 配置文件 < CLI 参数)。

常量清单(按职责分类):

- **G18 判定**(`scripts/ingest.py` line 43 附近):
  - `DENSITY_THRESHOLD = 0.05` — 字符密度上限(< 5% 触发 G18)
  - `CHAR_COUNT_THRESHOLD = 2000` — 字符总数上限(< 2000 触发 G18)
- **扩展名白名单**(`scripts/ingest.py` line 40-41):
  - `IMAGE_EXTS` — 纯图像扩展名集合(走 vision 待转)
  - `VIDEO_EXTS` — 视频扩展名集合(走 ffmpeg 抽帧)
- **.pptx 解嵌入图三闸**(`scripts/ingest.py` `extract_pptx_assets` 函数内):
  - `MIN_SIZE = 30 * 1024` — 体积闸(< 30KB 过滤为装饰图)
  - `MAX_ASSETS = 20` — 数量闸(单 .pptx 最多解 20 张,按体积降序)
  - `BLK = ("thumbnail", "hyperlink")` — 文件名黑名单

边界:改完直接重跑 ingest 即可生效;**不要为这些常量扩展 CLI 参数或配置文件**(轻量原则)。

### 5.6.3 归档候选扫描(v0.2 新增)

跑 `python scripts/archive_check.py`,输出 `logs/archive_candidates_<date>.txt`,列出 `corpus/01-projects/` 下超过 6 个月无新文件的项目候选。**LLM 不主动 mv**,只展示候选,等用户决定。

调整阈值改 `scripts/archive_check.py` 顶部 `ARCHIVE_THRESHOLD_DAYS` 常量(同 5.6.2 的"轻量原则",不引入 CLI 参数)。

---

## 6. PARA 路由协议(v0.2 新增)

本节是 ingest 时 AI 路由判断的工作说明书。当用户跑 ingest,你(AI)的工作流如下。

### 6.1 触发条件

用户对你说类似"把 D:/某目录 入库"时,你按本节协议执行:

1. Bash 调 `python scripts/ingest.py scan-only <源目录>`
2. Read `logs/routing_request.json`
3. Read `path_map.yaml`(拿 buckets 语义 + hint_subdir_keywords + explicit_mappings)
4. 按本节 6.2 流程产出路由方案
5. Write 到 `logs/routing_plan.json`
6. 展示方案给用户(不强制确认)
7. Bash 调 `python scripts/ingest.py execute-plan logs/routing_plan.json`

### 6.2 判断流程

#### Step A: 检查 explicit_mappings 优先

对每个源目录/文件,先扫 `path_map.yaml` 的 `explicit_mappings` 字段。匹配到 source 的,直接用对应 target,**跳过后续判断**。

#### Step B: 顶层目录性质判断

若 explicit_mappings 未命中,判断源目录顶层是什么类型:

- **项目目录**:看目录内容,如果包含总体方案 / 架构设计 / 纪要 / 调研等"具体工作单元交付物"迹象 → 整体落到 `01-projects/<原顶层目录名>/`,内部要进一步分流(Step C)
- **areas 类**:顶层名含"产品" / "方法论" / "投标章节" / "handbook" 关键词 → 整体落到 `02-areas/<合适子目录>/`
- **resources 类**:顶层名含"标准" / "规范" / "国标" / "行业研究" / "培训" 关键词 → 整体落到 `03-resources/<合适子目录>/`
- **archives 类**:顶层名含"已交付" / "已归档" / "已完成" → 落到 `04-archives/<原顶层目录名>/`
- **难判断**:用 Read 抽样看 1-2 个核心文件,基于内容判断,不只看目录名

#### Step C: 项目内部子目录脱钩判断

若 Step B 落到 projects,对项目内的每个子目录做脱钩判断:

判断要点:这个子目录是**项目特有**还是**跨项目可复用**?

- `标准/` `规范/` `国标/` 等 → 跨项目通用资源 → 脱钩到 `03-resources/国标行标/`,**文件名加项目前缀消歧**(如 `<项目名>_<原文件名>`)
- `行业研究/` `调研报告/` `竞品/` → 脱钩到 `03-resources/` 对应子目录
- `培训/` `分享/` → 脱钩到 `03-resources/培训与调研/`
- `纪要/` `调研/` `方案/` → 项目特有,留在项目内,按 Step D 映射到 5 子目录
- `素材/` `图片/` `截图/` → 留在项目内,落到 `05-附图/`
- `合同/` `验收/` `招标/` → 项目特有(合同是项目交付一部分),留在项目内 `99-其他/`
- **模糊的子目录 → 不要硬猜,留在项目内 `99-其他/`**

#### Step D: 单文件级路由(项目内 5 子目录映射)

对每个落到项目内的文件,判断属于哪个子目录:

- 文件名前缀 `方案-` / `设计-` / `架构-` 或文件名含"方案 / 设计 / 架构" → `01-方案/`
- 文件名前缀 `章节-` → `02-章节/`
- 文件名前缀 `纪要-` / `会议-` 或父目录是 `纪要/` → `03-纪要/`
- 文件名前缀 `调研-` / `访谈-` 或父目录是 `调研/` → `04-调研/`
- 图片扩展名(.png / .jpg / .jpeg / .gif / .bmp / .webp) → `05-附图/`
- 无前缀但内容明确 → 用 Read 看前 20 行,按内容判断
- 实在判断不出 → `99-其他/`

#### Step E: tier 判定(v0.3 新增,适用 projects + areas + resources 三 bucket)

对每个 plan item 落定 `target_bucket / target_subdir / target_filename` 后,判断 `tier`。

**适用范围**:

- `01-projects` / `02-areas` / `03-resources` 三 bucket 都做 Step E
- `04-archives` 跳过(已是 PARA 归档层,不需要再分 tier)

**判定要点**:这个文件是**主知识**还是**过程 / 版本 / 素材**?

- **canonical**(主知识 / 最终交付):文件名含 "最终" / "正文" / "建设方案" / "实施方案" / "需求说明书" / "研究报告" / "政策建议" / "审查要点" / "最终汇报";或父目录是 `01-方案/` 且内容明确是客户面前成品
- **normal**(项目内一般材料):**默认值**,无明显 working/versions/assets 特征即 normal
- **working**(过程材料):文件名前缀 `build_ / extract_ / dump_ / save_ / check_ / temp_ / test_ / demo_`;或父目录是 `临时 / 实验 / scripts / tools` 等
- **versions**(旧版本):文件名含 `v1 / v2 / v3 / 旧 / 草稿`,同系列多份(同 baseline + 版本号变化);保留最高版本为 canonical/normal,其余进 versions + family_key
- **assets**(原始素材):大量 png/jpg/mp4/shp/zip 或父目录是 `素材 / 截图 / 图片 / appendix_pages / 248_pages` 等

**约束**(沿用 v0.2.0 AI 语义路由原则):

- tier 判定**由 AI 在 routing_plan 阶段做出**,不写入 ingest.py 硬规则
- AI 看文件名 + 父目录 + 内容上下文综合判,比正则更准
- 模糊时优先 `normal`(保守 — normal 默认参与检索,误判到 working 会让材料失检索)
- versions 类必填 `family_key`(基线名 + 类型,如 `总体方案_docx` / `需求说明书_pdf`);**不可含 Windows 非法字符 `< > : " | ? * \\ /`**(Layer 6.3 强制拒)
- **v0.3 新 plan**:每个 item 必填 tier(顶层加 `"plan_schema_version": "v0.3"` 标记);**v0.2 旧 plan**:缺 tier 默认 normal(兜底)

### 6.3 输出 schema

写到 `logs/routing_plan.json`。完整 schema 见 `docs/v0.2-plan.md` §5.3 步骤 2.3。

每条 `items[i]` 必须包含:

| 字段 | 含义 |
|---|---|
| `src_abs` | 源文件绝对路径(从 routing_request.json 复制) |
| `target_bucket` | 一级目录:`01-projects` / `02-areas` / `03-resources` / `04-archives` |
| `target_project` | 仅当 bucket=01-projects 时有值,通常 = 顶层目录名 |
| `target_subdir` | bucket=01-projects 时是 5 子目录之一;否则是 areas/resources 的二级子目录 |
| `target_filename` | 目标文件名(脱钩到 resources 时**必须**加项目前缀消歧) |
| `frontmatter` | 注入到 .md 的 dict:`type / date / project / tags` |
| `ai_reason` | 路由判断理由(1-2 句话,供用户快速审) |

`frontmatter.project` 在 resources / areas 落地时**应为 null**(跨项目可复用,不绑定单项目)。

`frontmatter.date` 推断顺序:文件名形如 `YYYY-MM-DD` → 文件名日期;否则取源文件 mtime 的日期部分。

### 6.4 约束

- **不要主动改源目录命名** —— 路由完全基于读取
- **不要把可能是 resources 的内容(标准 / 国标)留在项目内** —— 跨项目可复用资源必须脱钩
- **不要把项目特有内容(纪要 / 调研)脱钩到 areas** —— 这些内容跟项目绑定
- **难判断的优先 `99-其他/`**,不要瞎归到 areas / resources —— 宁可保守归类
- **整个子目录决定前,Read 抽样看 1-2 个核心文件**,基于内容判断,不只看文件名
- **重名文件冲突时自动加项目前缀消歧**,不要覆盖原文件
- **archives_hint 关键词命中时倾向归到 archives**,但用 mtime 二次确认

### 6.5 用户介入点

`routing_plan.json` 产出后,展示给用户。用户可能:

- 没异议 → 直接跑 `execute-plan`
- 有异议 → 用户告诉你哪条不对,你修订 plan 后再展示

不需要每次都让用户敲 y 确认 —— 展示即可,用户沉默视为认可。

---

## 7. 检索词生成示例库(持续补充)

### 通用业务术语

- 密码复杂度 → 口令强度,口令复杂度,密码策略
- 数据库选型 → 数据库适配,信创替代,Kingbase,达梦,人大金仓
- 用户管理 → 账号管理,账户管理,人员管理
- 权限 → 角色,RBAC,鉴权,授权
- 部署架构 → 拓扑,部署方案,系统架构
- 接口 → API,服务,RESTful

### GIS / CIM 领域

- 地块 → 宗地,图斑,地块属性,用地图斑
- 地图操作 → 地图交互,图层操作,空间操作
- 三维场景 → 3D 场景,场景视图,数字孪生场景
- 图层 → 业务图层,数据图层,专题图层
- 空间分析 → 缓冲区分析,叠加分析,GIS 分析
- 坐标系 → CRS,投影,CGCS2000,2000 国家大地坐标系
- 大屏 → 综合展示,可视化大屏,综合监管平台
- 地图服务 → 瓦片服务,WMS,WMTS,矢量瓦片

### 项目流程术语

- 调研 → 摸底,需求采集,业务调研
- 评审 → 答辩,过会,汇报
- 验收 → 测试验收,初验,终验,试运行

(以上为种子词库,使用中持续追加。每次发现"用户用了 A 表述,文档用了 B 表述"的情况,把 A↔B 加入这里。)

---

## 8. 本文件版本管理

> CLAUDE.md 内部版本号与项目 release tag 两套并行 — 本节追踪契约文档本身的演进。项目 release tag 在 `docs/v0.2-plan.md` §12 与 git tags。

- v0.1:初始版
- **v0.7(本版,对应项目 release v0.2.0)**:PARA 四层 corpus + scope × behavior 双轴检索 + AI 语义路由 ingest + 嵌入媒体格式扩展
  - 第 1 节本仓库定位重写:从 v0.1 四类场景表 → PARA 四层 corpus 表 + 双轴检索说明
  - 新增 **第 2.0 节"步骤 0:检索行为识别"**:4 类行为定义(单点定位 / 盘点 / 决策溯源 / 模糊探索)+ 触发词优先级冲突规则 + 行为稳定性
  - 第 2 节状态段 schema 加 v0.2 新增 3 字段(`检索行为` / `行为判定依据` / `默认 scope`);硬上限补正"≤ 12 次(3 × 4 级)"(对齐其他位置)
  - 第 2.5.2 路径 A 表新增 `.docx 嵌入图`(v0.2 阶段 4)+ `.vsdx`(LibreOffice headless)两行 + ".docx 嵌入图 vision 转写位置"特例段
  - 第 5 节场景路由速查重写为 **PARA 关键词路由**(projects / areas / resources / archives / 跨corpus 盘点 5 行表)+ scope 路由 ≠ 行为识别说明 + 跨场景边界段
  - 新增 **第 5.6.3 子段"归档候选扫描"**(`scripts/archive_check.py` + `ARCHIVE_THRESHOLD_DAYS`)
  - 新增 **第 6 节"PARA 路由协议"**(98 行):6.1 触发条件 / 6.2 Step A-D 判断流程 / 6.3 输出 schema(routing_plan.json 7 字段 + frontmatter 4 字段)/ 6.4 约束 8 条 / 6.5 用户介入点
  - 原 v0.6 第 6 / 7 节顺延为 7 / 8(检索词生成示例库 / 本文件版本管理)
  - prompts/ v0.1 4 个 → v0.2 4 个完全替换(场景-projects / areas / resources / 跨corpus盘点,每个 6 段固定结构);v0.1 备份在 `tests/v0.1-prompts-archive/`
  - scripts/search.py SCENE_MAP → BUCKET_MAP / `--scene` → `--scope` / 新增 `--project` 参数;scripts/ingest.py 拆 `scan-only` + `execute-plan` 两个子命令(AI 语义路由)+ 新增 `extract_docx_assets` / `extract_docx_tables` / `process_vsdx_to_pdf` 3 个 helper + odf 异常降级
  - tests/查询记录.md 追加 E8 / E9 / E10 + W-W1 E2/E4 抽样 + V5 / V6 / V7 共 7 个新评估场景
  - 顺手修(v0.7 顺手):第 2 节硬上限 9→12(v0.3 prelude 同步漏修)+ search.py SCENE_MAP 失效(阶段 1 隐式遗漏)
  - **不在 v0.7 范围**(留 release notes / v0.2.1 / v0.3):vsdx LibreOffice 可用正向路径未实证(本机未装)/ ODF markitdown 0.1.5 不支持走 stub 降级 / 行为识别 3+ 触发词混合 case 靠 LLM 推断
- v0.2:引入 agent loop 多轮检索 + 跨工具三级降级(P0)
  - 第 2 节工作流从"单次流水线"改为"有状态多轮 agent loop";状态段时机为"决策入参快照,非最终行为记录"
  - 步骤 2 改名"第 1 轮检索词生成与状态初始化",新增轮次状态段固定 schema
  - 步骤 3 改写为"本轮检索调用(含三级降级)",定义 L1(rg 字面)/ L2(rg -i + 拆词)/ L3(stub 元数据)
  - 步骤 4 改写为"读取上下文(按级别)",L1/L2 沿用 ±20 行,L3 整文件读 + 禁止推断正文
  - 步骤 5 引用规范追加 L3 `(stub)` 后缀
  - 步骤 6 改为"轮间迭代评估(触发下一轮)",6a/6b/6c 重定位为"触发轮 N+1"判定输入
  - 新增步骤 7"轮间实质变化判定与终止",定义 Q1/Q2/Q3 功能性三问 + 退化规则
  - 红线新增 2 条上限(工具调用累计 ≤ 9 次,检索词迭代 ≤ 3 轮)
  - 新增 5.5 节 fixtures 路径约定(配合 `corpus/.fixtures/` 与 E 系评估场景)
- **v0.6(本版)**:L1 文件名扫描扩展 + 运维操作速查 + E6/E7 评估场景
  - 步骤 3 L1 描述扩展:L1 同时扫"内容" + "文件名",`rg --files <path> | rg -i <keywords>` 作为 L1.b 文件名扫,**与 L1.a 内容扫串行,工具预算合并算 1 次**;文件名命中合并到 L1 命中集合,无新增引用后缀(沿 KISS)
  - 新增 **5.6 节运维操作速查**:5.6.1 索引状态查询(5 条 bash 命令:find / wc / rg 组合)+ 5.6.2 阈值调参(G18 / 扩展名白名单 / .pptx 三闸常量清单,直 Edit ingest.py 源码,不引入 CLI 参数)
  - `tests/查询记录.md` E 系新增 **E6 / E7** 评估场景:E6 纯文件名命中(文件名有信息 + 内容无信息)/ E7 文件名误导(文件名提到 X 但内容讲 Y)
  - 配套 `corpus/.fixtures/E6_filename_only/` / `E7_filename_misleading/` 合成 fixtures(两层脱敏,P3 教训)
  - **工具预算上限保持 12**(L1 内部能力增强,非新增级别);不引入 L0 独立级别 / 不新增告知规则节 / 不新增 N 系评估编号(Plan 阶段过度应用 P1 三轴矩阵的反例,本次校正为最小化扩展)
- v0.5:增量 ingest(CLI 默认行为反转,首次升级有一次性全量重入)
  - CLI 默认行为反转:`python ingest.py <path>` 现在默认走**增量**(跳过已 ingest 且未变);不传 path → 全量(扫 corpus 根);新增 `--full` opt-out flag 显式强制全量
  - `ingest_log.jsonl` schema 新增 `src_mtime` 字段(整数秒,与 `files_equal()` mtime 比较一致);新增 SKIPPED_INCREMENTAL 计数(仅汇总段输出,不写 jsonl)
  - 新增 `load_ingest_log()` / `is_already_ingested()` 辅助函数(5 情形判定:无记录 / ERROR_* / target 被删 / size 变 / mtime 变 → 重入;完全一致 → 跳过)
  - **v0.4 → v0.5 升级注意事项**(由 Finding #v6 实证):v0.4 历史 `ingest_log.jsonl` 记录无 `src_mtime` 字段,首次跑 v0.5 增量(`python ingest.py <path>`)会被判 mtime 不等触发**一次性全量重入**(等同首次跑全量);第二次起增量正常生效。这是 by design 的诚实降级,**不要为压代码删 legacy 兼容分支**(保险起见重入比错过跳过更安全)。等 d 小阶段建好 5.6 节后,本注意事项可迁移到 5.6.3 子段
- v0.4:.pptx 自动解嵌入图(vision 路径 A 用户手动导出步骤被扫除)
  - `ingest.py` 新增 `extract_pptx_assets()`,G18 触发 .pptx 时自动 zipfile 解 `ppt/media/*` 嵌入图(三闸过滤:体积 ≥ 30KB + 上限 20 张 + thumbnail/hyperlink 名单 + zip-slip 防御);解出图放同目录 `<pptxname>.assets/`(类比 v0.3 视频 `.frames/`),vision 转完即删
  - stub schema 新增 3 字段:`vision_assets_extraction`(4 状态:`success` / `filtered_to_zero` / `no_media_in_zip` / `failed`)/ `vision_assets`(已解出图相对路径列表)/ `vision_assets_raw_count`(过滤前原图数);仅 .pptx 触发,其他 binary 类型不动
  - `is_temp_or_hidden` 扩展:跳过 `.assets/` 路径下文件(防重新 ingest 时把嵌入图当 IMAGE_EXTS 单独入库);2.5.2 节路径 A 表更新 .pptx 为"自动解嵌入图"
- v0.3:多模态接入(vision + 视频抽帧统一架构,P0)
  - 唯一 vision 引擎是 Claude Code 内置 Claude 模型原生 vision 能力(不调外部 API,不本地部署模型);唯一外部依赖 ffmpeg
  - 步骤 3 检索从三级升级为**四级降级**:L1(人工正文 .md)→ L2(同 L1 + 拆词)→ **L2.5(.vision.md,新增)**→ L3(.stub.md);每级 scope 显式排他(应用 P1 教训)
  - 步骤 4 新增 L2.5 命中文件读取规则(±30 行 / 单文件 ≤ 300 行)
  - 步骤 5 引用规范追加 `(vision)` 后缀(类比 `(stub)`)
  - 步骤 7 工具调用硬上限 9 → **12**(3 轮 × 4 级)
  - 新增 **2.5 节 vision 工作流**:路径 A(图为主文件)/ 路径 B(视频抽帧 + 双层算法 scene 0.3 + 时长上限分档);ffmpeg 软依赖降级语义
  - 新增 **3.5 节 vision 告知规则与禁令**(类比 G11):禁基于 .vision.md 推断未明文细节、视频时间戳保留 `[MM:SS]/[HH:MM:SS]`
  - 红线段:工具上限 9→12 + 新增"严禁基于 .vision.md 编造细节"
  - 第 5.5 节 fixtures 路径示例改用四级 scope(`-g '!*.stub.md' -g '!*.vision.md'` / `-g '*.vision.md'` / `-g '*.stub.md'`)
  - ingest.py 改动(主体不动,只追加):新增 `IMAGE_EXTS` / `VIDEO_EXTS` 常量 + `process_file` 两个新分支(走 `V_PENDING_IMAGE` / `V_PENDING_VIDEO` stub)+ `make_stub` 给 G15/G18/IMAGE/VIDEO 加 `vision_pending: YES` 标记 + `main` 输出 `logs/vision_pending_*.txt` + `is_temp_or_hidden` 跳过 `*.vision.md` 派生文件
  - 配套 `tests/查询记录.md` 新增 V1-V4 评估场景(V 系)
- 修订原则:
  - 每次查询效果不好且原因可归到提示词或同义词时,优先修订本文件
  - 提示词层(场景差异)的修订改 `prompts/`,不改本文件
  - 重大规则变更必须在 `tests/查询记录.md` 中记录变更动机和影响
