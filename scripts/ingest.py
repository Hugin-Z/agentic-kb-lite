"""ingest.py — knowledge-base 自动化 ingest pipeline(第一版)

对应 tests/查询记录.md G14-G18 规则,纯规则驱动,不调 LLM。

用法:
  python scripts/ingest.py <path>                            # 单文件或目录(递归)
  python scripts/ingest.py <path> --dry-run                  # 仅打印将要执行的动作,不写盘
  python scripts/ingest.py <path> --prefix-override 参考-    # 跨项目参考素材(J5 类)用,绕过 prefix_rules

不做的事(第一版边界):
  - 不做版本族(G3-G9)自动检测,留第二版
  - 不调 LLM(纯规则)
  - 不做 URL 输入
  - 不处理删除同步(增量 only)
"""
import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus"
PATH_MAP_FILE = REPO / "path_map.yaml"
INGEST_LOG = REPO / "logs" / "ingest_log.jsonl"

BINARY_EXTS = {".docx", ".doc", ".xlsx", ".pptx", ".pdf"}
TEXT_EXTS = {".html", ".txt", ".md", ".json"}

# v0.3 多模态接入:vision 待转扩展名(图像 + 视频)
# IMAGE_EXTS:纯图像文件,直接走 vision 待转(无需 markitdown 转 .md)
# VIDEO_EXTS:视频文件,走路径 B(ffmpeg 抽帧 + 逐帧 vision)
# 两者都在 process_file 内独立分支处理,不污染 BINARY/TEXT 流;
# infer_prefix 返回 None 时为这两类提供内置默认前缀(图-/视频-)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"}

DENSITY_THRESHOLD = 0.05      # G18 触发的字符密度上限(< 5%)
CHAR_COUNT_THRESHOLD = 2000   # G18 触发的字符总数上限(< 2000)
# G18 双条件 AND:密度 < 5% 且 字符总数 < 2000,即 R4-A 结构性稀薄
# 任一不成立走 G16(密度低但字符数足 = R4-B 衰减性稀薄,内容上足以入库)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def load_config():
    if not PATH_MAP_FILE.is_file():
        sys.stderr.write(f"ERROR: path_map.yaml 不存在 {PATH_MAP_FILE}\n")
        sys.exit(2)
    with open(PATH_MAP_FILE, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("path_mappings", []) or [], cfg.get("prefix_rules", {}) or {}


def norm_path(p):
    return str(p).replace("\\", "/")


def find_target_subdir(src_abs, mappings):
    """最长前缀匹配。返回 target_subdir 或 None。"""
    src_str = norm_path(src_abs)
    best = None
    best_len = -1
    for m in mappings:
        prefix = norm_path(m["source"]).rstrip("/")
        if src_str == prefix or src_str.startswith(prefix + "/"):
            if len(prefix) > best_len:
                best = m["target"]
                best_len = len(prefix)
    return best


def infer_prefix(filename, ext, rules):
    """按扩展名查 prefix_rules。返回 (prefix, rule_note) 或 (None, None)。"""
    rule = rules.get(ext)
    if rule is None:
        return None, None
    for kw in rule.get("keywords", []) or []:
        pat = kw["pattern"]
        if re.search(pat, filename, flags=re.IGNORECASE):
            return kw["prefix"], f"keyword:{pat}"
    default = rule.get("default")
    if default:
        return default, "default"
    return None, None


def get_md_engine(holder):
    if holder[0] is not None:
        return holder[0]
    try:
        from markitdown import MarkItDown
    except ImportError:
        sys.stderr.write("ERROR: markitdown 未安装。pip install 'markitdown[all]'\n")
        sys.exit(2)
    holder[0] = MarkItDown()
    return holder[0]


def derive_keywords(name_no_ext):
    parts = re.split(r"[-_\s\.\(\)（）【】\[\]]+", name_no_ext)
    return [p for p in parts if p and len(p) >= 2 and not p.isdigit()][:5]


def make_stub(src_path, scene, rule_id, density=None, char_count=None,
              source_abs_path=None, prefixed_name=None,
              vision_assets=None, vision_assets_extraction=None,
              vision_assets_raw_count=None):
    """生成 G11 stub 内容。scene 形如 '01-历史方案'。
    source_abs_path: ingest 时的源文件绝对路径,写入"源路径"字段(G11 必填,R3 退 stub 例外)。
    prefixed_name: corpus 落地的带前缀文件名,用于 G16 指向同目录 .md 兄弟文件。
    """
    src = Path(src_path)
    stat = src.stat()
    ext = src.suffix.lstrip(".").lower()
    size_bytes = stat.st_size
    if size_bytes < 1024 * 1024:
        size_human = f"{size_bytes/1024:.1f} KB"
    else:
        size_human = f"{size_bytes/1024/1024:.1f} MB"
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    name_no_ext = src.stem
    src_path_field = source_abs_path if source_abs_path is not None else str(src)

    # v0.3:vision_pending 标记 — 哪些 rule_id 的 stub 需要等待 vision 转写
    vision_pending = rule_id in ("G15", "G18", "V_PENDING_IMAGE", "V_PENDING_VIDEO")

    if rule_id == "G2":
        status = f"未入库正文(G2 超大文件 {size_bytes/1024/1024:.1f} MB > 50 MB,跳过 cp + 仅 stub)"
        note = f"G2 超大文件 stub。源未 cp 到 corpus(节省磁盘 + ingest 时间);源仍在原路径,如需打开请用源路径字段。"
        llm_hint = ("**LLM 处理规则**:本 stub 仅含元数据,源文件未 cp 到 corpus(G2 守门);"
                    "回答时只可说\"该素材是超大文件(>50 MB),未入库正文;请按源路径打开\","
                    "**禁止**对正文内容做任何推断。")
    elif rule_id == "G15":
        status = f"未入库正文(binary-{ext}, R3-pdf-blind:扫描件文本层为空)"
        note = "G15 扫描类 PDF stub。源 PDF 保留同目录,不入 .md。"
        llm_hint = ("**LLM 处理规则**:本 stub 仅含元数据,正文未入库;"
                    "回答时只可说\"该问题相关素材是 binary,正文未入库;请打开源路径\","
                    "**禁止**对正文内容做任何推断。")
    elif rule_id == "G18":
        status = (f"未入库正文(binary-{ext}, R4-A 结构性稀薄:"
                  f"markitdown 字符密度 {density:.1%} 且字符数 {char_count} < 2000)")
        note = "G18 结构性稀薄 stub(R4-A)。源保留同目录,不入 .md。"
        llm_hint = ("**LLM 处理规则**:本 stub 仅含元数据,正文未入库;"
                    "回答时只可说\"该问题相关素材是 binary,正文未入库;请打开源路径\","
                    "**禁止**对正文内容做任何推断。")
    elif rule_id == "V_PENDING_IMAGE":
        status = f"未入库正文(纯图像-{ext},等待 vision 转写;v0.3 路径 A)"
        note = "纯图像 stub,vision 待转。源图像保留同目录。vision 完成后同目录将生成 .vision.md。"
        llm_hint = ("**LLM 处理规则**:本 stub 仅含元数据,vision 正文未转写完成;"
                    "回答时只可说\"该问题相关素材是图像,vision 正文未入库;请打开源路径或等待 vision 转写\","
                    "**禁止**对图像内容做任何推断。")
    elif rule_id == "V_PENDING_VIDEO":
        status = f"未入库正文(视频-{ext},等待 vision 抽帧+转写;v0.3 路径 B)"
        note = "视频 stub,vision 待转。源视频保留同目录。vision 完成后同目录将生成 .vision.md(含帧序列叙事 + 帧明细)。"
        llm_hint = ("**LLM 处理规则**:本 stub 仅含元数据,vision 正文未转写完成;"
                    "回答时只可说\"该问题相关素材是视频,vision 正文未入库;请打开源路径或等待 vision 转写\","
                    "**禁止**对视频内容做任何推断。")
    else:
        # G16:三件共存(源 binary + 本 stub + 同目录 .md)
        status = (f"已转 markdown 正文(同目录 .md 文件;"
                  f"G16 三件共存形态:源 binary + 本 stub + .md")
        if density is not None:
            status += f",字符密度 {density:.1%}"
        status += ")"
        sibling = f"{prefixed_name}.md" if prefixed_name else f"{src.name}.md"
        note = f"G16 三件共存 stub。正文在同目录 `{sibling}`。"
        llm_hint = (f"**LLM 处理规则**:本 stub 仅作元数据索引,**正文在同目录 `{sibling}`**;"
                    "回答前优先读 .md 正文,本 stub 不构成 R2/stub-禁令场景。")

    keywords = derive_keywords(name_no_ext)
    vision_pending_line = "- vision_pending: YES\n" if vision_pending else ""
    # v0.3+ pptx 自动解嵌入图:vision_assets 三字段,仅在 extraction 非空时输出
    va_block = ""
    if vision_assets_extraction is not None:
        va_block = f"- vision_assets_extraction: {vision_assets_extraction}\n"
        if vision_assets_raw_count is not None:
            va_block += f"- vision_assets_raw_count: {vision_assets_raw_count}\n"
        if vision_assets:
            va_block += "- vision_assets:\n" + "".join(f"  - {p}\n" for p in vision_assets)

    return (
        f"# {name_no_ext}\n\n"
        f"- 类型: {ext}\n"
        f"- 大小: {size_human} ({size_bytes:,} 字节)\n"
        f"- mtime: {mtime}\n"
        f"- 场景: {scene}\n"
        f"- 源路径: {src_path_field}\n"
        f"- 状态: {status}\n"
        f"- 日期: {mtime[:10]}\n"
        f"- 与会人/对方/客户:\n"
        f"- 关键词: {', '.join(keywords)}\n"
        f"{vision_pending_line}"
        f"{va_block}\n"
        f"{llm_hint}\n\n"
        f"备注: {note}\n"
    )


def extract_pptx_assets(pptx_path, target_dir):
    """zipfile 解 .pptx 嵌入图(30KB 体积闸 + 20 张数量闸 + thumbnail/hyperlink 名闸 + zip-slip 校验 + try/except 降级)。
    返回 (status, [rel_paths] or None, raw_count or None);status ∈ {success, filtered_to_zero, no_media_in_zip, failed}。"""
    MIN_SIZE, MAX_ASSETS = 30 * 1024, 20
    IMG = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
    BLK = ("thumbnail", "hyperlink")
    try:
        with zipfile.ZipFile(pptx_path) as z:
            media = [(n, z.getinfo(n).file_size) for n in z.namelist()
                     if n.startswith("ppt/media/") and n.lower().endswith(IMG)]
            raw = len(media)
            if raw == 0:
                return "no_media_in_zip", None, 0
            cands = sorted(((n, s) for n, s in media
                            if s >= MIN_SIZE and not any(b in Path(n).name.lower() for b in BLK)),
                           key=lambda x: -x[1])[:MAX_ASSETS]
            if not cands:
                return "filtered_to_zero", None, raw
            assets_dir = target_dir / f"{Path(pptx_path).name}.assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            assets_abs = os.path.abspath(assets_dir)
            extracted = []
            for n, _ in cands:
                # zip-slip 防御:原始 name 解析后必须在 assets_dir 内,通过后扁平化到 .assets/ 根
                if os.path.commonpath([assets_abs, os.path.abspath(os.path.join(assets_dir, n))]) != assets_abs:
                    sys.stderr.write(f"skipped_zip_slip_attempt: {n}\n")
                    continue
                dst = assets_dir / Path(n).name
                with z.open(n) as src:
                    dst.write_bytes(src.read())
                extracted.append(norm_path(dst.relative_to(REPO)))
            return "success", extracted, raw
    except Exception as e:
        sys.stderr.write(f"extract_pptx_assets failed for {pptx_path}: {e}\n")
        return "failed", None, None


def files_equal(a, b):
    if not (a.is_file() and b.is_file()):
        return False
    sa, sb = a.stat(), b.stat()
    return sa.st_size == sb.st_size and int(sa.st_mtime) == int(sb.st_mtime)


def get_baseline(name_no_ext):
    """切出基线名(供同基线 glob)。简单实现:strip 末尾 [\\d._\\-vV]+ 字符。
    例:'tool_v3' → 'tool_v';'tool_v3_backup' → 'tool_v3_backup'(末尾非 strip 字符,基线即原名)。
    若 strip 后 < 4 字符则保留原名(避免误匹配)。"""
    base = re.sub(r"[\d._\-vV]+$", "", name_no_ext)
    return base if len(base) >= 4 else name_no_ext


def find_baseline_family(target_dir, prefix, src_basename):
    """glob 同目录下同基线文件。返回 [(name, bytes, mtime_str), ...] 排序。"""
    name_no_ext = Path(src_basename).stem
    baseline = get_baseline(name_no_ext)
    pat = f"{prefix}{baseline}*"
    family = []
    if target_dir.is_dir():
        for f in sorted(target_dir.glob(pat)):
            if f.is_file() and not f.name.endswith(".stub.md") and not f.name.endswith(".md"):
                # 只数源/正文层文件,不数派生 stub/md
                st = f.stat()
                mt = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                family.append((f.name, st.st_size, mt))
    return family, baseline


def log_action(record):
    INGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(INGEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_ingest_log():
    """v0.5 增量 ingest:读 INGEST_LOG,按 source_abs_path 索引最新记录(timestamp 最大)。
    返回 {source_abs_path: record},log 不存在返回空 dict。"""
    if not INGEST_LOG.is_file():
        return {}
    latest = {}
    with open(INGEST_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # 损坏行静默跳过,不影响其余记录
            src = rec.get("source_abs_path")
            if not src:
                continue
            prev = latest.get(src)
            if prev is None or rec.get("timestamp", "") > prev.get("timestamp", ""):
                latest[src] = rec
    return latest


def is_already_ingested(src_path, log_records):
    """v0.5 增量 ingest:按 Plan a Section 3 的 5 种情形规则判定。
    返回 True = 跳过(已入库且未变);False = 重入(走全量分流)。"""
    rec = log_records.get(str(src_path))
    if rec is None:
        return False  # 情形 4 无记录
    if rec.get("action", "").startswith("ERROR_"):
        return False  # 情形 5 上次错误,重试
    target_rel = rec.get("target_rel_path")
    if not target_rel or not (REPO / target_rel).exists():
        return False  # 情形 3 target 被删
    try:
        st = Path(src_path).stat()
    except OSError:
        return False  # 源不存在(应在 gather_files 已过滤,防御性)
    if st.st_size != rec.get("byte_size_src"):
        return False  # 情形 2 size 变
    if int(st.st_mtime) != rec.get("src_mtime"):
        return False  # 情形 2 mtime 变(v0.5 之前的记录缺 src_mtime,自动判为不等触发重入)
    return True  # 情形 1 完全一致,跳过


def make_record(src_path, target_rel, action, rule_applied, src_size, tgt_size, notes, char_density=None):
    rec = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source_abs_path": str(src_path),
        "target_rel_path": target_rel,
        "action": action,
        "rule_applied": rule_applied,
        "byte_size_src": src_size,
        "byte_size_tgt": tgt_size,
        "notes": notes,
    }
    if char_density is not None:
        rec["char_density"] = round(char_density, 4)
    # v0.5 增量 ingest:src_mtime(整数秒)用于跨次 ingest 的"内容/mtime 变更"判定;
    # 源文件已不存在的并发删除场景静默跳过(罕见,且 src 不存在时本次 ingest 早就走 ERROR 分支了)
    try:
        rec["src_mtime"] = int(Path(src_path).stat().st_mtime)
    except OSError:
        pass
    return rec


def is_temp_or_hidden(name, src_path=None):
    """返回 (is_skip, reason)。匹配则跳过,不进入后续分流。
    src_path: 可选完整路径;用于 v0.3+ .assets/ 子目录跳过判定(.pptx 嵌入图临时存放)。"""
    if name.startswith("~$"):
        return True, "Office 锁文件(~$ 开头)"
    if name in ("Thumbs.db", "desktop.ini"):
        return True, "Windows 系统文件"
    if name.endswith((".tmp", ".lock", ".bak")):
        return True, "临时文件(.tmp/.lock/.bak)"
    # v0.3:.vision.md 是 vision 转写派生文件,重新 ingest 同目录时明确跳过
    # (.stub.md 由 prefix_rules 缺 .md 规则间接跳过,这里 .vision.md 显式跳过更清晰)
    if name.endswith(".vision.md"):
        return True, "派生 vision 转写文件(.vision.md)"
    # v0.3+ pptx 自动解嵌入图:.assets/ 子目录是临时存放,vision 转完即删,不入库
    if src_path is not None and any(p.endswith(".assets") for p in Path(src_path).parts):
        return True, "派生 vision 嵌入图(.assets/ 目录内)"
    # 隐藏文件(. 开头),但保留我们自己的 .stub.md / .references.md
    if name.startswith(".") and not (name.endswith(".stub.md") or name == ".references.md"):
        return True, "隐藏文件(. 开头,非本仓库 stub)"
    return False, None


def process_file(src_abs, mappings, rules, dry_run, md_engine_holder, prefix_override=None):
    src_path = Path(src_abs)
    src_stat = src_path.stat()
    src_size = src_stat.st_size
    ext = src_path.suffix.lower()

    # 0. 临时 / 锁 / 隐藏文件:早期跳过,不进入 mapping/prefix/分流
    skip, skip_reason = is_temp_or_hidden(src_path.name, src_path)
    if skip:
        rec = make_record(src_path, None, "SKIPPED_TEMP", None, src_size, None,
                          f"{skip_reason},自动跳过")
        # 不写 ingest_log(避免污染主日志,体量太大),只走汇总
        return rec

    # 1. 查 path_map
    target_subdir = find_target_subdir(src_path, mappings)
    if target_subdir is None:
        rec = make_record(src_path, None, "ERROR_NO_MAPPING", None, src_size, None,
                          "path_map.yaml 中无匹配的 source 前缀。请添加 mapping 后重试。")
        if not dry_run:
            log_action(rec)
        return rec

    # 2. 推 G14 前缀(--prefix-override 优先级最高,绕过 prefix_rules)
    if prefix_override is not None:
        prefix = prefix_override
        rule_note = f"override:{prefix_override}"
    else:
        prefix, rule_note = infer_prefix(src_path.name, ext, rules)
        if prefix is None:
            # v0.3 fallback:IMAGE/VIDEO 用内置默认前缀(vision 类文件,
            # 不污染 path_map.yaml 的 G14 prefix 表)
            if ext in IMAGE_EXTS:
                prefix = "图-"
                rule_note = "v0.3-default-image"
            elif ext in VIDEO_EXTS:
                prefix = "视频-"
                rule_note = "v0.3-default-video"
            else:
                rec = make_record(src_path, None, "ERROR_NO_PREFIX", "G14", src_size, None,
                                  f"prefix_rules 中无 {ext} 类的规则,或该类规则无 default。请补充后重试。")
                if not dry_run:
                    log_action(rec)
                return rec

    # 3. 拼最终路径
    scene = target_subdir.split("/")[0]
    target_dir = CORPUS / target_subdir
    prefixed_name = f"{prefix}{src_path.name}"
    target_src = target_dir / prefixed_name
    target_rel = norm_path(target_src.relative_to(REPO))

    # 4. 同名冲突检查
    if target_src.exists():
        if files_equal(src_path, target_src):
            rec = make_record(src_path, target_rel, "SKIPPED_DUP", f"G14({prefix})",
                              src_size, target_src.stat().st_size, "字节 + mtime 一致,跳过")
            if not dry_run:
                log_action(rec)
            return rec
        # 不同 → 报错停;附带同基线族上下文(辅助 G9 人工判定)
        tgt_stat = target_src.stat()
        family, baseline = find_baseline_family(target_dir, prefix, src_path.name)
        notes = (
            f"目标已存在但内容不同。src 字节={src_size} mtime={int(src_stat.st_mtime)};"
            f"tgt 字节={tgt_stat.st_size} mtime={int(tgt_stat.st_mtime)}。"
            f"走 G3-G9 人工判定。"
        )
        if len(family) >= 3:
            notes += f"\n  ⚠ 同基线族 (≥3 份,基线='{prefix}{baseline}*',可能触发 G9,建议人工走 G9 判定):"
            for fname, fsize, fmt in family:
                notes += f"\n    - {fname} ({fsize:,} B, {fmt})"
        rec = make_record(
            src_path, target_rel, "ERROR_VERSION_CONFLICT", f"G14({prefix})",
            src_size, tgt_stat.st_size, notes,
        )
        if not dry_run:
            log_action(rec)
        return rec

    # 4.5 G2 超大文件守门(>50MB 全跳过 cp + 全做 stub,沿用 tests/查询记录.md G2 规则)
    if src_size > 50 * 1024 * 1024:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_G2", f"G14({prefix})+G2",
                               src_size, None, f"[dry-run] G2 超大文件 {src_size/1024/1024:.1f} MB > 50 MB,仅做 stub")
        target_dir.mkdir(parents=True, exist_ok=True)
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        stub_path.write_text(
            make_stub(src_path, scene, "G2",
                     source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                          "STUB_ONLY_G2", "G2", src_size, stub_path.stat().st_size,
                          f"G2 超大文件 {src_size/1024/1024:.1f} MB > 50 MB,跳过 cp + stub 化")
        log_action(rec)
        return rec

    # 5. binary 转 md(G15/G16/G18 分流);6. text 直接 cp
    if ext in BINARY_EXTS:
        if dry_run:
            return make_record(
                src_path, target_rel, "DRY_RUN_BINARY", f"G14({prefix})+G15/G16/G18(实际转换时定)",
                src_size, None,
                f"[dry-run] markitdown 转 .md,按字符密度走 G15/G16/G18 分流;源 + stub + .md(若 G16)三件落 {target_dir.relative_to(REPO).as_posix()}/",
            )
        md_engine = get_md_engine(md_engine_holder)
        try:
            result = md_engine.convert(str(src_path))
            md_text = result.text_content or ""
        except Exception as e:
            rec = make_record(src_path, target_rel, "ERROR_MARKITDOWN_FAILED", f"G14({prefix})",
                              src_size, None, f"markitdown 异常: {e}")
            log_action(rec)
            return rec

        char_count = len(md_text)
        density = char_count / src_size if src_size > 0 else 0.0
        target_dir.mkdir(parents=True, exist_ok=True)

        # 0 字节 → G15
        if char_count == 0:
            stub_path = target_dir / f"{prefixed_name}.stub.md"
            stub_path.write_text(
                make_stub(src_path, scene, "G15",
                          source_abs_path=str(src_path), prefixed_name=prefixed_name),
                encoding="utf-8")
            shutil.copy2(src_path, target_src)
            rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                              "STUB_ONLY_G15", "G15", src_size, stub_path.stat().st_size,
                              "扫描类:markitdown 0 字节,永久 stub,不入 .md", char_density=density)
            log_action(rec)
            return rec

        # 双条件 G18(R4-A 结构性稀薄):密度 < 5% AND 字符数 < 2000
        if density < DENSITY_THRESHOLD and char_count < CHAR_COUNT_THRESHOLD:
            # v0.3+ pptx 自动解嵌入图(其他 binary 类型不解,本小阶段约束)
            va_status, va_paths, va_raw = (extract_pptx_assets(src_path, target_dir)
                                           if ext == ".pptx" else (None, None, None))
            stub_path = target_dir / f"{prefixed_name}.stub.md"
            stub_path.write_text(
                make_stub(src_path, scene, "G18", density, char_count,
                          source_abs_path=str(src_path), prefixed_name=prefixed_name,
                          vision_assets=va_paths,
                          vision_assets_extraction=va_status,
                          vision_assets_raw_count=va_raw),
                encoding="utf-8")
            shutil.copy2(src_path, target_src)
            rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                              "STUB_ONLY_G18", "G18", src_size, stub_path.stat().st_size,
                              f"R4-A 结构性稀薄:密度 {density:.1%} < 5% 且字符数 {char_count} < 2000,永久 stub,不入 .md",
                              char_density=density)
            log_action(rec)
            return rec

        # 其余 → G16(三件共存:源 + stub + .md)
        # 包括两类:① 密度 ≥ 5% 正常文本主导;② 密度 < 5% 但字符数 ≥ 2000(R4-B 衰减性稀薄,如带覆层的 PDF)
        md_path = target_dir / f"{prefixed_name}.md"
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        md_path.write_text(md_text, encoding="utf-8")
        stub_path.write_text(
            make_stub(src_path, scene, "G16", density,
                      source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        shutil.copy2(src_path, target_src)
        rec = make_record(src_path, norm_path(md_path.relative_to(REPO)),
                          "INGESTED_MD", "G16", src_size, md_path.stat().st_size,
                          f"三件共存:源 + stub + .md,字符密度 {density:.1%}",
                          char_density=density)
        log_action(rec)
        return rec

    if ext in TEXT_EXTS:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_TEXT", f"G14({prefix})",
                               src_size, None, f"[dry-run] 文本类直接 cp 到 {target_rel}")
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, target_src)
        rec = make_record(src_path, target_rel, "INGESTED_TEXT", f"G14({prefix})",
                          src_size, target_src.stat().st_size, "文本类直接 cp")
        log_action(rec)
        return rec

    # v0.3 路径 A:纯图像类 → cp + 写 vision-pending stub(无 .md 正文)
    if ext in IMAGE_EXTS:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_VISION_IMAGE", f"G14({prefix})+V_PENDING_IMAGE",
                               src_size, None,
                               f"[dry-run] 纯图像 → 写 vision-pending stub,源 + stub 二件落 {target_dir.relative_to(REPO).as_posix()}/;待 vision 转写")
        target_dir.mkdir(parents=True, exist_ok=True)
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        stub_path.write_text(
            make_stub(src_path, scene, "V_PENDING_IMAGE",
                      source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        shutil.copy2(src_path, target_src)
        rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                          "VISION_PENDING_IMAGE", "V_PENDING_IMAGE", src_size, stub_path.stat().st_size,
                          "纯图像:vision 待转,source + stub 二件共存,vision 完成后同目录生成 .vision.md")
        log_action(rec)
        return rec

    # v0.3 路径 B:视频类 → cp + 写 vision-pending stub(无 .md 正文,待 ffmpeg 抽帧)
    if ext in VIDEO_EXTS:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_VISION_VIDEO", f"G14({prefix})+V_PENDING_VIDEO",
                               src_size, None,
                               f"[dry-run] 视频 → 写 vision-pending stub,源 + stub 二件落 {target_dir.relative_to(REPO).as_posix()}/;待 ffmpeg 抽帧 + vision 转写")
        target_dir.mkdir(parents=True, exist_ok=True)
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        stub_path.write_text(
            make_stub(src_path, scene, "V_PENDING_VIDEO",
                      source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        shutil.copy2(src_path, target_src)
        rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                          "VISION_PENDING_VIDEO", "V_PENDING_VIDEO", src_size, stub_path.stat().st_size,
                          "视频:vision 待转(ffmpeg 抽帧 + 逐帧 vision),source + stub 二件共存")
        log_action(rec)
        return rec

    # 不支持的扩展名
    rec = make_record(src_path, None, "ERROR_UNSUPPORTED_EXT", None, src_size, None,
                      f"不支持的扩展名 {ext}。BINARY={sorted(BINARY_EXTS)} TEXT={sorted(TEXT_EXTS)} "
                      f"IMAGE={sorted(IMAGE_EXTS)} VIDEO={sorted(VIDEO_EXTS)}")
    if not dry_run:
        log_action(rec)
    return rec


def gather_files(path):
    p = Path(path)
    if p.is_file():
        return [p.resolve()]
    if p.is_dir():
        return sorted(f.resolve() for f in p.rglob("*") if f.is_file())
    sys.stderr.write(f"ERROR: 路径不存在或不是文件/目录 {path}\n")
    sys.exit(2)


def print_record(i, total, rec):
    action = rec["action"]
    name = Path(rec["source_abs_path"]).name
    print(f"[{i}/{total}] {action}: {name}")
    if rec.get("target_rel_path"):
        print(f"    → {rec['target_rel_path']}")
    if rec.get("rule_applied"):
        print(f"    rule: {rec['rule_applied']}")
    if rec.get("char_density") is not None:
        print(f"    char_density: {rec['char_density']:.1%}")
    if rec.get("notes"):
        print(f"    notes: {rec['notes']}")


def main():
    ap = argparse.ArgumentParser(description="knowledge-base ingest pipeline (v0.5 增量 ingest)")
    ap.add_argument("path", nargs="?", default=None,
                    help="单文件或目录(递归);不传则全量扫整个 corpus 根目录")
    ap.add_argument("--dry-run", action="store_true", help="仅打印将要执行的动作,不写盘")
    ap.add_argument("--full", action="store_true",
                    help="v0.5:强制全量(opt-out)。默认行为:传 path 走增量(跳过已 ingest 且未变);不传 path 走全量")
    ap.add_argument("--prefix-override", default=None,
                    help="跨项目参考素材(J5 类)用,如 --prefix-override 参考-。绕过 prefix_rules 推断,优先级最高")
    args = ap.parse_args()
    # v0.5 默认行为:path 缺省 → 全量(扫 corpus 根);path 给定 → 增量(--full 可覆盖为全量)
    if args.path is None:
        actual_path = str(CORPUS)
        incremental = False
    else:
        actual_path = args.path
        incremental = not args.full

    mappings, rules = load_config()
    if not mappings:
        print("⚠ path_map.yaml 中没有 active 的 path_mappings")
        print()
        print("请先编辑仓库根的 path_map.yaml,做以下两步:")
        print("  1. 找到你想用的占位条目(默认 4 条都注释掉了)")
        print("  2. 去掉这条的行首 # 字符,把 source 改成你本机的项目目录绝对路径")
        print()
        print("详见 docs/试用指南.md 的「最简配置示例(3 行改路径)」段。")
        sys.exit(2)
    files = gather_files(actual_path)
    md_engine_holder = [None]
    # v0.5 增量过滤:只在 incremental 模式下生效,过滤已 ingest 且未变的文件
    incremental_skipped_count = 0
    if incremental:
        log_records = load_ingest_log()
        new_files = [f for f in files if not is_already_ingested(f, log_records)]
        incremental_skipped_count = len(files) - len(new_files)
        files = new_files

    mode_label = "全量" if not incremental else f"增量(跳过 {incremental_skipped_count} 个已入库且未变)"
    print(f"# ingest.py {'(DRY-RUN) ' if args.dry_run else ''}模式: {mode_label}")
    print(f"- 输入: {actual_path} ({len(files)} 个文件待处理)")
    print(f"- path_map.yaml: {len(mappings)} 条 mappings, {len(rules)} 类前缀规则")
    if args.prefix_override:
        print(f"- ⚠ --prefix-override='{args.prefix_override}' 启用,绕过 prefix_rules 推断")
    if not args.dry_run:
        print(f"- log: {INGEST_LOG.relative_to(REPO).as_posix()}")
    print()

    all_records = []
    for i, src in enumerate(files, 1):
        rec = process_file(src, mappings, rules, args.dry_run, md_engine_holder, args.prefix_override)
        print_record(i, len(files), rec)
        all_records.append(rec)

    # 汇总:按 action 分组打印 ERROR_*,落盘跳过清单(非 dry-run 才落盘)
    errors = [r for r in all_records if r["action"].startswith("ERROR_")]
    non_errors = [r for r in all_records if not r["action"].startswith("ERROR_")]
    temp_skips = [r for r in all_records if r["action"] == "SKIPPED_TEMP"]

    print()
    if temp_skips:
        print(f"# ℹ 已跳过 {len(temp_skips)} 个临时/隐藏文件(Office 锁文件 / 系统隐藏文件 / .tmp 等,不算错误)")
        for r in temp_skips[:3]:
            print(f"    示例: {Path(r['source_abs_path']).name} —— {r.get('notes', '')}")
        if len(temp_skips) > 3:
            print(f"    ... (共 {len(temp_skips)} 个)")
        print()

    if errors:
        skip_file_rel = None
        if not args.dry_run:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            skip_file = REPO / "logs" / f"ingest_skipped_{ts}.txt"
            skip_file.parent.mkdir(parents=True, exist_ok=True)
            with open(skip_file, "w", encoding="utf-8") as f:
                for r in errors:
                    f.write(f"{r['source_abs_path']}\t{r['action']}\t{r.get('notes', '')}\n")
            skip_file_rel = skip_file.relative_to(REPO).as_posix()

        suffix = f"(完整清单见 {skip_file_rel})" if skip_file_rel else "(dry-run, 未落盘清单)"
        print(f"# ⚠ 跳过 {len(errors)} 个文件 {suffix}")
        reason_map = {
            "ERROR_NO_MAPPING": "path_map.yaml 中无匹配 source",
            "ERROR_NO_PREFIX": "该扩展名无前缀规则",
            "ERROR_VERSION_CONFLICT": "目标已存在但内容不同(需走 G3-G9 人工判定)",
            "ERROR_MARKITDOWN_FAILED": "markitdown 转换异常",
            "ERROR_UNSUPPORTED_EXT": "不支持的扩展名",
        }
        by_action = defaultdict(list)
        for r in errors:
            by_action[r["action"]].append(r)
        for action in sorted(by_action.keys()):
            recs = by_action[action]
            reason = reason_map.get(action, "未分类")
            print(f"  - {action}: {len(recs)} 个(原因:{reason})")
            for r in recs[:3]:
                print(f"    示例: {Path(r['source_abs_path']).name}")
            if len(recs) > 3:
                print(f"    ... (共 {len(recs)} 个,完整清单见跳过文件)")
        print()

    # v0.3 vision_pending 汇总:G15(扫描 PDF) / G18(结构性稀薄,常为图为主 PPT) /
    # VISION_PENDING_IMAGE / VISION_PENDING_VIDEO,共 4 类待 vision 转写
    vision_pending_actions = {
        "STUB_ONLY_G15": ("扫描类 PDF (G15)", "Read 工具读 PDF;若文本层为空降级为分页 PNG 序列"),
        "STUB_ONLY_G18": ("结构性稀薄文档 (G18,常为图为主 PPT)", "需导出为 PDF/PNG 序列后再走 vision"),
        "VISION_PENDING_IMAGE": ("纯图像 (路径 A)", "Read 工具直接读图"),
        "VISION_PENDING_VIDEO": ("视频 (路径 B)", "需 ffmpeg 抽帧后逐帧 vision"),
    }
    vision_pending = [r for r in all_records if r["action"] in vision_pending_actions]
    if vision_pending:
        pending_file_rel = None
        if not args.dry_run:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            pending_file = REPO / "logs" / f"vision_pending_{ts}.txt"
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            with open(pending_file, "w", encoding="utf-8") as f:
                for r in vision_pending:
                    desc, hint = vision_pending_actions[r["action"]]
                    f.write(f"{r['source_abs_path']}\t{r['action']}\t{desc}\t{hint}\n")
            pending_file_rel = pending_file.relative_to(REPO).as_posix()

        suffix = f"(完整清单见 {pending_file_rel})" if pending_file_rel else "(dry-run, 未落盘清单)"
        print(f"# 👁 vision 待转 {len(vision_pending)} 个文件 {suffix}")
        by_action = defaultdict(list)
        for r in vision_pending:
            by_action[r["action"]].append(r)
        for action in sorted(by_action.keys()):
            recs = by_action[action]
            desc, hint = vision_pending_actions[action]
            print(f"  - {action}: {len(recs)} 个 — {desc}")
            print(f"    处置提示: {hint}")
            for r in recs[:3]:
                print(f"    示例: {Path(r['source_abs_path']).name}")
            if len(recs) > 3:
                print(f"    ... (共 {len(recs)} 个,完整清单见 vision_pending 文件)")
        print(f"  ⓘ Claude Code 对话层会读取该清单 + 询问用户(Y/N/行号筛选/类型筛选),触发 vision 转写")
        print()

    real_count = len(non_errors) - len(temp_skips)
    inc_seg = f" / 跳过-增量 {incremental_skipped_count} 个" if incremental else ""
    print(f"# ✅ 完成: 入库/跳过-重复 {real_count} 个 / 跳过-临时 {len(temp_skips)} 个 / 跳过-错误 {len(errors)} 个"
          f"{inc_seg}"
          f" / vision 待转 {len(vision_pending)} 个"
          f"{' (dry-run, 无写盘)' if args.dry_run else ''}")

    # 退出码:全部为 ERROR 且无任何正常动作 → exit 1(显式让 caller 感知问题);否则 exit 0
    if errors and not non_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
