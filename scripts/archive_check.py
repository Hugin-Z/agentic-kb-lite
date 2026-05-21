"""archive_check.py — 扫描 01-projects 下 6 个月以上无新文件的项目作为归档候选

设计原则:
  - 只展示候选,不自动 mv(项目可能只是暂停 ≠ 已归档)
  - 输出 logs/archive_candidates_<date>.txt,Hugin 手动决定
  - 调整阈值改下方 ARCHIVE_THRESHOLD_DAYS 常量

详见 docs/v0.2-plan.md §5.3 步骤 2.5、CLAUDE.md 第 5.6.3 节
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"

ARCHIVE_THRESHOLD_DAYS = 180  # 6 个月


def scan_archive_candidates(corpus_root: Path) -> list[dict]:
    projects_dir = corpus_root / "01-projects"
    if not projects_dir.is_dir():
        return []
    candidates: list[dict] = []
    now = datetime.now()
    threshold = now - timedelta(days=ARCHIVE_THRESHOLD_DAYS)

    for proj_dir in sorted(projects_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        file_mtimes = [f.stat().st_mtime for f in proj_dir.rglob("*") if f.is_file()]
        file_count = len(file_mtimes)
        if file_count == 0:
            continue
        latest_mtime = max(file_mtimes)
        latest_dt = datetime.fromtimestamp(latest_mtime)
        if latest_dt < threshold:
            candidates.append({
                "project": proj_dir.name,
                "latest_activity": latest_dt.strftime("%Y-%m-%d"),
                "days_inactive": (now - latest_dt).days,
                "file_count": file_count,
            })
    return candidates


def write_report(candidates: list[dict], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Archive Candidates @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# 阈值: {ARCHIVE_THRESHOLD_DAYS} 天 (无新文件即视为候选)",
        f"# corpus: {CORPUS.relative_to(REPO).as_posix()}",
        "",
    ]
    if not candidates:
        lines.append("(没有项目满足归档候选阈值。)")
    else:
        lines.append(f"项目名\t最近活动日期\t闲置天数\t文件数")
        for c in candidates:
            lines.append(f"{c['project']}\t{c['latest_activity']}\t{c['days_inactive']}\t{c['file_count']}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    candidates = scan_archive_candidates(CORPUS)
    out = REPO / "logs" / f"archive_candidates_{datetime.now().strftime('%Y%m%d')}.txt"
    write_report(candidates, out)
    print(f"# archive_check: {len(candidates)} 个项目候选(阈值 {ARCHIVE_THRESHOLD_DAYS} 天)")
    print(f"# 报告: {out.relative_to(REPO).as_posix()}")
    if candidates:
        print()
        for c in candidates:
            print(f"  - {c['project']}: 最近 {c['latest_activity']}({c['days_inactive']} 天前) / {c['file_count']} 文件")
        print()
        print("提示:LLM 不主动 mv,只展示候选。如需归档,手动 `mv corpus/01-projects/<项目> corpus/04-archives/`。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
