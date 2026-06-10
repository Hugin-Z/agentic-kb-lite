"""baseline.py —— 默认 recipe:markitdown 输出的轻量后处理(零新依赖,纯 stdlib)。

v0.4.0 脏文档预处理 recipe 层的默认实现。对 markitdown 转出的“半脏”文本做若干项
确定性 / 半确定性后处理,使其更适合 ripgrep 字面检索:

  能力 1 孤立行合并   —— 跨页表 / 跨页段被 markitdown 拆成的碎行,按保守启发式回接
  能力 2 重复空白行压缩 —— 连续 ≥3 空行压成 2 空行
  能力 3 表格行 padding —— 合并单元格拍扁后列数不齐的 | 表格行,按本块最大列数补 |
  能力 4 控制字符清理 —— NBSP / 全角空格 / 零宽字符归一(空格 / 删除)

能力 5(跨页表合并启发式)在 v0.4.0 **暂缓**:其 go/no-go 是 plan §8 第 4 条显式标注的
“实测-gated”决策,需对真实脱敏 anchor 实测才能定;anchor 未到位前不自合成数据自证
(fixture-first 反自指),故 baseline 先落 4 能力。§8.4 预留的 4-op 兜底“不算 scope 变更”。
anchor 到位后由 Phase 2.5 决定是否补 5。详见 RELEASE_NOTES_v0.4.0.md。

明确砍掉(scope-control,留下个 minor+):语义级清洗 / 字段抽取 / 表头语义识别 /
vision 复读 / docling 接入。baseline 只做不依赖语义理解的字面结构清理。
"""
from __future__ import annotations

import re

from . import Recipe, RecipeResult

# 能力 4:控制字符 → 归一映射(用 \u 转义,避免源码里写不可见字符无法字节核对)
_CONTROL_MAP = {
    " ": " ",   # NBSP 不间断空格 → 普通空格
    "　": " ",   # 全角空格 → 普通空格
    "​": "",    # 零宽空格 → 删除
    "‌": "",    # 零宽非连接符 → 删除
    "‍": "",    # 零宽连接符 → 删除
    "﻿": "",    # 零宽不换行空格 / BOM → 删除
}

# 能力 1:行尾含这些标点视为“句子 / 子句完整”,不与下一行合并
_PUNCT_TAIL = set("。！？；：，、…,.!?;:）)】」』”’《》<>|")


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def _is_structural(line: str) -> bool:
    """结构行(标题 / 引用 / 表格 / 列表 / 代码栅栏 / 分隔线 / 空行)不参与孤立行合并。"""
    s = line.strip()
    if s == "":
        return True
    if s.startswith(("#", ">", "|", "-", "*", "+", "```", "~~~")):
        return True
    if re.match(r"^\d+[.)、]", s):       # 有序列表 1. / 2) / 3、
        return True
    if re.match(r"^[=\-_]{3,}$", s):     # setext 下划线 / 水平线
        return True
    return False


def _clean_control_chars(text: str) -> tuple[str, int]:
    """能力 4:控制字符清理。返回(新文本, 命中字符数)。"""
    n = 0
    for ch, repl in _CONTROL_MAP.items():
        c = text.count(ch)
        if c:
            n += c
            text = text.replace(ch, repl)
    return text, n


def _merge_orphan_lines(text: str) -> tuple[str, int]:
    """能力 1:孤立行合并(保守)。

    仅当 cur 是非结构、非空、行尾无标点的行,且下一行也是非结构续行时合并;CJK 衔接
    不加空格,否则加一个空格。合并结果回填到下一行,允许链式继续合并。返回(新文本, 合并次数)。
    """
    lines = text.split("\n")
    out: list[str] = []
    merged = 0
    i = 0
    n = len(lines)
    while i < n:
        cur = lines[i]
        if (not _is_structural(cur) and cur.strip()
                and i + 1 < n and not _is_structural(lines[i + 1]) and lines[i + 1].strip()):
            cur_stripped = cur.rstrip()
            if cur_stripped and cur_stripped[-1] not in _PUNCT_TAIL:
                nxt = lines[i + 1].strip()
                if _is_cjk(cur_stripped[-1]) and _is_cjk(nxt[0]):
                    joined = cur_stripped + nxt
                else:
                    joined = cur_stripped + " " + nxt
                lines[i + 1] = joined   # 回填,下一轮看能否再并
                merged += 1
                i += 1
                continue
        out.append(cur)
        i += 1
    return "\n".join(out), merged


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def _col_count(line: str) -> int:
    return line.strip().count("|") - 1


def _pad_table_rows(text: str) -> tuple[str, int]:
    """能力 3:表格行 padding。同一连续表格块内,列数不足的行按本块最大列数补空单元格。

    返回(新文本, 补齐行数)。
    """
    lines = text.split("\n")
    out: list[str] = []
    padded = 0
    i = 0
    n = len(lines)
    while i < n:
        if _is_table_row(lines[i]):
            j = i
            while j < n and _is_table_row(lines[j]):
                j += 1
            block = lines[i:j]
            max_cols = max(_col_count(b) for b in block)
            for b in block:
                c = _col_count(b)
                if c < max_cols:
                    out.append(b.rstrip() + " |" * (max_cols - c))
                    padded += 1
                else:
                    out.append(b)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), padded


def _compress_blank_lines(text: str) -> tuple[str, int]:
    """能力 2:连续 ≥3 空行压成 2 空行。返回(新文本, 删除空行数)。"""
    lines = text.split("\n")
    out: list[str] = []
    blank_run = 0
    removed = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out.append(ln)
            else:
                removed += 1
        else:
            blank_run = 0
            out.append(ln)
    return "\n".join(out), removed


class BaselineRecipe(Recipe):
    """markitdown + 轻量后处理(能力 1-4)。零新依赖。"""

    name = "baseline"

    def applicable(self, src_path: str, markitdown_text: str) -> bool:
        # baseline 适用于任何非空 markitdown 文本;纯文本类不经此 hook(见 ingest G16 分支)
        return bool(markitdown_text and markitdown_text.strip())

    def process(self, src_path: str, markitdown_text: str) -> RecipeResult:
        text = markitdown_text
        notes: list[str] = []

        # 顺序:控制字符(4)先做(归一空白)→ 孤立行合并(1)→ 表格 padding(3)→ 空白压缩(2)收尾
        text, n4 = _clean_control_chars(text)
        if n4:
            notes.append(f"控制字符清理 {n4}")
        text, n1 = _merge_orphan_lines(text)
        if n1:
            notes.append(f"孤立行合并 {n1}")
        text, n3 = _pad_table_rows(text)
        if n3:
            notes.append(f"表格行 padding {n3}")
        text, n2 = _compress_blank_lines(text)
        if n2:
            notes.append(f"空白行压缩 {n2}")

        applied = text != markitdown_text
        note = "; ".join(notes) if notes else "无改动(透传)"
        return RecipeResult(text=text, applied=applied, recipe_name=self.name, notes=note)
