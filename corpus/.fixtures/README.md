# corpus/.fixtures/ — E 系 + V 系评估场景固定 fixtures

> 本目录为 `tests/查询记录.md` E 系评估场景(E1-E5,agent loop)与 V 系评估场景(V1-V4,vision)的本地回归测试数据。
> **不参与主 corpus 检索**;评估场景测试时,LLM 必须显式将 ripgrep 路径传 `corpus/.fixtures/<场景目录>/`,主 corpus 不被扫到(详见 `CLAUDE.md` 第 5.5 节)。
> 配套契约首次落地版本:E 系 = `CLAUDE.md` v0.2;V 系 = `CLAUDE.md` v0.3。

---

## 设计原则

1. **匹配预期 path,不刁难 LLM**——fixtures 用于验证 agent loop 在"代表性输入"下走出预期路径,不构造反直觉边界压力测试
2. **脱敏对外可用**——内容不带项目代号、客户名、内部术语,可作为后续对外内容素材(知乎/小红书)的原始片段
3. **每场景独立子目录**——避免跨场景关键词污染;`E3_narrow` 的"告警"不会被 `E1_simple` 查询命中
4. **固定不再变更**——fixtures 是评估基线,变更需在 `tests/查询记录.md` 显式记录变更动机,否则历史回归结果不可比

---

## 子目录与场景对应

| 目录              | 评估场景 | 设计要点                                                                                      |
| ----------------- | -------- | --------------------------------------------------------------------------------------------- |
| `E1_simple/`      | E1 简单单轮 | 1 个 .md,常见技术名词"微服务架构"明文 ≥ 4 处,第 1 轮 L1 字面命中即可                       |
| `E2_expand/`      | E2 0 命中扩词 | 1 个 .md,文档全用"口令"字样不用"密码",用户问"密码复杂度"第 1 轮 0 命中,第 2 轮扩词命中 |
| `E3_narrow/`      | E3 命中过多收窄 | 4 个 .md,"告警"高频(≥ 4 个文件均含),只有"章节-接口监控-告警上报.md"含"告警阈值"具体配置 |
| `E4_stub/`        | E4 stub 兜底 | 2 个 .stub.md(分别 G15 扫描 PDF 与 G18 结构性稀薄 docx),无 .md 正文,L3 才命中             |
| `E5_degenerate/`  | E5 无效迭代退化 | 1 个 .md(主题"中心化"),用户问"边缘计算节点部署",第 1 轮 0 命中,第 2 轮中英同义词扩展应被判退化 |
| `E6_filename_only/` | E6 纯文件名命中(v0.6)| 1 个 .md,**文件名**含 `0119`/`季度复盘`,**内容**仅占位文本无业务关键词;L1.a 内容扫 0 命中 → L1.b 文件名扫命中 → L1 合并 1 文件 |
| `E7_filename_misleading/` | E7 文件名误导(v0.6)| 1 个 .md,**文件名**含"数据治理",**内容**实际讲"年度预算";L1 命中后步骤 5 noise 主题对齐发现 mismatch,答案明示"文件可能误归档" |
| `V1_image_ppt/`   | V1 图为主 PPT vision 转写 | **2.3 Review 重合成**:2 张完全脱敏的合成架构示意图(Python 标准库 PPM 直写 → ffmpeg 转 PNG,各 ~2KB)+ 2 份 .vision.md + 2 份 .stub.md;原 V1 因含真实地名/项目名/采购单位名已删除;真实图为主 PPT 的 vision 行为由 2.2 Execute Step 7 野外 sanity check(临时复制 + 跑完即删)覆盖,不留仓库 |
| `V2_scan_pdf/`    | V2 扫描 PDF 失败降级 | 1 个真扫描 PDF(0 Font + 12 Image + markitdown 0 字符)+ 1 份 .stub.md(`vision_status: failed_no_pdf_converter`);用户机未装 poppler / ImageMagick / LibreOffice,vision 无法跑通,测"失败降级"诚实性。**注**:V2 PDF 实际素材是国标 GBT35958(公开文档,用户本地保留作实证现场),开源仓通过 `tests/*.pdf` `.gitignore` 不 track;V2 stub 描述足以解释场景,无需 PDF 也能跑评估 |
| `V3_short_video/` | V3 短视频极短-全帧 | 1 个合成 6 秒 mp4(6 张纯色帧切换,6 KB)+ 1 份 .vision.md(全帧策略 fps=1)+ 1 份 .stub.md;frames_dir 已按工作流清理 |
| `V4_medium_video/`| V4 中等视频双层逻辑 | 1 个合成 5 分钟 mp4(100 个 3 秒色块切换,211 KB)+ 1 份 .vision.md(双层降级链触底:scene 0.3 → 0.1 → 1/6s 均匀采样 50 帧)+ 1 份 .stub.md(`vision_quality: low`);frames_dir 已清理 |

---

## 评估调用示例

```bash
# E1 简单单轮
rg --json -e "微服务架构" corpus/.fixtures/E1_simple/

# E2 第 1 轮(应 0 命中)
rg --json -e "密码复杂度" corpus/.fixtures/E2_expand/

# E2 第 2 轮扩词(应命中)
rg --json -e "口令强度" -e "口令复杂度" -e "密码策略" corpus/.fixtures/E2_expand/

# E3 第 1 轮泛化(应命中过多)
rg --json -e "告警" corpus/.fixtures/E3_narrow/

# E3 第 2 轮收窄(应 1-2 文件直击)
rg --json -e "告警阈值" corpus/.fixtures/E3_narrow/

# E4 L1/L2(应 0 命中)—— 必须排除 stub
rg --json -e "产品规划" -e "季度评审" -g "!*.stub.md" corpus/.fixtures/E4_stub/

# E4 L3 stub(应命中 stub 文件)
rg --json -e "产品规划" -e "季度评审" -g "*.stub.md" corpus/.fixtures/E4_stub/

# E5 第 1 轮(应 0 命中)—— 必须排除 stub
rg --json -e "边缘计算" -g "!*.stub.md" corpus/.fixtures/E5_degenerate/

# === V 系(v0.3 多模态)===

# V1 L1/L2 排除 stub 和 vision(应 0 命中,因正文 .md 不存在)
rg --json -e "分层架构" -e "横向流程" -g "!*.stub.md" -g "!*.vision.md" corpus/.fixtures/V1_image_ppt/

# V1 L2.5(应命中 vision 转写文件)
rg --json -e "分层架构" -e "横向流程" -g "*.vision.md" corpus/.fixtures/V1_image_ppt/

# V2 L1/L2(应 0 命中,扫描 PDF 无正文)
rg --json -e "农村土地" -e "承包经营权" -g "!*.stub.md" -g "!*.vision.md" corpus/.fixtures/V2_scan_pdf/

# V2 L2.5(应 0 命中,vision 失败降级,无 .vision.md)
rg --json -e "农村土地" -g "*.vision.md" corpus/.fixtures/V2_scan_pdf/

# V2 L3 stub(应命中,关键词字段 + vision_status: failed)
rg --json -e "农村土地" -e "承包经营权" -g "*.stub.md" corpus/.fixtures/V2_scan_pdf/

# V3 L2.5(应命中 vision 转写,帧明细列表含 [MM:SS] 时间戳)
rg --json -e "幻灯片" -e "纯色" -g "*.vision.md" corpus/.fixtures/V3_short_video/

# V4 L2.5(应命中 vision 转写,验证双层降级链 + 抽帧总数 50)
rg --json -e "双层" -e "抽帧" -e "色相" -g "*.vision.md" corpus/.fixtures/V4_medium_video/
```

---

## 与 tests/查询记录.md 的关系

- 每个 E / V 子目录有且只有一个 E / V 编号对应
- E / V 系评估场景的"预期 path"与本目录 fixtures 一一对应
- 评估通过标准在 `tests/查询记录.md` 中以 A / B / C 三维评分记录(V 系 C 维 / 12,沿用 v0.3 上限)
