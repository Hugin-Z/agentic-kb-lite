# v0.3.0 — tier 5 类分层 + `.shelved/` 默认 search 排除

## 版本范围(v0.2.3 + v0.3.0 合并发)

本 release 包含 **v0.2.3 hotfix + v0.3.0 主要功能** 两部分。v0.2.3 不单独 release。

---

## Part A: v0.2.3 hotfix 内容(合并发布)

Codex 在 trialV3 测试仓库真实素材入库时反馈,Hugin 部分采纳(4 实质 / 拒 2 装饰):

- **TEXT_EXTS 扩展**(`.py / .csv / .geojson / .xml / .cpg / .prj / .meta / .tfw`):GIS 业务高频文本文件按原文入库,不再 `ERROR_UNSUPPORTED_EXT`
- **IMAGE_EXTS 加 `.tif / .tiff`**:TIFF 走 vision 路径 A(Claude Code 内置 vision 能力直接识别)
- **MARKITDOWN_FAILED_STUB 降级路径**:markitdown 失败不丢文件,改为"源文件 cp + stub"二件共存,装齐依赖后重跑 ingest 自动重入正文
- **UNSUPPORTED_COPY_STUB 降级路径**:未知扩展名(`.shp / .dbf / .zip / .fcs` 等)不丢文件,改为"源文件 cp + stub",LLM 检索时禁令明示"请打开源文件查看"
- smoke_test 10/10 → 12/12

**设计语义变更**:

- v0.2.2:失败 → `ERROR_*` + 不入库 + 报错
- v0.2.3:失败 → `STUB_ONLY_*` + 源文件 + stub + 可恢复

---

## Part B: v0.3.0 主要功能

### tier 5 类分层(canonical / normal / working / versions / assets)

入库时 AI 在 routing_plan 阶段判定 tier(详 CLAUDE.md §6 Step E):

- **canonical / normal**:主知识 / 一般材料,默认参与检索
- **working / versions / assets**:过程材料 / 旧版本 / 原始素材,落到 `.shelved/<tier>/` 默认不检索

**判定方式**:**AI 看文件名 + 父目录 + 内容上下文综合判**(不写代码硬规则,符合 v0.2.0 AI 语义路由原则)。

### `.shelved/` 物理目录(三 bucket × B 分散)

`projects / areas / resources` 三 bucket 内每个 subdir 独立 `.shelved/<tier>/`。`archives` bucket 不走 tier。

### `search.py --deep` flag

默认排除 `.shelved/** + .archive/**`。追溯过程材料 / 旧版本 / 素材时加 `--deep`(含 `--hidden`,真扫隐藏目录)。

### frontmatter 3 新字段

入库时 ingest 自动注入 `kb_tier / kb_default_search / family_key`(versions 类才写 family_key)。

### migration helper(dry-run only)

`scripts/migrate_v023_to_v030.py` 扫描已入库材料 → 推断 tier 候选 → 输出 `logs/v030_migration_candidates_<ts>.md` 候选清单。**不自动 mv**(自动 mv 留 v0.4+,因 mv 涉及 log / stub / .assets / frontmatter 五件套同步)。

### smoke_test 12/12 → 16/16

加 4 个 assert:

- [13/16] tier 白名单拒非法 tier(Layer 6.2)
- [14/16] `tier=working` 端到端落 `.shelved/working/`
- [15/16] family_key Windows 非法字符拒(Layer 6.3)
- [16/16] `search --deep` 三 bucket × `.shelved/` 真扫端到端(强证据断言:命中文件数 ≥ 3 + 路径含 `.shelved`)

### Layer 6 校验(REQUIRED_FIELDS_SCHEMA 6 层)

v0.2.2 5 Layer(key / type / non_empty / field-rules / path-traversal)+ v0.3 Layer 6(tier 必填 / 白名单 / family_key Windows 非法字符)。

---

## 致谢

- **Codex** 测试仓库 trialV3 现场反馈:tier 分层 + 5 类 + 8 条 plan 修订建议
- **Hugin** 拍板修订:AI 填 tier 不写硬规则 / `.shelved` 命名 / 三 bucket 适用 / dry-run only migration
- **v0.3 节奏**:整体走完 PER 5 阶段后 Codex 一次终审,通过才 release(不沿用 v0.2.2 hotfix 每轮审)

---

## 已知限制

### tier 判定误判

tier 判定靠 AI 推断,边界 case 可能误判(如文件名含 `build` 但实际是项目最终方案)。累计 ≥ 2 真实误判触发补 CLAUDE.md §6 Step E 规则(沿用 v0.2.2 W-5-W1 跟踪机制)。

### migration helper 仅 dry-run

v0.3.0 第一版 migration helper 只输出候选,不自动 mv。自动 mv 留 v0.4+(mv 涉及 `log / stub / .assets / frontmatter` 五件套同步,复杂度等价于重做一次 ingest)。

### v0.2.3 已入库材料

v0.2.3 已入库材料默认按 `tier=normal` 参与检索(可能包含本该 `.shelved` 的 working / versions / assets)。用户跑 migration helper 出候选清单,人工审 + 手动 mv + 重跑 ingest。

### v0.3 阶段 3 假阳 PASS 自捉

v0.3 阶段 4A 跑 E11 fixture 时发现阶段 3 smoke [16/16] 假阳:加 `--deep` 时漏 `--hidden`,rg 默认跳隐藏目录 → `--deep` 实际扫不到 `.shelved/`。弱断言(`keyword in stdout`)误判通过。阶段 4A 立即修复 + 断言加强(命中文件数 + 路径双判定)。

经验落定:**smoke 断言优先用结构化字段判定,跨阶段新增 flag 时端到端验证应跑真实有命中的 fixture**。

详见 [tests/v0.3-plan-progress.md](tests/v0.3-plan-progress.md) 阶段 4A W-v0.3-阶段3-W1 段。

### V1-V7 vision 路径本地无法跑回归

V 系 fixtures 需要 vision 推理 + ffmpeg/poppler 依赖。本 release 沿用 v0.2.x 阶段 5 W-2 deferred 状态,**留 release 后用户实测**。

---

## 向后兼容

- v0.2 已入库材料 + v0.2 routing_plan 完全向后兼容
- v0.2 routing_plan 重跑:自动注入 `kb_tier=normal + kb_default_search=true`,不报错
- v0.2.x → v0.3.0 升级无需任何操作(除非主动跑 migration helper)

---

## 工作流定义(再次重申)

本项目实行 **"Codex 外审通过 = release 门禁"**:

- 不强行收尾
- 找问题就修,修完再审
- 直到 "no blockers"
- 重新定义"可以 release"的标准

v0.3 节奏:整体走完 PER 5 阶段(含阶段 0 基线确认)+ Codex 一次终审,通过才 tag / push / release。
