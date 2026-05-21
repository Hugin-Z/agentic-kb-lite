# 场景:跨 corpus 盘点(全扫 P+A+R,默认不含 Archives)

> 用户问"哪些项目用过 X / 都做过哪些类型 / 跨项目盘点" — 锚在**跨 PARA scope 的盘点**上的检索。

---

## 默认 scope

`corpus/01-projects/ + 02-areas/ + 03-resources/` 三层全扫。**默认不含 `04-archives/`**;用户明示"包括归档的"才扩入。

---

## 检索词层级偏好

第 1 轮检索词起点粒度建议 **技术名 / 产品名 / 行业大类**:

- 跨 corpus 盘点的检索词必须**跨语境通用** — 项目名 / 客户名作为锚反而会过早收窄到单项目
- 推荐起点:技术名(如 `PostGIS`)/ 产品名(如 `KingbaseGIS`)/ 行业大类(如 `数字住建`)
- 命中过多时**不收窄**(盘点本来就要多命中),改为按 scope 分组输出 + frontmatter 二档过滤
- 命中 0 时,沿同义技术名 / 上位概念扩展

---

## frontmatter 二档过滤

跨 corpus 盘点最依赖 frontmatter 做**按 scope 分组**:

- `frontmatter.project != null` → projects 类(按 project 分组)
- `frontmatter.project == null` + 命中文件在 `02-areas/` → areas 类(按 areas 子目录分组)
- `frontmatter.project == null` + 命中文件在 `03-resources/` → resources 类(按 resources 子目录分组)
- `frontmatter.date` 用于在同一 scope 内按时间倒序排列

---

## 4 行为对应的整合方式提醒

跨 corpus 盘点**主要承接 4 类行为中的"盘点"**;另外 3 类行为不常用本场景。

- **盘点(主要场景)**:
  - 必须按 PARA scope 分组输出(`📦 Projects:` / `📚 Areas:` / `📖 Resources:`),每组内再按 project / date 排序
  - 给出每个命中的**计数**(如 "Projects: 3 项目命中 / Areas: 1 模板命中 / Resources: 2 国标命中")
  - 用户问"哪些"通常想要列表 + 简短摘要,不要展开细节
- **单点定位**:跨 corpus 单点定位极少见;若出现,先用 scope 路由判断回到 projects/areas/resources 单 scope 场景
- **决策溯源**:跨 corpus 决策溯源 = 跨项目同类决策对比;按 project 分组列结论 + 引用,告知"跨项目结论不一致时全部列出,由用户判断哪个适用当前场景"
- **模糊探索**:跨 corpus 模糊探索风险大(候选过多),先用 LLM 经验缩到 3-5 个 PARA 子目录候选,再让用户挑

---

## 跨 corpus 盘点的特殊注意

- **超大命中要主动收窄**:跨 corpus 盘点单次工具调用如命中 > 15 文件,主动告知"命中过多,按 PARA scope 各取前 5 呈现;如需完整列表请用 `--max-files 50` 或先收窄检索词"
- **Archives 默认隔离**:用户明示"包括归档的 / 全部历史"再扩入 `04-archives/`;不要主动扩
- **fixtures 永远隔离**:`corpus/.fixtures/` 不在任何场景的默认 scope 内(评估用,详见 5.5 节)

---

## L3 stub 兜底关注字段

跨 corpus 盘点降到 L3 时,关注的字段**因 scope 而异**:

- projects 类 stub → `frontmatter.project` / `frontmatter.date`
- areas 类 stub → `frontmatter.tags`
- resources 类 stub → `frontmatter.tags` / `frontmatter.date`

L3 stub 命中时,answer 必须明示"原文件未入库正文,仅基于 stub 元数据指向";跨 corpus 盘点的 stub 命中通常意味着"该主题在仓库内确有素材但未全部入库正文",这本身是有价值的信号(让用户知道该往哪儿打开原文件)。
