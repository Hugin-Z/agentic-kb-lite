"""test_baseline.py —— baseline recipe 5 能力确定性单测(合成输入 → 人工写定预期)。

轻量原则:不引入 pytest,assert + main() 自跑(同 scripts/smoke_test.py 风格)。
退出码 0 = 全过。

fixture-first 说明:每个 case 的预期值是**人工按各能力 spec 写定的正确结果**,不是函数
跑出来的输出。反自指禁的是“用 baseline 自己的输出当预期值”;这里预期值独立于实现,测试
确认实现与 spec 一致。每能力 ≥1 正向 case(该变换的)+ ≥1 负向 case(不该动的,断言原样)。
能力 5 含 3 个“不该合”负向(列数不同 / 有汇总行 / 表头不重复)断言不误合。

不可见字符(NBSP/全角空格/零宽)在源码里用 chr(0x..) 构造,不写字面不可见字符 —— 保证
源码字节无歧义(byte-level review 时一眼可辨,不会把 NBSP 误认成普通空格)。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from recipes.baseline import (  # noqa: E402
    _clean_control_chars,
    _merge_orphan_lines,
    _pad_table_rows,
    _compress_blank_lines,
    _merge_cross_page_tables,
)

# 控制字符(用 chr(0x..) 构造,源码无字面不可见字符)
NBSP = chr(0x00A0)      # 不间断空格 → 归一为普通空格
FWSP = chr(0x3000)      # 全角空格 → 归一为普通空格
ZWSP = chr(0x200B)      # 零宽空格 → 删除
ZWNBSP = chr(0xFEFF)    # 零宽不换行空格 / BOM → 删除


def _eq(got, exp, label: str) -> None:
    assert got == exp, f"{label}\n  got: {got!r}\n  exp: {exp!r}"


# ---------- 能力 4 控制字符清理 ----------
def test_op4_control_chars() -> None:
    print("[op4] 控制字符清理(NBSP/全角空格/零宽)... ", end="")
    # 正向:NBSP→空格, 全角空格→空格, 零宽空格/零宽不换行→删除
    src = "甲" + NBSP + "乙" + FWSP + "丙" + ZWSP + "丁" + ZWNBSP + "戊"
    out, n = _clean_control_chars(src)
    _eq(out, "甲 乙 丙丁戊", "op4 正向 文本")     # 预期里两个空格是普通 ASCII 空格
    _eq(n, 4, "op4 正向 计数")
    # 负向:纯 ASCII / 普通汉字无控制字符 → 原样,计数 0
    clean = "clean 普通文本 no special"
    out2, n2 = _clean_control_chars(clean)
    _eq(out2, clean, "op4 负向 文本")
    _eq(n2, 0, "op4 负向 计数")
    print("✓ (正向 + 负向)")


# ---------- 能力 1 孤立行合并 ----------
def test_op1_orphan_merge() -> None:
    print("[op1] 孤立行合并(保守)... ", end="")
    # 正向:上行非结构、行尾无标点,下行续行 → CJK 衔接无空格合并
    src = "断行无标点\n续上一行。"
    out, n = _merge_orphan_lines(src)
    _eq(out, "断行无标点续上一行。", "op1 正向 文本")
    _eq(n, 1, "op1 正向 计数")
    # 负向 a:上行以句号结尾(行尾有标点)→ 不合
    src2 = "第一句结束。\n第二句独立。"
    out2, n2 = _merge_orphan_lines(src2)
    _eq(out2, src2, "op1 负向a(行尾有标点)")
    _eq(n2, 0, "op1 负向a 计数")
    # 负向 b:结构行(列表项)→ 不合
    src3 = "- 项目一\n- 项目二"
    out3, n3 = _merge_orphan_lines(src3)
    _eq(out3, src3, "op1 负向b(结构行)")
    _eq(n3, 0, "op1 负向b 计数")
    print("✓ (正向 + 负向×2)")


# ---------- 能力 3 表格行 padding ----------
def test_op3_table_pad() -> None:
    print("[op3] 表格行 padding... ", end="")
    # 正向:块内短行按最大列数补空单元格(3 列表中 1 列行 → 补 2 个空单元格)
    src = "| a | b | c |\n| x |\n"
    out, n = _pad_table_rows(src)
    _eq(out, "| a | b | c |\n| x | | |\n", "op3 正向 文本")
    _eq(n, 1, "op3 正向 计数")
    # 负向:已对齐表 → 原样,计数 0
    src2 = "| a | b |\n| c | d |\n"
    out2, n2 = _pad_table_rows(src2)
    _eq(out2, src2, "op3 负向 文本")
    _eq(n2, 0, "op3 负向 计数")
    print("✓ (正向 + 负向)")


# ---------- 能力 2 重复空白行压缩 ----------
def test_op2_blank_compress() -> None:
    print("[op2] 重复空白行压缩... ", end="")
    # 正向:4 连空行 → 2 空行(删 2)。用显式 list join 避免手数 \n
    src = "\n".join(["头", "", "", "", "", "尾"])           # 头 + 4 空行 + 尾
    out, n = _compress_blank_lines(src)
    _eq(out, "\n".join(["头", "", "", "尾"]), "op2 正向 文本")   # 头 + 2 空行 + 尾
    _eq(n, 2, "op2 正向 计数")
    # 负向:≤2 空行 → 原样
    src2 = "\n".join(["A", "", "B"])                       # 1 空行
    out2, n2 = _compress_blank_lines(src2)
    _eq(out2, src2, "op2 负向 文本")
    _eq(n2, 0, "op2 负向 计数")
    print("✓ (正向 + 负向)")


# ---------- 能力 5 跨页表合并(最保守一档)----------
def test_op5_cross_page_merge() -> None:
    print("[op5] 跨页表合并(保守)... ", end="")
    # 正向:相邻两表 列数同 + 下表重复表头 + 上表无汇总行 → 合并,删下表表头
    pos = "| 列A | 列B |\n| 1 | 2 |\n\n| 列A | 列B |\n| 3 | 4 |\n"
    out, n = _merge_cross_page_tables(pos)
    _eq(out, "| 列A | 列B |\n| 1 | 2 |\n| 3 | 4 |\n", "op5 正向 文本")
    _eq(n, 1, "op5 正向 计数")

    # 负向 1:列数不同 → 不合
    neg_cols = "| 列A | 列B |\n| 1 | 2 |\n\n| 列A | 列B | 列C |\n| 3 | 4 | 5 |\n"
    o1, n1 = _merge_cross_page_tables(neg_cols)
    _eq(o1, neg_cols, "op5 负向1(列数不同)")
    _eq(n1, 0, "op5 负向1 计数")

    # 负向 2:上表有尾部汇总行(合计)→ 不合
    neg_sum = "| 列A | 列B |\n| 1 | 2 |\n| 合计 | 3 |\n\n| 列A | 列B |\n| 3 | 4 |\n"
    o2, n2 = _merge_cross_page_tables(neg_sum)
    _eq(o2, neg_sum, "op5 负向2(有汇总行)")
    _eq(n2, 0, "op5 负向2 计数")

    # 负向 3:下表表头与上表不一致 → 不合
    neg_hdr = "| 列A | 列B |\n| 1 | 2 |\n\n| 列X | 列Y |\n| 3 | 4 |\n"
    o3, n3 = _merge_cross_page_tables(neg_hdr)
    _eq(o3, neg_hdr, "op5 负向3(表头不重复)")
    _eq(n3, 0, "op5 负向3 计数")

    # 负向 4:两表之间有非空文字(非相邻)→ 不合
    neg_adj = "| 列A | 列B |\n| 1 | 2 |\n\n一段说明\n\n| 列A | 列B |\n| 3 | 4 |\n"
    o4, n4 = _merge_cross_page_tables(neg_adj)
    _eq(o4, neg_adj, "op5 负向4(非相邻)")
    _eq(n4, 0, "op5 负向4 计数")

    # 边界:3 表连续重复表头 → 只合 disjoint 对(A+B),第 3 表不进(不做 3+ 连续)
    three = ("| 列A | 列B |\n| 1 | 2 |\n\n| 列A | 列B |\n| 3 | 4 |\n\n"
             "| 列A | 列B |\n| 5 | 6 |\n")
    o5, n5 = _merge_cross_page_tables(three)
    _eq(o5, "| 列A | 列B |\n| 1 | 2 |\n| 3 | 4 |\n\n| 列A | 列B |\n| 5 | 6 |\n",
        "op5 边界(3 表 disjoint)")
    _eq(n5, 1, "op5 边界 计数(只合 1 对)")
    print("✓ (正向 + 负向×4 + 3 表 disjoint 边界)")


def main() -> int:
    print(f"# test_baseline.py — baseline recipe 5 能力确定性单测 (Python: {sys.executable})")
    print()
    failures: list[tuple[str, str]] = []
    for name, fn in [
        ("op4 控制字符清理", test_op4_control_chars),
        ("op1 孤立行合并", test_op1_orphan_merge),
        ("op3 表格行 padding", test_op3_table_pad),
        ("op2 空白行压缩", test_op2_blank_compress),
        ("op5 跨页表合并", test_op5_cross_page_merge),
    ]:
        try:
            fn()
        except Exception as e:
            print("✗ FAIL")
            failures.append((name, str(e)))
    print()
    if not failures:
        print("# ✅ test_baseline 5/5 能力单测全过")
        return 0
    print(f"# ❌ test_baseline {len(failures)} 能力 FAIL:")
    for name, err in failures:
        print(f"  - {name}: {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
