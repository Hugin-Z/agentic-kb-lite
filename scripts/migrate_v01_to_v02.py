"""migrate_v01_to_v02.py — v0.1 → v0.2 corpus 一次性迁移脚本

按 docs/v0.2-plan.md §4.3 步骤 1.3 设计:
  - 两阶段执行:dry-run(默认) → commit(--commit flag + 交互确认)
  - 可重入:dst 已存在跳过
  - 安全:先 copy2 再 verify size 再 unlink 原文件(避免中断丢数据)
  - 全程日志:logs/migration_v02_<timestamp>.{jsonl,md}
  - 排除 .fixtures/(评估 fixtures 不参与迁移)
  - 排除 is_temp_or_hidden(对齐 ingest.py 行为)

用法:
  python scripts/migrate_v01_to_v02.py                # dry-run(默认)
  python scripts/migrate_v01_to_v02.py --commit       # 实际迁移,交互确认
  python scripts/migrate_v01_to_v02.py --corpus path  # 指定 corpus 根
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
LOGS_DIR = REPO / "logs"

V01_TO_V02_BUCKET_MAP = {
    "01-历史方案": "01-projects",
    "02-投标章节": "02-areas/投标章节模板",
    "03-技术决策": "02-areas/技术方法论",
    "04-个人记忆": "03-resources/培训与调研",
}


def is_temp_or_hidden(name: str, src_path: Path | None = None) -> tuple[bool, str | None]:
    """对齐 ingest.py 的临时/隐藏判定。"""
    if name.startswith("~$"):
        return True, "Office 锁文件"
    if name in ("Thumbs.db", "desktop.ini"):
        return True, "Windows 系统文件"
    if name.endswith((".tmp", ".lock", ".bak")):
        return True, "临时文件"
    if src_path is not None and any(p.endswith(".assets") for p in src_path.parts):
        return True, "派生 vision 嵌入图(.assets/)"
    if src_path is not None and any(p.endswith(".frames") for p in src_path.parts):
        return True, "派生视频抽帧(.frames/)"
    if name.startswith(".") and not (name.endswith(".stub.md") or name == ".references.md"):
        return True, "隐藏文件(非本仓库 stub)"
    return False, None


def discover_files(corpus_root: Path) -> list[dict]:
    """扫描 v0.1 corpus 所有文件,生成迁移计划(.fixtures/ 排除)。"""
    plans: list[dict] = []
    for old_bucket, new_bucket in V01_TO_V02_BUCKET_MAP.items():
        old_dir = corpus_root / old_bucket
        if not old_dir.exists():
            continue
        for f in sorted(old_dir.rglob("*")):
            if not f.is_file():
                continue
            skip, skip_reason = is_temp_or_hidden(f.name, f)
            if skip:
                plans.append({
                    "src": str(f),
                    "dst": None,
                    "action": "skip",
                    "reason": skip_reason,
                    "old_bucket": old_bucket,
                })
                continue
            relative = f.relative_to(old_dir)
            new_path = corpus_root / new_bucket / relative
            plans.append({
                "src": str(f),
                "dst": str(new_path),
                "action": "move",
                "reason": f"v01_to_v02_bucket_map[{old_bucket}]",
                "old_bucket": old_bucket,
                "size_bytes": f.stat().st_size,
            })
    return plans


def write_dry_run_report(plans: list[dict], logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = logs_dir / f"migration_v02_dryrun_{ts}.md"
    jsonl_path = logs_dir / f"migration_v02_dryrun_{ts}.jsonl"

    moves = [p for p in plans if p["action"] == "move"]
    skips = [p for p in plans if p["action"] == "skip"]

    by_bucket: dict[str, list[dict]] = {}
    for p in moves:
        by_bucket.setdefault(p["old_bucket"], []).append(p)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# v0.1 → v0.2 迁移 dry-run 报告\n\n")
        f.write(f"- 生成时间:{ts}\n")
        f.write(f"- 计划迁移文件数:{len(moves)}\n")
        f.write(f"- 跳过(临时/隐藏)文件数:{len(skips)}\n\n")
        if not moves:
            f.write("**v0.1 四个 bucket 全空,无文件需要迁移。**\n\n")
            f.write("解释:本仓库 v0.1.0 即首发版,corpus/ 下四个 bucket 是空骨架(README 占位),")
            f.write("真实素材入库由用户在本机进行;首发版未入任何素材即直接进入 v0.2 升级。\n\n")
        for old_bucket, items in by_bucket.items():
            new_bucket = V01_TO_V02_BUCKET_MAP[old_bucket]
            f.write(f"## {old_bucket} → {new_bucket}({len(items)} 文件)\n\n")
            for p in items:
                src = Path(p["src"]).relative_to(REPO)
                dst = Path(p["dst"]).relative_to(REPO)
                f.write(f"- `{src}` → `{dst}`\n")
            f.write("\n")
        if skips:
            f.write(f"## 跳过项({len(skips)})\n\n")
            for p in skips:
                src = Path(p["src"]).relative_to(REPO)
                f.write(f"- `{src}`:{p['reason']}\n")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for p in plans:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    return md_path


def execute_commit(plans: list[dict], logs_dir: Path) -> dict:
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"migration_v02_commit_{ts}.jsonl"

    stats = {"success": 0, "skip_dst_exists": 0, "skip_temp": 0, "fail": 0}
    moves = [p for p in plans if p["action"] == "move"]

    with open(log_path, "w", encoding="utf-8") as logf:
        for plan in plans:
            if plan["action"] == "skip":
                stats["skip_temp"] += 1
                logf.write(json.dumps({**plan, "result": "skip_temp", "ts": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
                continue
            src = Path(plan["src"])
            dst = Path(plan["dst"])
            if dst.exists():
                stats["skip_dst_exists"] += 1
                logf.write(json.dumps({**plan, "result": "skip_dst_exists", "ts": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                if dst.exists() and dst.stat().st_size == src.stat().st_size:
                    src.unlink()
                    stats["success"] += 1
                    logf.write(json.dumps({**plan, "result": "success", "ts": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
                else:
                    stats["fail"] += 1
                    logf.write(json.dumps({**plan, "result": "fail_size_mismatch", "ts": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
            except Exception as e:
                stats["fail"] += 1
                logf.write(json.dumps({**plan, "result": "fail_exception", "error": str(e), "ts": datetime.now().isoformat()}, ensure_ascii=False) + "\n")

    return {**stats, "total_planned": len(moves), "log_file": str(log_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1 → v0.2 corpus 迁移")
    parser.add_argument("--commit", action="store_true", help="实际执行(默认 dry-run)")
    parser.add_argument("--corpus", default=str(REPO / "corpus"))
    parser.add_argument("--yes", action="store_true", help="commit 时跳过交互确认(慎用)")
    args = parser.parse_args()

    corpus_root = Path(args.corpus).resolve()
    if not corpus_root.is_dir():
        sys.stderr.write(f"ERROR: corpus 根目录不存在 {corpus_root}\n")
        return 2

    plans = discover_files(corpus_root)
    moves = [p for p in plans if p["action"] == "move"]
    skips = [p for p in plans if p["action"] == "skip"]

    if not args.commit:
        report = write_dry_run_report(plans, LOGS_DIR)
        print(f"[DRY-RUN] 计划迁移 {len(moves)} 文件,跳过 {len(skips)} 临时/隐藏文件。")
        print(f"[DRY-RUN] 报告:{report.relative_to(REPO)}")
        if not moves:
            print("[DRY-RUN] v0.1 四个 bucket 全空,无文件需迁移(本仓库首发版即空骨架)。")
        print(f"[DRY-RUN] 确认后用 --commit 实际执行。")
        return 0

    print(f"[COMMIT] 即将迁移 {len(moves)} 文件(跳过 {len(skips)} 临时项)。")
    if not args.yes:
        ans = input("继续? [y/N]: ").strip().lower()
        if ans != "y":
            print("[COMMIT] 已取消。")
            return 1

    result = execute_commit(plans, LOGS_DIR)
    print(f"[COMMIT] success={result['success']} / skip_dst_exists={result['skip_dst_exists']} / "
          f"skip_temp={result['skip_temp']} / fail={result['fail']} / total_planned={result['total_planned']}")
    print(f"[COMMIT] 日志:{Path(result['log_file']).relative_to(REPO)}")
    if result["fail"] > 0:
        return 3
    if result["success"] != result["total_planned"]:
        sys.stderr.write(f"WARN: success({result['success']}) != total_planned({result['total_planned']})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
