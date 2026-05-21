---
type: 方案
date: '2024-04-20'
project: 项目B
tags: [Kingbase, 信创, 数据库选型]
---

# 项目 B 数据库选型方案(合成示例)

合成项目 B 客户有强制信创要求,本方案重点讨论数据库选型对比。

## 候选对比

| 候选 | 优势 | 劣势 |
|---|---|---|
| Kingbase V8R6 | 信创资质完整,KingbaseGIS 支持 | 部分 PostGIS 函数语法差异 |
| PostgreSQL 14 + PostGIS | 性能强,生态成熟 | 不满足信创要求 |
| 达梦 DM8 | 信创资质完整 | 空间扩展支持弱 |

## 结论:为什么选 Kingbase 不选 PostgreSQL

项目 B 选 Kingbase 不选 PostgreSQL 的核心原因是**信创合规强制要求**,客户上线前需通过等保三级测评 + 信创目录核查。PostgreSQL 因不在信创目录内,直接排除。Kingbase 在测试集上虽性能略低,但满足合规底线。
