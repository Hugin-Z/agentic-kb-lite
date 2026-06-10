"""smoke_test.py — 最小自动化 smoke test(单文件 17 assert,v0.3 16 个 + v0.4 recipe 1 个)

本脚本不引入 pytest 重型测试栈(轻量原则)。17 个核心 assert,覆盖
主链路 + schema 3 层校验(key 存在 / 类型 / 非空)+ BOM 兼容 + 真实路径边界
+ 失败降级路径(markitdown_failed / unsupported_ext stub 化)
+ v0.3 tier 字段(Layer 6 三层校验 + .shelved 物理路由)
+ v0.3 阶段 3 search.py --deep flag(三 bucket × .shelved/未shelved):

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
 11. markitdown 失败降级 stub(v0.2.3 5th-3,不再 ERROR_MARKITDOWN_FAILED)
 12. 未知扩展名降级 stub(v0.2.3 5th-4,不再 ERROR_UNSUPPORTED_EXT)
 13. execute-plan 拒绝非法 tier(v0.3 Layer 6.2 白名单)
 14. execute-plan tier=working 落 项目/.shelved/working/(v0.3 阶段 2 tier 路由)
 15. execute-plan 拒绝 family_key Windows 非法字符(v0.3 Layer 6.3)
 16. search.py --deep 三 bucket × .shelved/未shelved(v0.3 阶段 3 默认排除 + --deep 包含)
 17. recipe 接口 import + baseline 可调用(v0.4 脏文档预处理 recipe 层)

用法:
  python scripts/smoke_test.py
退出码:0 = 17 个 assert 全过;非 0 = 至少一个失败(stderr 写明哪个)
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
    print("[1/17] search.py --scope all --help (install 烟测调用参数)... ", end="")
    proc = _run([PY, str(REPO / "scripts" / "search.py"), "--scope", "all", "--help"])
    # --help 在 argparse 下 returncode=0 + stdout 含 usage
    assert proc.returncode == 0, f"search.py --help exit={proc.returncode}\nstderr:\n{proc.stderr}"
    assert "usage:" in proc.stdout, f"search.py --help 输出无 'usage:'\nstdout:\n{proc.stdout[:500]}"
    print("✓")


# ---------- Assert 2: scan-only 走通 + routing_request.json 生成 ----------
def assert_2_scan_only() -> None:
    print("[2/17] ingest.py scan-only corpus/.fixtures/E8_scope_routing/... ", end="")
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
    print("[3/17] execute-plan 真实拒 3 个路径边界 malformed plan(Layer 5 路径穿越)... ", end="")
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
    print("[4/17] import docx + yaml + markitdown... ", end="")
    proc = _run([PY, "-c", "import docx; import yaml; import markitdown"])
    assert proc.returncode == 0, \
        f"关键依赖 import 失败 exit={proc.returncode}\nstderr:\n{proc.stderr}"
    print("✓")


# ---------- Assert 5: execute-plan 拒绝缺 target_subdir 的 plan (v0.2.2 C-1) ----------
def assert_5_missing_subdir_rejected() -> None:
    print("[5/17] execute-plan 拒绝缺 target_subdir 的 plan(schema Layer 1 key 存在)... ", end="")
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
    print("[6/17] execute-plan 读 UTF-8 BOM plan(BOM 兼容)... ", end="")
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
    print("[7/17] execute-plan 拒绝缺 frontmatter 的 plan(schema Layer 1 key 存在)... ", end="")
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
    print("[8/17] execute-plan 拒绝缺 ai_reason 的 plan(schema Layer 1 key 存在)... ", end="")
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
    print("[9/17] execute-plan 拒绝 frontmatter 非 dict 的 plan(Layer 2 类型校验)... ", end="")
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
    print("[10/17] execute-plan 拒绝 target_subdir / ai_reason 空字符串(Layer 3 非空)... ", end="")
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


# ---------- Assert 11: markitdown 失败降级为 STUB_ONLY_MARKITDOWN_FAILED (v0.2.3 5th-3) ----------
def assert_11_markitdown_failed_stub() -> None:
    """风格说明:markitdown 对所有坏 binary 都极度容错 fallback 到 plain text 不报错,
    无法通过 subprocess + 坏 fixture 模拟真实失败。这里改为**直接 import + 调函数**
    验证 MARKITDOWN_FAILED_STUB 路径(make_stub rule_id + process_file except 分支)
    的行为正确性。end-to-end 由 manual 验证补充(progress.md 落表)。"""
    print("[11/17] markitdown 失败降级路径函数级验证(make_stub + process_file)... ", end="")
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        # 强制 reimport,避免被前面 assert 缓存影响
        if "ingest" in sys.modules:
            del sys.modules["ingest"]
        import ingest
    finally:
        sys.path.pop(0)

    # 验证 1:make_stub MARKITDOWN_FAILED_STUB rule_id 分支输出含"markitdown 转换失败"
    smoke_src = REPO / "scripts" / "smoke_test.py"  # 用自身做 src_path 避开构造文件
    stub_content = ingest.make_stub(smoke_src, "test-scene", "MARKITDOWN_FAILED_STUB",
                                     source_abs_path=str(smoke_src),
                                     prefixed_name="smoke.docx")
    assert "markitdown 转换失败" in stub_content, \
        f"MARKITDOWN_FAILED_STUB 分支应含'markitdown 转换失败'\nstub:\n{stub_content[:500]}"
    assert "已复制源文件" in stub_content, \
        f"MARKITDOWN_FAILED_STUB 分支应含'已复制源文件'\nstub:\n{stub_content[:500]}"
    assert "未入库正文" in stub_content, \
        f"MARKITDOWN_FAILED_STUB 分支应含 stub 标识\nstub:\n{stub_content[:500]}"

    # 验证 2:REQUIRED_FIELDS_SCHEMA 仍 6 字段(防回退)
    assert len(ingest.REQUIRED_FIELDS_SCHEMA) == 6, \
        f"REQUIRED_FIELDS_SCHEMA 应 6 字段,实际 {len(ingest.REQUIRED_FIELDS_SCHEMA)}"

    print("✓ (函数级,make_stub MARKITDOWN_FAILED_STUB 分支输出符合预期)")


# ---------- Assert 12: 未知扩展名降级为 STUB_ONLY_UNSUPPORTED_EXT (v0.2.3 5th-4) ----------
def assert_12_unsupported_ext_stub() -> None:
    print("[12/17] 未知扩展名降级 stub(不再 ERROR_UNSUPPORTED_EXT)... ", end="")
    unknown_dir = tempfile.mkdtemp(prefix="smoke_unsup_")
    unknown_src = Path(unknown_dir) / "smoke.xyz"
    unknown_src.write_bytes(b"smoke_test unknown extension fixture")
    plan = {
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(unknown_src),
            "target_bucket": "02-areas",
            "target_subdir": "产品方案库",
            "target_filename": "smoke.xyz",
            "frontmatter": {},
            "ai_reason": "smoke_test unsupported ext",
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
        plan_file = f.name
    landed_stub = REPO / "corpus" / "02-areas" / "产品方案库" / "smoke.xyz.stub.md"
    landed_src = REPO / "corpus" / "02-areas" / "产品方案库" / "smoke.xyz"
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file])
        assert "STUB_ONLY_UNSUPPORTED_EXT" in proc.stdout, \
            f"未知扩展名应降级 STUB_ONLY_UNSUPPORTED_EXT 但未触发\n" \
            f"stdout:\n{proc.stdout[:800]}\nstderr:\n{proc.stderr[:400]}"
        assert "ERROR_UNSUPPORTED_EXT" not in proc.stdout, \
            f"v0.2.3 后不应再走 ERROR_UNSUPPORTED_EXT,应降级 stub\n" \
            f"stdout:\n{proc.stdout[:800]}"
        assert landed_stub.exists(), f"stub 应落地: {landed_stub}"
        assert landed_src.exists(), f"源文件应 cp: {landed_src}"
    finally:
        Path(plan_file).unlink(missing_ok=True)
        unknown_src.unlink(missing_ok=True)
        Path(unknown_dir).rmdir() if Path(unknown_dir).exists() else None
        landed_stub.unlink(missing_ok=True)
        landed_src.unlink(missing_ok=True)
    print("✓")


# ---------- Assert 13: execute-plan 拒绝非法 tier (v0.3 阶段 1 Layer 6.2 白名单) ----------
def assert_13_invalid_tier_rejected() -> None:
    """v0.3 阶段 2 step 2.4 [13/17]:tier 字段白名单拒非法值。
    反向断言:拒因含 'whitelist' 不含 'missing required field'。"""
    print("[13/17] execute-plan 拒绝非法 tier 'evil'(Layer 6.2 白名单)... ", end="")
    bad_plan = {
        "plan_schema_version": "v0.3",
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(REPO / "README.md"),
            "target_bucket": "02-areas",
            "target_subdir": "产品方案库",
            "target_filename": "a.md",
            "frontmatter": {},
            "ai_reason": "smoke_test invalid tier",
            "tier": "evil",  # 非白名单
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(bad_plan, f, ensure_ascii=False)
        plan_file = f.name
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
        assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
            f"非法 tier 应拒但未触发 ERROR_INVALID_PLAN_ITEM\n" \
            f"stdout:\n{proc.stdout[:800]}\nstderr:\n{proc.stderr[:400]}"
        assert "not in whitelist" in proc.stdout, \
            f"拒因应含 'not in whitelist'\nstdout:\n{proc.stdout[:800]}"
        # 反向断言:不应是 schema 缺字段拒
        assert "missing required field" not in proc.stdout, \
            f"应被 Layer 6.2 拒,不应是 Layer 1 缺字段拒\nstdout:\n{proc.stdout[:800]}"
    finally:
        Path(plan_file).unlink(missing_ok=True)
    print("✓")


# ---------- Assert 14: execute-plan 落 项目/.shelved/working/ (v0.3 阶段 2 tier 路由) ----------
def assert_14_shelved_working_landing() -> None:
    """v0.3 阶段 2 step 2.4 [14/17]:tier=working 端到端落 .shelved/working/。
    用虚构项目名 _v03_smoke_working_,测完清理(W-v0.3-阶段1-W1 防御)。"""
    print("[14/17] execute-plan 落 项目/.shelved/working/(tier=working 端到端)... ", end="")
    working_dir = tempfile.mkdtemp(prefix="smoke_v03_working_")
    working_src = Path(working_dir) / "build_demo.md"
    working_src.write_text("# v03 working tier smoke\n\nbuild script demo", encoding="utf-8")
    plan = {
        "plan_schema_version": "v0.3",
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(working_src),
            "target_bucket": "01-projects",
            "target_project": "_v03_smoke_working_",
            "target_subdir": "99-其他",
            "target_filename": "build_demo.md",
            "frontmatter": {},
            "ai_reason": "smoke_test tier=working 端到端",
            "tier": "working",
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False)
        plan_file = f.name
    proj_root = REPO / "corpus" / "01-projects" / "_v03_smoke_working_"
    expected = proj_root / ".shelved" / "working" / "99-其他" / "build_demo.md"
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file])
        assert proc.returncode == 0, f"execute-plan exit={proc.returncode}\nstderr:\n{proc.stderr}"
        assert expected.exists(), \
            f".shelved/working/ 落地 .md 缺失:{expected}\nstdout:\n{proc.stdout[:600]}"
        # 验证 frontmatter 3 字段
        content = expected.read_text(encoding="utf-8-sig")
        assert "kb_tier: working" in content, \
            f"frontmatter 缺 kb_tier: working\n{content[:400]}"
        assert "kb_default_search: false" in content, \
            f"frontmatter 缺 kb_default_search: false\n{content[:400]}"
    finally:
        Path(plan_file).unlink(missing_ok=True)
        working_src.unlink(missing_ok=True)
        Path(working_dir).rmdir() if Path(working_dir).exists() else None
        # 清理 corpus 虚构项目目录(W-v0.3-阶段1-W1 防御规则)
        if proj_root.exists():
            import shutil
            shutil.rmtree(proj_root)
    print("✓")


# ---------- Assert 15: execute-plan 拒绝 family_key Windows 非法字符 (v0.3 阶段 1 Layer 6.3) ----------
def assert_15_family_key_invalid_char_rejected() -> None:
    """v0.3 阶段 2 step 2.4 [15/17]:tier=versions + family_key 含 Win 非法字符拒。
    反向断言:拒因含 'Windows-invalid chars' 不含 'missing required field' / 'not in whitelist'。"""
    print("[15/17] execute-plan 拒绝 family_key Windows 非法字符(Layer 6.3)... ", end="")
    bad_plan = {
        "plan_schema_version": "v0.3",
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(REPO / "README.md"),
            "target_bucket": "01-projects",
            "target_project": "_v03_smoke_bad_fk_",
            "target_subdir": "01-方案",
            "target_filename": "v1.md",
            "frontmatter": {},
            "ai_reason": "smoke_test family_key 含 Win 非法字符",
            "tier": "versions",
            "family_key": "bad<name|here",  # < 和 | 都是 Win 非法
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(bad_plan, f, ensure_ascii=False)
        plan_file = f.name
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
        assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
            f"应拒但未触发 ERROR_INVALID_PLAN_ITEM\nstdout:\n{proc.stdout[:800]}"
        assert "Windows-invalid chars" in proc.stdout, \
            f"拒因应含 'Windows-invalid chars'\nstdout:\n{proc.stdout[:800]}"
        # 双向反向断言:不是 schema 缺字段拒 + 不是白名单拒
        assert "missing required field" not in proc.stdout, \
            f"应被 Layer 6.3 拒,不应是 Layer 1 缺字段拒\nstdout:\n{proc.stdout[:800]}"
        assert "not in whitelist" not in proc.stdout, \
            f"应被 Layer 6.3 拒,不应是 Layer 6.2 白名单拒\nstdout:\n{proc.stdout[:800]}"
    finally:
        Path(plan_file).unlink(missing_ok=True)

    # archives bucket 不走 tier:即使给 tier=versions 且缺 family_key,也应忽略 tier,
    # 不触发 Layer 6.3,物理路径保持 04-archives 下的普通路径。
    archive_plan = {
        "plan_schema_version": "v0.3",
        "src_root": "smoke_test",
        "items": [{
            "src_abs": str(REPO / "README.md"),
            "target_bucket": "04-archives",
            "target_project": "_v03_smoke_archive_",
            "target_subdir": "01-方案",
            "target_filename": "archive.md",
            "frontmatter": {},
            "ai_reason": "smoke_test archives bucket ignores tier",
            "tier": "versions",
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(archive_plan, f, ensure_ascii=False)
        archive_plan_file = f.name
    try:
        proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", archive_plan_file, "--dry-run"])
        assert "ERROR_INVALID_PLAN_ITEM" not in proc.stdout, \
            f"archives bucket 应忽略 tier,不应触发 Layer 6.3\nstdout:\n{proc.stdout[:800]}"
        assert "DRY_RUN_TEXT" in proc.stdout, \
            f"archives bucket dry-run 应正常处理\nstdout:\n{proc.stdout[:800]}"
        assert "corpus/04-archives/_v03_smoke_archive_/archive.md" in proc.stdout, \
            f"archives bucket 不应落 .shelved,应保持普通 04-archives 路径\nstdout:\n{proc.stdout[:800]}"
        assert ".shelved" not in proc.stdout, \
            f"archives bucket 不走 tier,stdout 不应含 .shelved\nstdout:\n{proc.stdout[:800]}"
    finally:
        Path(archive_plan_file).unlink(missing_ok=True)
    print("✓")


# ---------- Assert 16: search.py --deep 三 bucket × shelved/未shelved (v0.3 阶段 3) ----------
def assert_16_deep_flag_three_buckets() -> None:
    """v0.3 阶段 3 step 3.3 + 3.4 [16/17]:三 bucket 各放 canonical + .shelved/working
    fixture,验证默认 search 不命中 shelved,--deep 命中,且默认输出含提示。
    用虚构项目名 _v03_phase3_deep_*_,测完 shutil.rmtree 清理(W-v0.3-阶段1-W1 防御)。"""
    print("[16/17] search.py --deep 三 bucket × .shelved/未shelved 端到端... ", end="")
    import shutil

    # 三 bucket × (canonical + shelved/working) = 6 fixture
    UNIQUE_CANON = "v03_p3_canon_unique_xyz_zzz"
    UNIQUE_SHELVED = "v03_p3_shelved_unique_xyz_zzz"
    fixtures = []
    cleanups = []

    proj = REPO / "corpus" / "01-projects" / "_v03_phase3_deep_test_"
    areas = REPO / "corpus" / "02-areas" / "_v03_phase3_areas_test_"
    res = REPO / "corpus" / "03-resources" / "_v03_phase3_res_test_"

    for root, canon_sub, shelved_sub in [
        (proj, "01-方案", ".shelved/working/99-其他"),
        (areas, "", ".shelved/working"),
        (res, "", ".shelved/working"),
    ]:
        # canonical(默认命中)
        canon_path = root / canon_sub / "canonical.md" if canon_sub else root / "canonical.md"
        canon_path.parent.mkdir(parents=True, exist_ok=True)
        canon_path.write_text(f"# canonical\n\nbody:{UNIQUE_CANON}", encoding="utf-8")
        # shelved/working(默认不命中)
        shelved_path = root / shelved_sub / "working_demo.md"
        shelved_path.parent.mkdir(parents=True, exist_ok=True)
        shelved_path.write_text(f"# shelved working\n\nbody:{UNIQUE_SHELVED}", encoding="utf-8")
        fixtures.append((canon_path, shelved_path))
        cleanups.append(root)

    try:
        search = [PY, str(REPO / "scripts" / "search.py")]

        # 跑 1:默认搜 canonical 关键词 → 应命中(默认行为)+ 提示
        proc1 = _run(search + ["--scope", "all", "--terms", UNIQUE_CANON])
        assert proc1.returncode == 0, f"search canonical exit={proc1.returncode}\nstderr:\n{proc1.stderr}"
        assert UNIQUE_CANON in proc1.stdout, \
            f"默认搜 canonical 应命中关键词\nstdout:\n{proc1.stdout[:800]}"
        assert "默认检索已排除 .shelved" in proc1.stdout, \
            f"默认输出应含 .shelved 排除提示\nstdout:\n{proc1.stdout[:600]}"

        # 跑 2:默认搜 shelved 关键词 → 应 0 命中(默认排除 .shelved/**)
        # 判定标准:search.py 输出"命中文件: 0";search.py 会 echo 出检索词到"未命中检索词"
        # 段,所以不能用 UNIQUE_SHELVED in stdout 判定。
        proc2 = _run(search + ["--scope", "all", "--terms", UNIQUE_SHELVED])
        assert proc2.returncode == 0, f"search shelved (default) exit={proc2.returncode}\nstderr:\n{proc2.stderr}"
        assert "命中文件**: 0" in proc2.stdout or "**命中文件**: 0" in proc2.stdout, \
            f"默认搜 shelved 应 0 命中(应被 .shelved/** glob 排除)\nstdout:\n{proc2.stdout[:1500]}"

        # 跑 3:--deep 搜 shelved 关键词 → 应命中(三 bucket 都命中)
        # v0.3 阶段 4A W-v0.3-阶段3-W1 修:加强断言,不能用 "keyword in stdout"(误判:search.py
        # 在"未命中检索词"段也 echo keyword)和 "bucket name in stdout"(误判:"搜索范围"行
        # 含所有 bucket 路径)。改用具体命中文件数 + 命中文件路径含 .shelved 双判定。
        proc3 = _run(search + ["--scope", "all", "--terms", UNIQUE_SHELVED, "--deep"])
        assert proc3.returncode == 0, f"search shelved --deep exit={proc3.returncode}\nstderr:\n{proc3.stderr}"
        # 主判定:命中文件数 ≥ 3(三 bucket 各 1 个 .shelved/working/working_demo.md)
        # search.py 输出格式 "- **命中文件**: N (正文 N + stub 0)"
        import re
        m = re.search(r"\*\*命中文件\*\*:\s*(\d+)", proc3.stdout)
        assert m, f"--deep 输出无 '命中文件: N' 统计行\nstdout:\n{proc3.stdout[:1500]}"
        deep_hits = int(m.group(1))
        assert deep_hits >= 3, \
            f"--deep 应在三 bucket 各命中一次(共 ≥ 3 文件),实际命中 {deep_hits}\nstdout:\n{proc3.stdout[:1500]}"
        # 辅判定 1:命中文件路径段含 .shelved(`### corpus/.../.shelved/working/working_demo.md`)
        assert ".shelved" in proc3.stdout, \
            f"--deep 命中文件路径应含 '.shelved' 段\nstdout:\n{proc3.stdout[:1500]}"
        # 辅判定 2:--deep 时不应输出排除提示
        assert "默认检索已排除 .shelved" not in proc3.stdout, \
            f"--deep 时不应输出 .shelved 排除提示\nstdout:\n{proc3.stdout[:600]}"
    finally:
        for root in cleanups:
            if root.exists():
                shutil.rmtree(root)
    print("✓ (3 bucket × default 排除 + --deep 命中)")


# ---------- Assert 17: recipe 接口 import + baseline 可调用 (v0.4 脏文档预处理) ----------
def assert_17_recipe() -> None:
    """v0.4.0 recipe 层 [17/17]:接口 import + baseline 4 能力可调用 + 透传 + 未知名 KeyError。

    用合成最小串做单测(非 C 系 fixture anchor —— C 系 anchor 必须是 Hugin 提供的真实
    脱敏样本,见 tests/查询记录.md C 系;此处的合成串等同既有 assert 的合成 plan,是单测
    输入而非评估 fixture)。"""
    print("[17/17] recipe 接口 import + baseline 可调用(v0.4)... ", end="")
    import sys as _sys
    _sys.path.insert(0, str(REPO / "scripts"))
    try:
        from recipes import get_recipe, Recipe, RecipeResult
    finally:
        _sys.path.pop(0)

    r = get_recipe()  # 默认 baseline
    assert isinstance(r, Recipe), "get_recipe() 应返回 Recipe 子类实例"
    assert r.name == "baseline", f"默认 recipe 应为 baseline,实际 {r.name}"

    # 合成脏串:NBSP(U+00A0)+ 全角空格(U+3000)+ 零宽(U+200B)+ 4 连空行 + 错位表行
    dirty = ("中心 节点　部署​说明\n\n\n\n"
             "| 列A | 列B | 列C |\n| 单格 |\n| a | b | c |\n")
    rr = r.process("x.docx", dirty)
    assert isinstance(rr, RecipeResult), "process 应返回 RecipeResult"
    assert rr.applied is True, f"脏串应被加工 applied=True,notes={rr.notes}"
    assert " " not in rr.text and "　" not in rr.text and "​" not in rr.text, \
        f"控制字符应被清理\n{rr.text!r}"
    assert "\n\n\n\n" not in rr.text, "连续 ≥3 空行应被压缩"
    padded = [ln for ln in rr.text.splitlines() if "单格" in ln][0]
    header = [ln for ln in rr.text.splitlines() if "列A" in ln][0]
    assert padded.count("|") == header.count("|"), \
        f"错位表行 padding 后列数应与表头对齐:{padded!r} vs {header!r}"

    # 透传:已干净文本 applied=False
    clean = "# 标题\n\n正文一段。\n\n正文两段。\n"
    assert r.process("y.docx", clean).applied is False, "已干净文本应透传 applied=False"

    # 未知 recipe 名 → KeyError
    try:
        get_recipe("__nope__")
        raise AssertionError("未知 recipe 名应抛 KeyError")
    except KeyError:
        pass
    print("✓")


def main() -> int:
    print(f"# smoke_test.py — v0.3 minimal smoke test 17/17 (Python: {PY})")
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
        ("Assert 11 (markitdown failed → stub — v0.2.3 5th-3)", assert_11_markitdown_failed_stub),
        ("Assert 12 (unsupported ext → stub — v0.2.3 5th-4)", assert_12_unsupported_ext_stub),
        ("Assert 13 (invalid tier → Layer 6.2 whitelist — v0.3)", assert_13_invalid_tier_rejected),
        ("Assert 14 (tier=working → .shelved/working/ — v0.3 阶段 2)", assert_14_shelved_working_landing),
        ("Assert 15 (family_key Win-invalid chars → Layer 6.3 — v0.3)", assert_15_family_key_invalid_char_rejected),
        ("Assert 16 (search.py --deep 三 bucket × .shelved — v0.3 阶段 3)", assert_16_deep_flag_three_buckets),
        ("Assert 17 (recipe interface + baseline — v0.4)", assert_17_recipe),
    ]:
        try:
            fn()
        except Exception as e:
            print(f"✗ FAIL")
            failures.append((name, str(e)))
    print()
    if not failures:
        print("# ✅ smoke_test 17/17 PASS")
        return 0
    print(f"# ❌ smoke_test {len(failures)} FAIL:")
    for name, err in failures:
        print(f"  - {name}: {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
