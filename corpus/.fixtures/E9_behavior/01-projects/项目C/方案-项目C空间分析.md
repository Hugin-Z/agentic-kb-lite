---
type: 方案
date: '2025-02-08'
project: 项目C
tags: [PostGIS, 空间分析]
---

# 项目 C 空间分析方案(合成示例)

合成项目 C 同样选用 PostgreSQL + PostGIS,主要承载空间分析任务。

## 空间分析能力

PostGIS 提供 ST_Buffer / ST_Intersection / ST_Union 等核心空间分析函数,项目 C 在虚构业务场景中用到了缓冲区分析 + 叠加分析两类。
