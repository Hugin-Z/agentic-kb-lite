"""migrate_v023_to_v030.py — v0.2.3 → v0.3.0 tier 分层迁移候选扫描(dry-run only)

v0.3 阶段 4A 步骤 4.2 实现(详见 docs/v0.3-plan.md §7.3 步骤 4.2)。

行为(沿用 scripts/archive_check.py 同款 dry-run only 风格):

  1. 扫 corpus/01-projects/<project>/ + corpus/02-areas/<subdir>/ +
     corpus/03-resources/<subdir>/ 下的文件
     (跳过 .shelved/ / .archive/ / .fixtures/ / 04-archives bucket)
  2. 基于文件名 / 父目录 / 扩展名推断 tier 候选(参考 CLAUDE.md §6 Step E 规则的简化版):
     - working: 文件名前缀 build_/extract_/dump_/save_/check_/temp_/test_/demo_
     - versions: 文件名含 v[0-9]+ / 旧 / 草稿(family_key 留空,让用户填)
     - assets: 父目录是 素材/截图/图片/appendix / 扩展名是 .png/.jpg/.jpeg/.gif/.bmp/.webp/.tif/.tiff/.mp4/.mov/.avi/.mkv/.shp/.dbf/.shx/.zip
     - canonical: 文件名含 最终/建设方案/实施方案/需求说明书/研究报告/政策建议/审查要点/最终汇报
     - 其他: normal(默认不需要 mv)
  3. 输出 logs/v030_migration_candidates_<YYYYMMDD_HHMMSS>.md
     (类比 archive_check.py 风格 + plan §7.3 步骤 4.2 格式)
  4. **不自动 mv**(v0.3.0 dry-run only 决策;自动 mv 留 v0.4+,见 plan §7.3 + 附录 A.3)

v0.3.0 → v0.4+ 升级原因:mv 操作会破坏五件套一致性(详 plan §7.3 步骤 4.2):
  - logs/ingest_log.jsonl 的 target_rel_path 字段(增量判定关键)
  - is_already_ingested 增量判定
  - .md / .stub.md 内"正文在同目录 <sibling>.md"等指向兄弟文件的说明
  - .assets/ 目录跟 .md 的相对路径关系
  - frontmatter 的 kb_tier / kb_default_search / family_key 与新 target_dir 不一致

CLI:
  python scripts/migrate_v023_to_v030.py [--corpus-root <path>]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
LOGS_DIR = REPO / "logs"


# ====================== tier 推断规则(CLAUDE.md §6 Step E 简化版)======================

WORKING_PREFIXES = ("build_", "extract_", "dump_", "save_", "check_",
                    "temp_", "test_", "demo_")
VERSIONS_PATTERNS = [
    re.compile(r"_v\d+", re.IGNORECASE),         # _v1 / _v2 / _V3
    re.compile(r"v\d+\."),                        # v1.md / v2.docx
    re.compile(r"旧"),                            # 旧稿 / 旧版
    re.compile(r"草稿"),                          # 草稿
]
ASSETS_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff",
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm",
    ".shp", ".dbf", ".shx", ".qix", ".zip",
}
ASSETS_PARENT_KEYWORDS = ("素材", "截图", "图片", "appendix", "_pages")
CANONICAL_KEYWORDS = (
    "最终", "建设方案", "实施方案", "需求说明书", "研究报告",
    "政策建议", "审查要点", "最终汇报",
)

# 扫描跳过的子目录(不进入)
SKIP_DIRS = {".shelved", ".archive", ".fixtures", ".assets", ".frames"}


def infer_tier(file_path: Path) -> tuple[str, str]:
    """返回 (tier, reason);tier in {working, versions, assets, canonical, normal}。"""
    name = file_path.name
    name_lower = name.lower()
    ext = file_path.suffix.lower()
    parent = file_path.parent.name

    # 1. working:文件名前缀
    for prefix in WORKING_PREFIXES:
        if name_lower.startswith(prefix):
            return "working", f"文件名前缀 '{prefix}'"

    # 2. canonical:文件名含 canonical 关键词
    for kw in CANONICAL_KEYWORDS:
        if kw in name:
            return "canonical", f"文件名含 '{kw}'"

    # 3. assets:扩展名 / 父目录
    if ext in ASSETS_EXTS:
        return "assets", f"扩展名 '{ext}'"
    for kw in ASSETS_PARENT_KEYWORDS:
        if kw in parent:
            return "assets", f"父目录含 '{kw}'"

    # 4. versions:文件名版本号 / 旧 / 草稿
    for pat in VERSIONS_PATTERNS:
        if pat.search(name):
            return "versions", f"文件名匹配版本模式 '{pat.pattern}'"

    return "normal", "无明显特征(默认)"


def suggest_family_key(file_path: Path) -> str:
    """versions 类的 family_key 建议:剥掉版本号后的基线名 + 类型后缀。"""
    name = file_path.stem  # 不含扩展名
    ext = file_path.suffix.lstrip(".").lower()
    # 剥版本号
    baseline = re.sub(r"[_-]?[vV]\d+", "", name)
    baseline = re.sub(r"_?(旧|草稿)", "", baseline).strip("_- ")
    if not baseline:
        baseline = name
    return f"{baseline}_{ext}" if ext else baseline


# ====================== 扫 + 候选 + 写报告 ======================


def should_skip_dir(d: Path) -> bool:
    """判定是否跳过(隐藏 / .shelved / .archive / .fixtures / .assets / .frames)。"""
    name = d.name
    return name in SKIP_DIRS or name.startswith(".")


def walk_bucket(bucket_root: Path) -> list[Path]:
    """v0.4+ 可改 os.walk 显式跳过 SKIP_DIRS 提速;v0.3.0 简单 rglob + post-filter 够用。"""
    if not bucket_root.is_dir():
        return []
    files = []
    for p in bucket_root.rglob("*"):
        if not p.is_file():
            continue
        # 跳过 .stub.md / .vision.md 派生文件(它们不该被 mv 到 .shelved,跟源走)
        if p.name.endswith(".stub.md") or p.name.endswith(".vision.md"):
            continue
        # 跳过路径段含 SKIP_DIRS 任一目录的文件(已在 .shelved/.archive/.fixtures 等里)
        if any(part in SKIP_DIRS or part.startswith(".")
               for part in p.relative_to(bucket_root).parts[:-1]):
            continue
        files.append(p)
    return files


def build_target_path(file_path: Path, bucket_root: Path, bucket: str,
                       tier: str, family_key: str | None,
                       corpus_root: Path = CORPUS) -> str:
    """根据 tier 计算 mv 后的目标路径(相对 corpus 显示;family_key 缺时占位 <填 family_key>)。
    bucket = '01-projects' / '02-areas' / '03-resources'。
    corpus_root 默认全局 CORPUS;支持 --corpus-root 参数指定别的 root。"""
    rel = file_path.relative_to(corpus_root)
    rel_parts = rel.parts  # 含 bucket / project|subdir / ... / filename

    if tier in ("canonical", "normal"):
        # 不 mv(留原位)
        return ""

    # 找到要把 .shelved 插在哪一层:
    # 01-projects/<project>/ 之后 → .shelved/<tier>/[<family_key>/]/...
    # 02-areas/<subdir>/ 之后(subdir 可多级)→ 取第一段 subdir 之后 → 同上
    # 03-resources/<subdir>/ → 同上
    if bucket == "01-projects":
        # bucket / project / [01-方案/ 等]/ filename
        head = rel_parts[:2]   # bucket / project
        tail = rel_parts[2:]   # 5 子目录之一 / filename
    else:
        # bucket / subdir / [子级]/ filename  → subdir 可多级,取第一段
        head = rel_parts[:2]   # bucket / subdir
        tail = rel_parts[2:]   # 余下层级 / filename

    if tier == "versions":
        fk = family_key or "<填 family_key>"
        new_path = Path(*head) / ".shelved" / "versions" / fk / file_path.name
    else:  # working / assets
        # 保留原 tail 的中间目录段(剥掉最末尾 filename),让 .shelved/<tier>/ 后接相对原结构
        mid = "/".join(tail[:-1])
        if mid:
            new_path = Path(*head) / ".shelved" / tier / mid / file_path.name
        else:
            new_path = Path(*head) / ".shelved" / tier / file_path.name
    return str(new_path).replace("\\", "/")


def scan_candidates(corpus_root: Path) -> dict:
    """扫三 bucket,返回按 tier 分组的候选 dict。"""
    candidates = {"working": [], "versions": [], "assets": [], "canonical": []}
    counts = {"total_scanned": 0, "candidates": 0, "stay_normal": 0}

    for bucket in ("01-projects", "02-areas", "03-resources"):
        bucket_root = corpus_root / bucket
        for f in walk_bucket(bucket_root):
            counts["total_scanned"] += 1
            tier, reason = infer_tier(f)
            if tier == "normal":
                counts["stay_normal"] += 1
                continue
            counts["candidates"] += 1
            family_key = suggest_family_key(f) if tier == "versions" else None
            target = build_target_path(f, bucket_root, bucket, tier, family_key, corpus_root)
            # src 展示用 corpus 相对路径(去掉 corpus 根前缀,加 corpus 名头)
            try:
                src_rel = f.relative_to(corpus_root)
                src_disp = f"corpus/{src_rel.as_posix()}"
            except ValueError:
                src_disp = str(f).replace("\\", "/")
            candidates[tier].append({
                "src": src_disp,
                "target": target,
                "reason": reason,
                "family_key_suggest": family_key,
            })
    return {"candidates": candidates, "counts": counts}


def write_report(scan_result: dict, output: Path) -> Path:
    counts = scan_result["counts"]
    candidates = scan_result["candidates"]

    lines = [
        f"# v0.2.3 → v0.3.0 Migration Candidates(dry-run only)",
        f"",
        f"- 生成时间:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 扫描范围:`corpus/01-projects` + `corpus/02-areas` + `corpus/03-resources`(跳过 `.shelved/.archive/.fixtures` 等)",
        f"- 共扫描 {counts['total_scanned']} 文件 / 候选迁移 **{counts['candidates']}** 项 / 留 normal {counts['stay_normal']} 项",
        f"",
        f"---",
        f"",
        f"## 候选清单",
        f"",
    ]

    section_titles = {
        "canonical": "tier=canonical(建议手动标 frontmatter `kb_tier: canonical`,不需要 mv)",
        "working": "tier=working(建议手动 mv 到 `.shelved/working/`)",
        "versions": "tier=versions(建议手动 mv + 填 `family_key`)",
        "assets": "tier=assets(建议手动 mv 到 `.shelved/assets/`)",
    }
    for tier in ("canonical", "working", "versions", "assets"):
        items = candidates.get(tier, [])
        if not items:
            continue
        lines.append(f"### {section_titles[tier]}")
        lines.append(f"")
        lines.append(f"共 {len(items)} 项候选:")
        lines.append(f"")
        for item in items:
            lines.append(f"- [ ] `{item['src']}`")
            if item['target']:
                lines.append(f"  → `{item['target']}`")
            lines.append(f"  理由:{item['reason']}")
            if item.get("family_key_suggest"):
                lines.append(f"  family_key 建议:`{item['family_key_suggest']}`(用户审定)")
            lines.append(f"")

    lines.extend([
        f"---",
        f"",
        f"## 迁移步骤(人工)",
        f"",
        f"1. 审下方候选清单(打勾 / 删除 / 修改)",
        f"2. 手动 `mv` 选定的文件到目标路径",
        f"3. 删除 `logs/ingest_log.jsonl` 里对应旧 `target_rel_path` 的记录(避免增量判定混乱)",
        f"4. 重跑 ingest 让新的 target 重新登记 frontmatter(`kb_tier` / `kb_default_search` / `family_key`)",
        f"5. 验证:`python scripts/search.py --scope all --terms <...>` 默认应不再命中 working / versions / assets 内容",
        f"",
        f"---",
        f"",
        f"## v0.3.0 dry-run only 说明",
        f"",
        f"本工具**仅输出候选,不自动 mv**。自动 mv 留 v0.4+ 实现。",
        f"",
        f"理由:mv 操作会破坏 `logs/ingest_log.jsonl` / `.md` 内兄弟引用 / `.assets/` 相对路径 / `frontmatter kb_tier` 等五件套一致性,**复杂度等价于重做一次 ingest**(详 `docs/v0.3-plan.md` §7.3 步骤 4.2)。",
        f"",
    ])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def main() -> int:
    p = argparse.ArgumentParser(description="v0.2.3 → v0.3.0 tier 分层迁移候选扫描(dry-run only)")
    p.add_argument("--corpus-root", type=Path, default=CORPUS,
                   help="corpus 根目录(默认 <repo>/corpus)")
    args = p.parse_args()

    corpus_root = args.corpus_root.resolve()
    if not corpus_root.is_dir():
        sys.stderr.write(f"ERROR: corpus 根目录不存在或不是目录:{corpus_root}\n")
        return 2

    print(f"# v0.2.3 → v0.3.0 migration 候选扫描(dry-run only)")
    print(f"# corpus 根:{corpus_root}")
    print()

    scan_result = scan_candidates(corpus_root)
    counts = scan_result["counts"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = LOGS_DIR / f"v030_migration_candidates_{ts}.md"
    write_report(scan_result, output)

    print(f"# 扫描完成:{counts['total_scanned']} 文件 / 候选迁移 {counts['candidates']} 项 / 留 normal {counts['stay_normal']} 项")
    by_tier = scan_result["candidates"]
    for tier in ("canonical", "working", "versions", "assets"):
        items = by_tier.get(tier, [])
        if items:
            print(f"  - {tier}: {len(items)} 项")
    print()
    print(f"# 候选清单已写入:{output.relative_to(REPO)}")
    print(f"# 请人工审 + 手动 mv(v0.3.0 dry-run only,不自动 mv;自动 mv 留 v0.4+)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
