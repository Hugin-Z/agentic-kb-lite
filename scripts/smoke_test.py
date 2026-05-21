"""smoke_test.py — v0.2.2 最小自动化 smoke test(单文件 10 assert)

本脚本不引入 pytest 重型测试栈(轻量原则)。v0.2.2 Codex-5th 起 10 个核心 assert,
覆盖主链路 + schema 3 层校验(key 存在 / 类型 / 非空)+ BOM 兼容 + 真实路径边界:

  1. search.py --help(install 烟测调用参数有效)
  2. ingest.py scan-only(走通基础流程)
  3. execute-plan 真实拒 3 个路径边界 malformed plan(补齐 6 字段,只让路径字段坏)
  4. 关键依赖 import(docx / yaml / markitdown 全装)
  5. execute-plan 拒绝缺 target_subdir 的 plan(schema Layer 1 key 存在)
  6. execute-plan 读 UTF-8 BOM plan(BOM 兼容)
  7. execute-plan 拒绝缺 frontmatter 的 plan(schema Layer 1 key 存在)
  8. execute-plan 拒绝缺 ai_reason 的 plan(schema Layer 1 key 存在)
  9. execute-plan 拒绝 frontmatter 非 dict 的 plan(Codex-5th schema Layer 2 类型校验)
 10. execute-plan 拒绝 target_subdir / ai_reason 空字符串的 plan(Codex-5th schema Layer 3 非空校验)

用法:
  python scripts/smoke_test.py
退出码:0 = 全 4 个 assert 过;非 0 = 至少一个失败(stderr 写明哪个)
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable  # 用当前 Python(与 install.bat / install.ps1 一致)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", **kw)


# ---------- Assert 1: search.py --help 返回 0(验证 install 调用参数有效)----------
def assert_1_search_help() -> None:
    print("[1/10] search.py --scope all --help (install 烟测调用参数)... ", end="")
    proc = _run([PY, str(REPO / "scripts" / "search.py"), "--scope", "all", "--help"])
    # --help 在 argparse 下 returncode=0 + stdout 含 usage
    assert proc.returncode == 0, f"search.py --help exit={proc.returncode}\nstderr:\n{proc.stderr}"
    assert "usage:" in proc.stdout, f"search.py --help 输出无 'usage:'\nstdout:\n{proc.stdout[:500]}"
    print("✓")


# ---------- Assert 2: scan-only 走通 + routing_request.json 生成 ----------
def assert_2_scan_only() -> None:
    print("[2/10] ingest.py scan-only corpus/.fixtures/E8_scope_routing/... ", end="")
    fixture = REPO / "corpus" / ".fixtures" / "E8_scope_routing"
    assert fixture.is_dir(), f"fixture 缺失: {fixture}"
    out = REPO / "logs" / "_smoke_test_routing_request.json"
    proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "scan-only", str(fixture),
                 "--output", str(out)])
    assert proc.returncode == 0, f"scan-only exit={proc.returncode}\nstderr:\n{proc.stderr}"
    assert out.is_file(), f"未生成 {out}"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data.get("stats", {}).get("total_files", 0) > 0, \
        f"routing_request 未扫到文件: {data.get('stats')}"
    out.unlink(missing_ok=True)
    print("✓")


# ---------- Assert 3: execute-plan 真实拒 3 个路径边界 malformed plan ----------
def assert_3_malformed_plan_rejected() -> None:
    """v0.2.2 Codex-5th 升级:6 字段全补齐,只让路径字段坏 — 这样错误是被路径校验
    拒,不是被 schema (REQUIRED_FIELDS) 拒(后者是 Layer 1,前者是 Layer 5)。"""
    print("[3/10] execute-plan 真实拒 3 个路径边界 malformed plan(Layer 5 路径穿越)... ", end="")
    base_fields = {
        "frontmatter": {},
        "ai_reason": "smoke_test 路径边界",
    }
    malformed_cases = [
        {
            "desc": "filename ../",
            "expected_keywords": ["path traversal", ".."],
            "items": [{
                "src_abs": str(REPO / "README.md"),
                "target_bucket": "01-projects",
                "target_project": "X",
                "target_subdir": "01-方案",
                "target_filename": "../../evil.txt",
                **base_fields,
            }],
        },
        {
            "desc": "bucket 非白名单",
            "expected_keywords": ["not in whitelist", "target_bucket"],
            "items": [{
                "src_abs": str(REPO / "README.md"),
                "target_bucket": "05-evil",
                "target_subdir": "x",
                "target_filename": "a.md",
                **base_fields,
            }],
        },
        {
            "desc": "filename 绝对路径前缀(Windows 盘符或 POSIX 根)",
            "expected_keywords": ["absolute path", "drive"],
            "items": [{
                "src_abs": str(REPO / "README.md"),
                "target_bucket": "02-areas",
                "target_subdir": "产品方案库",
                "target_filename": "C:\\Windows\\evil.txt",
                **base_fields,
            }],
        },
    ]
    for case in malformed_cases:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"src_root": "smoke_test", "items": case["items"]}, f, ensure_ascii=False)
            plan_file = f.name
        try:
            proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
            assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
                f"case '{case['desc']}' 应拒绝但未触发 ERROR_INVALID_PLAN_ITEM\n" \
                f"stdout:\n{proc.stdout[:800]}\nstderr:\n{proc.stderr[:400]}"
            # v0.2.2 Codex-5th:错误信息应含路径相关关键词,不应是 "missing required field"
            assert "missing required field" not in proc.stdout, \
                f"case '{case['desc']}' 应被路径校验拒,不是 schema 缺字段拒\n" \
                f"stdout:\n{proc.stdout[:800]}"
            assert any(kw in proc.stdout for kw in case["expected_keywords"]), \
                f"case '{case['desc']}' 错误信息应含路径关键词 {case['expected_keywords']}\n" \
                f"stdout:\n{proc.stdout[:800]}"
        finally:
            Path(plan_file).unlink(missing_ok=True)
    print("✓ (3 cases, real path boundary)")


# ---------- Assert 4: 关键依赖 import(docx + yaml + markitdown)----------
def assert_4_imports() -> None:
    print("[4/10] import docx + yaml + markitdown... ", end="")
    proc = _run([PY, "-c", "import docx; import yaml; import markitdown"])
    assert proc.returncode == 0, \
        f"关键依赖 import 失败 exit={proc.returncode}\nstderr:\n{proc.stderr}"
    print("✓")


# ---------- Assert 5: execute-plan 拒绝缺 target_subdir 的 plan (v0.2.2 C-1) ----------
def assert_5_missing_subdir_rejected() -> None:
    print("[5/10] execute-plan 拒绝缺 target_subdir 的 plan(schema Layer 1 key 存在)... ", end="")
    bad_plan = {
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(REPO / "README.md"),
            "target_bucket": "01-projects",
            "target_project": "X",
            # 故意缺 target_subdir(其他 5 字段都补齐,验证拒因精确到 subdir)
            "target_filename": "a.md",
            "frontmatter": {},
            "ai_reason": "smoke_test 故意缺 subdir",
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(bad_plan, f, ensure_ascii=False)
        plan_file = f.name
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
        assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
            f"缺 target_subdir 应拒但未触发 ERROR_INVALID_PLAN_ITEM\n" \
            f"stdout:\n{proc.stdout[:800]}\nstderr:\n{proc.stderr[:400]}"
        assert "target_subdir" in proc.stdout, \
            f"拒绝原因应提及 target_subdir\nstdout:\n{proc.stdout[:800]}"
    finally:
        Path(plan_file).unlink(missing_ok=True)
    print("✓")


# ---------- Assert 6: execute-plan 能读 UTF-8 BOM plan (v0.2.2 C-2) ----------
def assert_6_utf8_bom_plan() -> None:
    print("[6/10] execute-plan 读 UTF-8 BOM plan(BOM 兼容)... ", end="")
    fixture = REPO / "corpus" / ".fixtures" / "E8_scope_routing"
    sample_file = next((fixture / "01-projects").rglob("*.md"), None)
    assert sample_file is not None, "E8 fixture 内未找到 .md 文件作 src_abs"
    valid_plan = {
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(sample_file),
            "target_bucket": "02-areas",
            "target_subdir": "产品方案库",
            "target_filename": "smoke_bom_test.md",
            "frontmatter": {},
            "ai_reason": "smoke_test BOM 兼容验收",
        }],
    }
    # 写一个带 UTF-8 BOM 的 plan(EF BB BF 前缀 + 普通 UTF-8 JSON)
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
        f.write(b"\xef\xbb\xbf")
        f.write(json.dumps(valid_plan, ensure_ascii=False).encode("utf-8"))
        plan_file = f.name
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
        # BOM 不应导致 JSONDecodeError(v0.2.2 C-2 修后应正常 parse)
        assert "JSONDecodeError" not in proc.stderr and "Expecting value" not in proc.stderr, \
            f"BOM plan 触发 JSONDecodeError(C-2 修复未生效)\nstderr:\n{proc.stderr[:600]}"
        assert proc.returncode == 0, \
            f"BOM plan dry-run 应 exit 0(行为不变化,只是 BOM 兼容)\n" \
            f"exit={proc.returncode}\nstdout:\n{proc.stdout[:600]}\nstderr:\n{proc.stderr[:400]}"
    finally:
        Path(plan_file).unlink(missing_ok=True)
    print("✓")


# ---------- Assert 7: execute-plan 拒绝缺 frontmatter 的 plan (v0.2.2 Codex-4th-1) ----------
def assert_7_missing_frontmatter_rejected() -> None:
    print("[7/10] execute-plan 拒绝缺 frontmatter 的 plan(schema Layer 1 key 存在)... ", end="")
    bad_plan = {
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(REPO / "README.md"),
            "target_bucket": "02-areas",
            "target_subdir": "产品方案库",
            "target_filename": "a.md",
            # 故意缺 frontmatter(其他 5 字段都补齐,验证拒因精确到 frontmatter)
            "ai_reason": "smoke_test 故意缺 frontmatter",
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(bad_plan, f, ensure_ascii=False)
        plan_file = f.name
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
        assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
            f"缺 frontmatter 应拒但未触发 ERROR_INVALID_PLAN_ITEM\n" \
            f"stdout:\n{proc.stdout[:800]}\nstderr:\n{proc.stderr[:400]}"
        assert "frontmatter" in proc.stdout, \
            f"拒绝原因应提及 frontmatter\nstdout:\n{proc.stdout[:800]}"
    finally:
        Path(plan_file).unlink(missing_ok=True)
    print("✓")


# ---------- Assert 8: execute-plan 拒绝缺 ai_reason 的 plan (v0.2.2 Codex-4th-1) ----------
def assert_8_missing_ai_reason_rejected() -> None:
    print("[8/10] execute-plan 拒绝缺 ai_reason 的 plan(schema Layer 1 key 存在)... ", end="")
    bad_plan = {
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(REPO / "README.md"),
            "target_bucket": "02-areas",
            "target_subdir": "产品方案库",
            "target_filename": "a.md",
            "frontmatter": {},
            # 故意缺 ai_reason
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(bad_plan, f, ensure_ascii=False)
        plan_file = f.name
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
        assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
            f"缺 ai_reason 应拒但未触发 ERROR_INVALID_PLAN_ITEM\n" \
            f"stdout:\n{proc.stdout[:800]}\nstderr:\n{proc.stderr[:400]}"
        assert "ai_reason" in proc.stdout, \
            f"拒绝原因应提及 ai_reason\nstdout:\n{proc.stdout[:800]}"
    finally:
        Path(plan_file).unlink(missing_ok=True)
    print("✓")


# ---------- Assert 9: execute-plan 拒绝 frontmatter 非 dict (Codex-5th Layer 2 类型校验) ----------
def assert_9_frontmatter_wrong_type_rejected() -> None:
    print("[9/10] execute-plan 拒绝 frontmatter 非 dict 的 plan(Layer 2 类型校验)... ", end="")
    type_cases = [
        ("frontmatter=None", None),
        ("frontmatter=\"str\"", "string instead of dict"),
        ("frontmatter=[]", []),
    ]
    for desc, bad_value in type_cases:
        bad_plan = {
            "src_root": "smoke_test",
            "items": [{
                "src_abs": str(REPO / "README.md"),
                "target_bucket": "02-areas",
                "target_subdir": "产品方案库",
                "target_filename": "a.md",
                "frontmatter": bad_value,
                "ai_reason": "smoke_test 类型校验",
            }],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bad_plan, f, ensure_ascii=False)
            plan_file = f.name
        try:
            proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
            assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
                f"{desc} 应拒但未触发 ERROR_INVALID_PLAN_ITEM\nstdout:\n{proc.stdout[:800]}"
            assert "must be dict" in proc.stdout, \
                f"{desc} 拒绝原因应提及 'must be dict'\nstdout:\n{proc.stdout[:800]}"
        finally:
            Path(plan_file).unlink(missing_ok=True)
    print("✓ (3 type cases)")


# ---------- Assert 10: execute-plan 拒绝空字符串字段 (Codex-5th Layer 3 非空校验) ----------
def assert_10_empty_string_field_rejected() -> None:
    print("[10/10] execute-plan 拒绝 target_subdir / ai_reason 空字符串(Layer 3 非空)... ", end="")
    empty_cases = [
        ("target_subdir=\"\"", "target_subdir", ""),
        ("target_subdir=\"   \"", "target_subdir", "   "),  # strip 后空
        ("ai_reason=\"\"", "ai_reason", ""),
    ]
    for desc, field, bad_value in empty_cases:
        item = {
            "src_abs": str(REPO / "README.md"),
            "target_bucket": "02-areas",
            "target_subdir": "产品方案库",
            "target_filename": "a.md",
            "frontmatter": {},
            "ai_reason": "smoke_test 非空校验",
        }
        item[field] = bad_value
        bad_plan = {"src_root": "smoke_test", "items": [item]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(bad_plan, f, ensure_ascii=False)
            plan_file = f.name
        try:
            proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
            assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
                f"{desc} 应拒但未触发 ERROR_INVALID_PLAN_ITEM\nstdout:\n{proc.stdout[:800]}"
            assert "empty string" in proc.stdout, \
                f"{desc} 拒绝原因应提及 'empty string'\nstdout:\n{proc.stdout[:800]}"
            assert field in proc.stdout, \
                f"{desc} 拒绝原因应提及字段名 '{field}'\nstdout:\n{proc.stdout[:800]}"
        finally:
            Path(plan_file).unlink(missing_ok=True)
    print("✓ (3 empty-string cases)")


def main() -> int:
    print(f"# smoke_test.py — v0.2.2 minimal smoke test 10/10 (Python: {PY})")
    print()
    failures: list[tuple[str, str]] = []
    for name, fn in [
        ("Assert 1 (search.py --help)", assert_1_search_help),
        ("Assert 2 (ingest scan-only)", assert_2_scan_only),
        ("Assert 3 (real path boundary — Codex-5th)", assert_3_malformed_plan_rejected),
        ("Assert 4 (key deps import)", assert_4_imports),
        ("Assert 5 (missing target_subdir — Layer 1)", assert_5_missing_subdir_rejected),
        ("Assert 6 (UTF-8 BOM plan compat)", assert_6_utf8_bom_plan),
        ("Assert 7 (missing frontmatter — Layer 1)", assert_7_missing_frontmatter_rejected),
        ("Assert 8 (missing ai_reason — Layer 1)", assert_8_missing_ai_reason_rejected),
        ("Assert 9 (frontmatter wrong type — Layer 2)", assert_9_frontmatter_wrong_type_rejected),
        ("Assert 10 (empty string field — Layer 3)", assert_10_empty_string_field_rejected),
    ]:
        try:
            fn()
        except Exception as e:
            print(f"✗ FAIL")
            failures.append((name, str(e)))
    print()
    if not failures:
        print("# ✅ smoke_test 10/10 PASS")
        return 0
    print(f"# ❌ smoke_test {len(failures)} FAIL:")
    for name, err in failures:
        print(f"  - {name}: {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
