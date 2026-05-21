"""smoke_test.py — v0.2.1 最小自动化 smoke test(单文件 4 assert)

GPT 外审 P1-9 / Codex 提及"无 pytest CI";本版**只做 4 个核心 assert**,
不引入 pytest 重型测试栈。验证主链路:install 调用参数有效 / scan-only 走通 /
路径边界拒绝 malformed / 关键依赖 import 都 OK。

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
    print("[1/4] search.py --scope all --help (install 烟测调用参数)... ", end="")
    proc = _run([PY, str(REPO / "scripts" / "search.py"), "--scope", "all", "--help"])
    # --help 在 argparse 下 returncode=0 + stdout 含 usage
    assert proc.returncode == 0, f"search.py --help exit={proc.returncode}\nstderr:\n{proc.stderr}"
    assert "usage:" in proc.stdout, f"search.py --help 输出无 'usage:'\nstdout:\n{proc.stdout[:500]}"
    print("✓")


# ---------- Assert 2: scan-only 走通 + routing_request.json 生成 ----------
def assert_2_scan_only() -> None:
    print("[2/4] ingest.py scan-only corpus/.fixtures/E8_scope_routing/... ", end="")
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


# ---------- Assert 3: execute-plan 拒绝 3 个 malformed plan ----------
def assert_3_malformed_plan_rejected() -> None:
    print("[3/4] execute-plan 拒绝 3 个 malformed plan(P0-2 路径边界)... ", end="")
    malformed_cases = [
        {
            "desc": "filename ../",
            "items": [{
                "src_abs": str(REPO / "README.md"),
                "target_bucket": "01-projects",
                "target_project": "X",
                "target_subdir": "01-方案",
                "target_filename": "../../etc/passwd",
            }],
        },
        {
            "desc": "bucket 非白名单",
            "items": [{
                "src_abs": str(REPO / "README.md"),
                "target_bucket": "evil-bucket",
                "target_filename": "a.md",
            }],
        },
        {
            "desc": "绝对路径前缀",
            "items": [{
                "src_abs": str(REPO / "README.md"),
                "target_bucket": "01-projects",
                "target_project": "C:/Windows",
                "target_subdir": "01-方案",
                "target_filename": "a.md",
            }],
        },
    ]
    for case in malformed_cases:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"src_root": "smoke_test", "items": case["items"]}, f, ensure_ascii=False)
            plan_file = f.name
        try:
            proc = _run([PY, str(REPO / "scripts" / "ingest.py"), "execute-plan", plan_file, "--dry-run"])
            # 校验失败应在 stdout 显示 ERROR_INVALID_PLAN_ITEM(单 item 失败不退出非 0,
            # 但 stats 中该 action 必须出现)
            assert "ERROR_INVALID_PLAN_ITEM" in proc.stdout, \
                f"case '{case['desc']}' 应拒绝但未触发 ERROR_INVALID_PLAN_ITEM\n" \
                f"stdout:\n{proc.stdout[:800]}\nstderr:\n{proc.stderr[:400]}"
        finally:
            Path(plan_file).unlink(missing_ok=True)
    print("✓ (3 cases)")


# ---------- Assert 4: 关键依赖 import(docx + yaml + markitdown)----------
def assert_4_imports() -> None:
    print("[4/4] import docx + yaml + markitdown... ", end="")
    proc = _run([PY, "-c", "import docx; import yaml; import markitdown"])
    assert proc.returncode == 0, \
        f"关键依赖 import 失败 exit={proc.returncode}\nstderr:\n{proc.stderr}"
    print("✓")


def main() -> int:
    print(f"# smoke_test.py — v0.2.1 minimal smoke test (Python: {PY})")
    print()
    failures: list[tuple[str, str]] = []
    for name, fn in [
        ("Assert 1 (search.py --help)", assert_1_search_help),
        ("Assert 2 (ingest scan-only)", assert_2_scan_only),
        ("Assert 3 (malformed plan rejection)", assert_3_malformed_plan_rejected),
        ("Assert 4 (key deps import)", assert_4_imports),
    ]:
        try:
            fn()
        except Exception as e:
            print(f"✗ FAIL")
            failures.append((name, str(e)))
    print()
    if not failures:
        print("# ✅ smoke_test 4/4 PASS")
        return 0
    print(f"# ❌ smoke_test {len(failures)} FAIL:")
    for name, err in failures:
        print(f"  - {name}: {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
