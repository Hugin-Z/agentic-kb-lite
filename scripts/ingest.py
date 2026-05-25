"""ingest.py — knowledge-base ingest pipeline (v0.2: AI 语义路由)

v0.1 → v0.2 范式切换:
  - v0.1:`python ingest.py <path>`  → 单命令入口,内部按 path_map.yaml 规则匹配路由
  - v0.2:`python ingest.py scan-only <src>`     → 扫目录输出 routing_request.json
         `python ingest.py execute-plan <plan>` → 按 AI 给的 plan 执行迁移 + frontmatter 注入

为什么:真实操作者是 AI(Claude Code 在 agent loop 里跑 ingest);AI 看子目录名一眼就知道
"标准/"是 resources、"投标资料/"是 areas、"智慧城市可视化平台"是 project,把判断写进
yaml 正则是低效的反 AI 设计。详见 docs/v0.2-plan.md §2.2、CLAUDE.md 第 6 节"PARA 路由协议"。

G14/G15/G16/G18 分流、markitdown 转换、stub 生成、vision_pending 标记**完全保留**,只是
target 路径由 routing_plan 外部给定,不再由 path_map.yaml 内部推断。
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

BINARY_EXTS = {".docx", ".doc", ".xlsx", ".pptx", ".pdf",
               # v0.2 阶段 4:vsdx + odf 三件加入 markitdown 主流程
               ".vsdx", ".odt", ".ods", ".odp"}
TEXT_EXTS = {
    ".html", ".txt", ".md", ".json",
    # v0.2.3 5th-1(Codex 测试仓库真实素材现场反馈):常见脚本 / 表格 / GIS 文本文件,
    # 按原文 shutil.copy2 入库即可被 ripgrep 检索;不需要 markitdown 转换。
    # .py:用户脚本 / .csv:表格 / .geojson:GIS 矢量 / .xml:配置/数据交换
    # .cpg / .prj / .meta / .tfw:GIS 元数据小文件(投影 / 字符集 / 地理参考)
    ".py", ".csv", ".geojson", ".xml", ".cpg", ".prj", ".meta", ".tfw",
}

# v0.2 阶段 4:vsdx 走 LibreOffice headless 转 PDF 后接现有 G15/G16 路径;
# LibreOffice 不可用时永久 stub 标 failed_no_libreoffice(plan §7.3 步骤 4.3)
VSDX_EXT = ".vsdx"

# v0.3 多模态接入(沿用 v0.1):图像 + 视频走 vision 待转
# v0.2.3 5th-2:加 .tif/.tiff(Codex 测试仓库现场反馈;TIFF 是 GIS 业务高频遥感影像格式,
# Claude Code 内置 vision 能力直接 Read 即可识别,沿用路径 A 无需新增依赖)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"}

DENSITY_THRESHOLD = 0.05      # G18 触发的字符密度上限(< 5%)
CHAR_COUNT_THRESHOLD = 2000   # G18 触发的字符总数上限(< 2000)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def norm_path(p):
    return str(p).replace("\\", "/")


# ====================== v0.2 新增:scan-only / execute-plan / inject_frontmatter ======================


def _file_node(p: Path, src_root: Path) -> dict:
    stat = p.stat()
    return {
        "rel_path": norm_path(p.relative_to(src_root)),
        "abs_path": norm_path(p.resolve()),
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%S"),
        "type": "file",
        "ext": p.suffix.lower(),
    }


def _dir_node(d: Path, src_root: Path, child_count: int) -> dict:
    return {
        "rel_path": norm_path(d.relative_to(src_root)) + "/",
        "type": "dir",
        "child_count": child_count,
    }


def scan_and_write_request(src_dir: Path, output: Path) -> dict:
    """扫源目录 → routing_request.json(v0.2 步骤 2.2)。
    不做任何路由/分流判断,纯目录扫描。"""
    src_dir = src_dir.resolve()
    if not src_dir.is_dir():
        sys.stderr.write(f"ERROR: src_dir 不是目录:{src_dir}\n")
        sys.exit(2)

    tree: list[dict] = []
    ext_counts: dict[str, int] = defaultdict(int)
    file_count = dir_count = 0
    for item in sorted(src_dir.rglob("*")):
        if item.is_dir():
            # 排除 __pycache__ / .git 等
            if item.name in ("__pycache__", ".git"):
                continue
            children = [c for c in item.iterdir() if not (c.name == "__pycache__" or c.name == ".git")]
            tree.append(_dir_node(item, src_dir, len(children)))
            dir_count += 1
            continue
        # 文件:跳过临时/隐藏(同 ingest 主流程)
        skip, _ = is_temp_or_hidden(item.name, item)
        if skip:
            continue
        tree.append(_file_node(item, src_dir))
        ext_counts[item.suffix.lower()] += 1
        file_count += 1

    request = {
        "src_root": norm_path(src_dir),
        "scan_timestamp": datetime.now().isoformat(timespec="seconds"),
        "tree": tree,
        "stats": {
            "total_files": file_count,
            "total_dirs": dir_count,
            "extensions": dict(sorted(ext_counts.items())),
        },
    }

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        out_disp = output.relative_to(REPO)
    except ValueError:
        out_disp = output
    print(f"[scan-only] {file_count} 文件 / {dir_count} 目录 → {out_disp}")
    return request


def inject_frontmatter(md_file: Path, frontmatter: dict) -> str:
    """v0.2 步骤 2.4:向 .md 注入 YAML frontmatter。
    - 已有 frontmatter:保留,只补缺失字段(不覆盖原值)
    - 无 frontmatter:完整注入
    - frontmatter 格式坏:跳过(保守),返回 'malformed_preserved'
    返回 'injected_new' / 'merged_existing' / 'malformed_preserved' / 'no_change'

    v0.2.2 C-2 顺手修:读用 utf-8-sig 容忍用户 hand-edit 后带 BOM 的 .md
    (Windows Notepad 默认存 UTF-8 BOM);写仍用 utf-8 不带 BOM(标准产物)。
    """
    content = md_file.read_text(encoding="utf-8-sig")

    if content.startswith("---\n"):
        end_marker = content.find("\n---\n", 4)
        if end_marker < 0:
            return "malformed_preserved"
        existing_fm_text = content[4:end_marker]
        try:
            existing_fm = yaml.safe_load(existing_fm_text) or {}
            if not isinstance(existing_fm, dict):
                return "malformed_preserved"
        except yaml.YAMLError:
            return "malformed_preserved"
        added = 0
        for k, v in frontmatter.items():
            if k not in existing_fm:
                existing_fm[k] = v
                added += 1
        if added == 0:
            return "no_change"
        new_fm_text = yaml.safe_dump(existing_fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        content = f"---\n{new_fm_text}---\n{content[end_marker+5:]}"
        md_file.write_text(content, encoding="utf-8")
        return "merged_existing"

    fm_text = yaml.safe_dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    content = f"---\n{fm_text}---\n\n{content}"
    md_file.write_text(content, encoding="utf-8")
    return "injected_new"


# ====================== 保留:v0.1 公共工具(make_stub / extract_pptx_assets / 增量判定 等) ======================


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
    """生成 G11 stub 内容。scene 现在由 plan 决定(如 '01-projects/智慧城市可视化平台'),不再从 path_map 取。"""
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
    """zipfile 解 .pptx 嵌入图(30KB 体积闸 + 20 张数量闸 + thumbnail/hyperlink 名闸 + zip-slip 校验 + try/except 降级)。"""
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


def extract_docx_assets(docx_path, target_dir):
    """v0.2 阶段 4 步骤 4.1:zipfile 解 .docx 嵌入图(word/media/*),沿用 v0.4 .pptx 三闸过滤机制。
    返回 (status, [rel_paths] or None, raw_count or None);status ∈ {success, filtered_to_zero, no_media_in_zip, failed}。

    类比 extract_pptx_assets,差异:
      - 媒体目录 ppt/media → word/media
      - 解出 dir 命名仍是 `<prefixed_name>.assets/`(沿用 v0.4 命名,vision 转完即删)
    """
    MIN_SIZE, MAX_ASSETS = 30 * 1024, 20
    IMG = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
    BLK = ("thumbnail", "hyperlink")
    try:
        with zipfile.ZipFile(docx_path) as z:
            media = [(n, z.getinfo(n).file_size) for n in z.namelist()
                     if n.startswith("word/media/") and n.lower().endswith(IMG)]
            raw = len(media)
            if raw == 0:
                return "no_media_in_zip", None, 0
            cands = sorted(((n, s) for n, s in media
                            if s >= MIN_SIZE and not any(b in Path(n).name.lower() for b in BLK)),
                           key=lambda x: -x[1])[:MAX_ASSETS]
            if not cands:
                return "filtered_to_zero", None, raw
            assets_dir = target_dir / f"{Path(docx_path).name}.assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            assets_abs = os.path.abspath(assets_dir)
            extracted = []
            for n, _ in cands:
                if os.path.commonpath([assets_abs, os.path.abspath(os.path.join(assets_dir, n))]) != assets_abs:
                    sys.stderr.write(f"skipped_zip_slip_attempt: {n}\n")
                    continue
                dst = assets_dir / Path(n).name
                with z.open(n) as src:
                    dst.write_bytes(src.read())
                extracted.append(norm_path(dst.relative_to(REPO)))
            return "success", extracted, raw
    except Exception as e:
        sys.stderr.write(f"extract_docx_assets failed for {docx_path}: {e}\n")
        return "failed", None, None


def extract_docx_tables(docx_path):
    """v0.2 阶段 4 步骤 4.2:python-docx 抽 docx 所有表格 → markdown 表格列表。
    处理合并单元格(占位标记)和空单元格(标"-")。

    返回 [str, ...] markdown 表格字符串列表(每个表一个 str)。失败返回 []。

    设计:不替换 markitdown 转出的"空骨架表",而是把 python-docx 抽出的版本作为补充段
    append 到 .md 末尾"## 嵌入表(python-docx 抽取版本)"。两份共存让 LLM 检索时有 2 个命中。
    """
    try:
        from docx import Document
    except ImportError:
        sys.stderr.write("WARN: python-docx 未安装,跳过 docx 嵌入表抽取(pip install python-docx)\n")
        return []
    try:
        doc = Document(str(docx_path))
    except Exception as e:
        sys.stderr.write(f"extract_docx_tables open failed for {docx_path}: {e}\n")
        return []

    md_tables = []
    for tbl in doc.tables:
        rows = []
        for row in tbl.rows:
            cells_text = []
            for cell in row.cells:
                # python-docx 合并单元格:同一 cell.text 会在合并的多个 row 出现;
                # 用 "—" 替换 cell 内 | 字符,避免破坏 markdown 表格语法
                txt = (cell.text or "").strip().replace("|", "／").replace("\n", " ")
                if not txt:
                    txt = "-"
                cells_text.append(txt)
            rows.append(cells_text)
        if not rows:
            continue
        ncols = max(len(r) for r in rows)
        # 对齐列数(python-docx 合并单元格场景可能 row 列数不齐,补 "-")
        rows = [r + ["-"] * (ncols - len(r)) for r in rows]
        # 第一行作为表头
        header = "| " + " | ".join(rows[0]) + " |"
        sep = "| " + " | ".join(["---"] * ncols) + " |"
        body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
        md_tables.append("\n".join([header, sep] + body))
    return md_tables


def process_vsdx_to_pdf(vsdx_path, target_dir):
    """v0.2 阶段 4 步骤 4.3:soffice headless 把 .vsdx 转 PDF。
    返回 (status, pdf_path_or_None);
    status ∈ {success, failed_no_libreoffice, failed_convert}
    """
    import subprocess
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return "failed_no_libreoffice", None
    try:
        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf",
             "--outdir", str(target_dir), str(vsdx_path)],
            capture_output=True, timeout=120, text=True,
        )
        if result.returncode != 0:
            sys.stderr.write(f"soffice convert failed: {result.stderr}\n")
            return "failed_convert", None
        pdf_path = target_dir / (Path(vsdx_path).stem + ".pdf")
        if not pdf_path.is_file():
            return "failed_convert", None
        return "success", pdf_path
    except Exception as e:
        sys.stderr.write(f"process_vsdx_to_pdf failed: {e}\n")
        return "failed_convert", None


def files_equal(a, b):
    if not (a.is_file() and b.is_file()):
        return False
    sa, sb = a.stat(), b.stat()
    return sa.st_size == sb.st_size and int(sa.st_mtime) == int(sb.st_mtime)


def log_action(record):
    INGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(INGEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_ingest_log():
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
                continue
            src = rec.get("source_abs_path")
            if not src:
                continue
            prev = latest.get(src)
            if prev is None or rec.get("timestamp", "") > prev.get("timestamp", ""):
                latest[src] = rec
    return latest


def is_already_ingested(src_path, log_records):
    """v0.5 增量 ingest:5 情形规则判定。"""
    rec = log_records.get(str(src_path))
    if rec is None:
        return False
    if rec.get("action", "").startswith("ERROR_"):
        return False
    target_rel = rec.get("target_rel_path")
    if not target_rel or not (REPO / target_rel).exists():
        return False
    try:
        st = Path(src_path).stat()
    except OSError:
        return False
    if st.st_size != rec.get("byte_size_src"):
        return False
    if int(st.st_mtime) != rec.get("src_mtime"):
        return False
    return True


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
    try:
        rec["src_mtime"] = int(Path(src_path).stat().st_mtime)
    except OSError:
        pass
    return rec


def is_temp_or_hidden(name, src_path=None):
    if name.startswith("~$"):
        return True, "Office 锁文件(~$ 开头)"
    if name in ("Thumbs.db", "desktop.ini"):
        return True, "Windows 系统文件"
    if name.endswith((".tmp", ".lock", ".bak")):
        return True, "临时文件(.tmp/.lock/.bak)"
    if name.endswith(".vision.md"):
        return True, "派生 vision 转写文件(.vision.md)"
    if src_path is not None and any(p.endswith(".assets") for p in Path(src_path).parts):
        return True, "派生 vision 嵌入图(.assets/ 目录内)"
    if src_path is not None and any(p.endswith(".frames") for p in Path(src_path).parts):
        return True, "派生视频抽帧(.frames/ 目录内)"
    if name.startswith(".") and not (name.endswith(".stub.md") or name == ".references.md"):
        return True, "隐藏文件(. 开头,非本仓库 stub)"
    return False, None


# ====================== v0.2 重构:process_file_with_explicit_target ======================


# v0.2.1 P0-2:execute_plan 路径边界校验
# 防御 malformed routing_plan.json — AI 产出有可能(尤其是 jailbreak / 错配 prompts 时)
# 包含 ".."、绝对路径前缀、路径分隔符等危险字段;统一在拼路径前拒绝
ALLOWED_BUCKETS = {"01-projects", "02-areas", "03-resources", "04-archives"}

# v0.2.2 Codex-5th 系统性升级:从"打补丁式扩字段"升到完整三层校验
#   (key 存在 + 类型正确 + 非空),避免下轮 Codex 再发现 ai_reason 空串 /
#   target_filename 非 str / frontmatter null 等同类问题
#
# 演进史:
#   v0.2.1 P0-2:加 src_abs / target_bucket / target_filename 必填(key 存在)
#   v0.2.2 C-1:加 target_subdir(key 存在)+ 01-projects 时 target_project 必填
#   v0.2.2 Codex-4th:加 frontmatter / ai_reason(key 存在)
#   v0.2.2 Codex-5th(本轮):升级为 SCHEMA dict + 三层校验
#
# 三层语义:
#   1. key 存在:字段名 in item.keys()
#   2. 类型正确:isinstance(item[field], schema["type"])
#   3. 非空(仅 non_empty=True 时):
#        - str 类型:value.strip() 非空
#        - dict 类型:不强制(空 {} 合法 — frontmatter 可缺 type/date/project/tags 全字段)
#
#   特殊规则:
#     - src_abs:必须是绝对路径(Path(...).is_absolute())
#     - target_bucket:必须在 ALLOWED_BUCKETS 白名单
#     - target_project:仅当 target_bucket=01-projects 时必填且非空
#     - 路径穿越:沿用 P0-2 _check_path_component 对 project/subdir/filename 字段
REQUIRED_FIELDS_SCHEMA = {
    "src_abs":         {"type": str,  "non_empty": True},
    "target_bucket":   {"type": str,  "non_empty": True},
    "target_subdir":   {"type": str,  "non_empty": True},
    "target_filename": {"type": str,  "non_empty": True},
    "frontmatter":     {"type": dict, "non_empty": False},  # 空 dict {} 合法
    "ai_reason":       {"type": str,  "non_empty": True},
}


def _validate_plan_item_paths(item: dict) -> None:
    """v0.2.2 Codex-5th:对 plan item 做完整 3 层校验 + 路径边界校验。
    三层 = key 存在 + 类型正确 + 非空;路径边界 = src_abs 绝对路径 + bucket 白名单 +
    target_project 条件必填 + 路径穿越(.. / 绝对路径前缀 / 单层限制)。
    失败抛 ValueError(message 含字段名 + 触发原因);execute_plan 调用方 catch
    后转 ERROR_INVALID_PLAN_ITEM,不中断其他 items。"""

    # ====================== Layer 1+2+3:key 存在 + 类型 + 非空 ======================
    for field, rules in REQUIRED_FIELDS_SCHEMA.items():
        # Layer 1: key 存在
        if field not in item:
            raise ValueError(f"missing required field: {field}")

        value = item[field]
        expected_type = rules["type"]

        # Layer 2: 类型正确
        if not isinstance(value, expected_type):
            raise ValueError(
                f"field '{field}' must be {expected_type.__name__}, "
                f"got {type(value).__name__}: {value!r}"
            )

        # Layer 3: 非空(仅 str + non_empty=True 时;dict 类型不强制非空)
        if rules["non_empty"] and isinstance(value, str) and not value.strip():
            raise ValueError(f"field '{field}' must not be empty string (got: {value!r})")

    # ====================== Layer 4:字段特殊规则 ======================

    # src_abs 必须是绝对路径
    src_path = Path(item["src_abs"])
    if not src_path.is_absolute():
        raise ValueError(f"src_abs must be absolute path, got: {item['src_abs']!r}")

    # target_bucket 白名单
    bucket = item["target_bucket"]
    if bucket not in ALLOWED_BUCKETS:
        raise ValueError(
            f"target_bucket '{bucket}' not in whitelist {sorted(ALLOWED_BUCKETS)}"
        )

    # 01-projects bucket 必须有非空 target_project
    if bucket == "01-projects":
        tp = item.get("target_project")
        if not isinstance(tp, str) or not tp.strip():
            raise ValueError(
                f"01-projects bucket requires non-empty target_project, "
                f"got: {tp!r}"
            )

    # ====================== Layer 5:路径穿越校验(沿用 P0-2)======================

    def _check_path_component(field_name: str, value, allow_subpath: bool = False) -> None:
        """检测 .. / 绝对路径前缀 / 路径分隔符(单层 vs 多级);
        value 已在 Layer 1-3 保证为合法 str(非空);target_project 可能为 None(非 01-projects 时),特别处理。"""
        if value is None or value == "":
            return  # target_project 在非 01-projects 时允许 None
        if ".." in value.split("/") or ".." in value.split("\\"):
            raise ValueError(f"{field_name} contains '..' path traversal segment: {value!r}")
        # Windows 盘符 / POSIX 根
        if len(value) >= 2 and value[1] == ":":
            raise ValueError(f"{field_name} contains absolute path prefix (Windows drive): {value!r}")
        if value.startswith("/") or value.startswith("\\"):
            raise ValueError(f"{field_name} starts with path separator (absolute path): {value!r}")
        # 路径分隔符:filename / project 不允许;subdir 允许内部 / 作为多级
        if not allow_subpath:
            if "/" in value or "\\" in value:
                raise ValueError(f"{field_name} contains path separator (must be single-level): {value!r}")

    _check_path_component("target_project", item.get("target_project"), allow_subpath=False)
    _check_path_component("target_subdir", item["target_subdir"], allow_subpath=True)
    _check_path_component("target_filename", item["target_filename"], allow_subpath=False)


# v0.2.2 Codex-4th 历史别名(REQUIRED_FIELDS):部分 progress.md 引用,保留向后兼容
REQUIRED_FIELDS = set(REQUIRED_FIELDS_SCHEMA.keys())


def _build_target_dir(item: dict) -> Path:
    """从 plan item 构造 corpus 内 target_dir 绝对路径。
    调用前必须先经 `_validate_plan_item_paths` 校验(P0-2)。
    末尾再 resolve + 边界 sanity check:确保拼出来的路径在 CORPUS 内。"""
    bucket = item["target_bucket"]
    parts = [bucket]
    if bucket == "01-projects":
        parts.append(item["target_project"])
        parts.append(item["target_subdir"])
    else:
        # 02-areas / 03-resources / 04-archives:target_subdir 可能是多级(如 '产品方案库/子目录')
        sub = item.get("target_subdir") or ""
        if sub:
            parts.extend(sub.strip("/").split("/"))
    target_dir = CORPUS.joinpath(*parts)
    # 二次防御:resolve 后必须在 CORPUS 内(若校验已拒 .. 则此步永真,但保留作 defense in depth)
    corpus_resolved = CORPUS.resolve()
    target_resolved = target_dir.resolve()
    try:
        target_resolved.relative_to(corpus_resolved)
    except ValueError:
        raise ValueError(
            f"target 路径不在 corpus 内: {target_resolved} (corpus={corpus_resolved})"
        )
    return target_dir


def _scene_label(item: dict) -> str:
    """供 make_stub 的 scene 字段使用。"""
    bucket = item["target_bucket"]
    if bucket == "01-projects":
        return f"{bucket}/{item['target_project']}"
    sub = item.get("target_subdir") or ""
    return f"{bucket}/{sub}" if sub else bucket


def process_file_with_explicit_target(item: dict, dry_run: bool, md_engine_holder, incremental: bool, log_records: dict) -> dict:
    """v0.2 步骤 2.3:target 路径由 plan 外部传入,G14/G15/G16/G18 分流逻辑保持不变。

    item 必填字段(详见 docs/v0.2-plan.md §2.3 与附录 A.1):
      src_abs / target_bucket / target_subdir / target_filename / frontmatter / ai_reason
      (01-projects 还要 target_project)
    """
    src_path = Path(item["src_abs"])
    if not src_path.exists():
        return make_record(src_path, None, "ERROR_SRC_MISSING", None, 0, None,
                          f"plan item 指向的源文件不存在:{src_path}")
    src_stat = src_path.stat()
    src_size = src_stat.st_size
    ext = src_path.suffix.lower()

    skip, skip_reason = is_temp_or_hidden(src_path.name, src_path)
    if skip:
        return make_record(src_path, None, "SKIPPED_TEMP", None, src_size, None,
                          f"{skip_reason},自动跳过")

    # v0.5 增量跳过(v0.2 默认走增量)
    if incremental and is_already_ingested(src_path, log_records):
        return make_record(src_path, log_records[str(src_path)].get("target_rel_path"),
                          "SKIPPED_INCREMENTAL", "v0.5-incremental",
                          src_size, None, "已 ingest 且未变(size+mtime 一致),增量跳过")

    target_dir = _build_target_dir(item)
    prefixed_name = item["target_filename"]
    target_src = target_dir / prefixed_name
    target_rel = norm_path(target_src.relative_to(REPO))
    scene = _scene_label(item)
    frontmatter = item.get("frontmatter") or {}

    # 同名冲突
    if target_src.exists():
        if files_equal(src_path, target_src):
            rec = make_record(src_path, target_rel, "SKIPPED_DUP", "v0.2-plan-routed",
                              src_size, target_src.stat().st_size, "字节 + mtime 一致,跳过")
            if not dry_run:
                log_action(rec)
            return rec
        rec = make_record(src_path, target_rel, "ERROR_TARGET_CONFLICT", "v0.2-plan-routed",
                          src_size, target_src.stat().st_size,
                          f"target 已存在但内容不同;plan 应给新的 target_filename 消歧(如加项目前缀)。")
        if not dry_run:
            log_action(rec)
        return rec

    # G2 超大守门
    if src_size > 50 * 1024 * 1024:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_G2", "v0.2-plan-routed+G2",
                               src_size, None, f"[dry-run] G2 超大 {src_size/1024/1024:.1f} MB")
        target_dir.mkdir(parents=True, exist_ok=True)
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        stub_path.write_text(
            make_stub(src_path, scene, "G2", source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        if frontmatter:
            inject_frontmatter(stub_path, frontmatter)
        rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                          "STUB_ONLY_G2", "G2", src_size, stub_path.stat().st_size,
                          f"G2 超大 {src_size/1024/1024:.1f} MB,跳过 cp + stub 化")
        log_action(rec)
        return rec

    # v0.2 阶段 4 步骤 4.3:vsdx 走 LibreOffice headless → PDF → 再走现有 binary 路径
    # LibreOffice 不可用时永久 stub 标 failed_no_libreoffice(plan §7.3 步骤 4.3 降级路径)
    if ext == VSDX_EXT:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_VSDX", "v0.2-plan-routed+vsdx",
                               src_size, None, "[dry-run] vsdx → LibreOffice 转 PDF → 现有 binary 分流")
        target_dir.mkdir(parents=True, exist_ok=True)
        vsdx_status, pdf_path = process_vsdx_to_pdf(src_path, target_dir)
        if vsdx_status == "failed_no_libreoffice":
            stub_path = target_dir / f"{prefixed_name}.stub.md"
            stub_path.write_text(
                make_stub(src_path, scene, "G15",
                          source_abs_path=str(src_path), prefixed_name=prefixed_name),
                encoding="utf-8")
            # 在 stub 末尾追加 vsdx 降级原因(沿用 .pptx vision_assets 字段的"软扩展"思路,改写 status 标签)
            stub_extra = (f"\n- vsdx_status: failed_no_libreoffice\n"
                         f"- 降级原因: LibreOffice (soffice) 未安装,无法把 .vsdx 转 PDF;走永久 stub 不入正文\n"
                         f"- 修复方案: 装 LibreOffice 后重跑 ingest(plan §7.3 步骤 4.3)\n")
            with open(stub_path, "a", encoding="utf-8") as f:
                f.write(stub_extra)
            shutil.copy2(src_path, target_src)
            if frontmatter:
                inject_frontmatter(stub_path, frontmatter)
            rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                              "STUB_ONLY_VSDX_NO_LIBREOFFICE", "vsdx+G15",
                              src_size, stub_path.stat().st_size,
                              "vsdx 降级:LibreOffice 不可用,永久 stub")
            log_action(rec)
            return rec
        if vsdx_status == "failed_convert":
            rec = make_record(src_path, target_rel, "ERROR_VSDX_CONVERT_FAILED", "vsdx",
                              src_size, None, "vsdx 转 PDF 失败(LibreOffice 可用但转换报错)")
            log_action(rec)
            return rec
        # success:用 PDF 路径接 markitdown 现有 binary 分流;原 .vsdx 也 cp 到 target_src
        shutil.copy2(src_path, target_src)
        md_engine = get_md_engine(md_engine_holder)
        try:
            result = md_engine.convert(str(pdf_path))
            md_text = result.text_content or ""
        except Exception as e:
            rec = make_record(src_path, target_rel, "ERROR_MARKITDOWN_FAILED", "vsdx+G15/G16",
                              src_size, None, f"vsdx 转 PDF 成功但 markitdown 异常: {e}")
            log_action(rec)
            return rec
        char_count = len(md_text)
        density = char_count / src_size if src_size > 0 else 0.0
        if char_count == 0:
            stub_path = target_dir / f"{prefixed_name}.stub.md"
            stub_path.write_text(
                make_stub(src_path, scene, "G15",
                          source_abs_path=str(src_path), prefixed_name=prefixed_name),
                encoding="utf-8")
            if frontmatter:
                inject_frontmatter(stub_path, frontmatter)
            rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                              "STUB_ONLY_G15_VSDX_BLIND", "vsdx+G15", src_size, stub_path.stat().st_size,
                              "vsdx 转 PDF 后 markitdown 0 字节,永久 stub")
            log_action(rec)
            return rec
        md_path = target_dir / f"{prefixed_name}.md"
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        md_path.write_text(md_text, encoding="utf-8")
        stub_path.write_text(
            make_stub(src_path, scene, "G16", density,
                      source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        fm_status = "skipped"
        if frontmatter:
            fm_status = inject_frontmatter(md_path, frontmatter)
        # 清理临时 PDF(中间产物,不入库)
        try:
            pdf_path.unlink()
        except OSError:
            pass
        rec = make_record(src_path, norm_path(md_path.relative_to(REPO)),
                          "INGESTED_MD", "vsdx+G16", src_size, md_path.stat().st_size,
                          f"vsdx 转 PDF + markitdown,三件共存,密度 {density:.1%},frontmatter={fm_status}",
                          char_density=density)
        log_action(rec)
        return rec

    # binary 转 markdown(G15/G16/G18 分流)
    if ext in BINARY_EXTS:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_BINARY", "v0.2-plan-routed",
                               src_size, None, f"[dry-run] markitdown → G15/G16/G18 分流")
        md_engine = get_md_engine(md_engine_holder)
        # v0.2 阶段 4 步骤 4.4:.odt/.ods/.odp markitdown 异常时降级 G15 永久 stub
        # (plan §7.3 步骤 4.4 "失败则降级 G15 永久 stub" 语义;其他 binary 类型保持 ERROR_MARKITDOWN_FAILED)
        ODF_EXTS = {".odt", ".ods", ".odp"}
        try:
            result = md_engine.convert(str(src_path))
            md_text = result.text_content or ""
        except Exception as e:
            if ext in ODF_EXTS:
                target_dir.mkdir(parents=True, exist_ok=True)
                stub_path = target_dir / f"{prefixed_name}.stub.md"
                stub_path.write_text(
                    make_stub(src_path, scene, "G15",
                              source_abs_path=str(src_path), prefixed_name=prefixed_name),
                    encoding="utf-8")
                stub_extra = (f"\n- odf_status: failed_markitdown_no_odf_converter\n"
                             f"- 降级原因: markitdown 当前版本未带 ODF converter(.odt/.ods/.odp);永久 stub\n"
                             f"- 修复方案: 装 markitdown 的 odf extra(若未来版本提供)或装 odfpy + 自行扩展 converter\n"
                             f"- markitdown 异常: {e}\n")
                with open(stub_path, "a", encoding="utf-8") as f:
                    f.write(stub_extra)
                shutil.copy2(src_path, target_src)
                if frontmatter:
                    inject_frontmatter(stub_path, frontmatter)
                rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                                  "STUB_ONLY_ODF_NO_CONVERTER", "odf+G15",
                                  src_size, stub_path.stat().st_size,
                                  "odf 降级:markitdown 未带 ODF converter,永久 stub")
                log_action(rec)
                return rec
            rec = make_record(src_path, target_rel, "ERROR_MARKITDOWN_FAILED", "v0.2-plan-routed",
                              src_size, None, f"markitdown 异常: {e}")
            log_action(rec)
            return rec

        char_count = len(md_text)
        density = char_count / src_size if src_size > 0 else 0.0
        target_dir.mkdir(parents=True, exist_ok=True)

        if char_count == 0:
            stub_path = target_dir / f"{prefixed_name}.stub.md"
            stub_path.write_text(
                make_stub(src_path, scene, "G15", source_abs_path=str(src_path), prefixed_name=prefixed_name),
                encoding="utf-8")
            shutil.copy2(src_path, target_src)
            if frontmatter:
                inject_frontmatter(stub_path, frontmatter)
            rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                              "STUB_ONLY_G15", "G15", src_size, stub_path.stat().st_size,
                              "扫描类:markitdown 0 字节,永久 stub", char_density=density)
            log_action(rec)
            return rec

        if density < DENSITY_THRESHOLD and char_count < CHAR_COUNT_THRESHOLD:
            va_status, va_paths, va_raw = (extract_pptx_assets(src_path, target_dir)
                                           if ext == ".pptx" else (None, None, None))
            stub_path = target_dir / f"{prefixed_name}.stub.md"
            stub_path.write_text(
                make_stub(src_path, scene, "G18", density, char_count,
                          source_abs_path=str(src_path), prefixed_name=prefixed_name,
                          vision_assets=va_paths, vision_assets_extraction=va_status,
                          vision_assets_raw_count=va_raw),
                encoding="utf-8")
            shutil.copy2(src_path, target_src)
            if frontmatter:
                inject_frontmatter(stub_path, frontmatter)
            rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                              "STUB_ONLY_G18", "G18", src_size, stub_path.stat().st_size,
                              f"R4-A 结构性稀薄 密度 {density:.1%} 字符 {char_count}", char_density=density)
            log_action(rec)
            return rec

        # G16 三件共存
        md_path = target_dir / f"{prefixed_name}.md"
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        md_path.write_text(md_text, encoding="utf-8")

        # v0.2 阶段 4 步骤 4.2:.docx 嵌入表用 python-docx 抽取,append 到 .md 末尾作为补充段
        # (markitdown 转 .docx 表格常出空骨架行 + 合并单元格错位,python-docx 抽取更稳;
        #  两份共存让 LLM 检索时多一个命中)
        docx_tables = extract_docx_tables(src_path) if ext == ".docx" else []
        if docx_tables:
            with open(md_path, "a", encoding="utf-8") as f:
                f.write("\n\n## 嵌入表(python-docx 抽取版本)\n\n")
                f.write("> 由 ingest 阶段 4 步骤 4.2 自动抽取;若 markitdown 转出的同表已正常,本段可作 2nd 视角校对。\n\n")
                for i, t in enumerate(docx_tables, 1):
                    f.write(f"### 表 {i}\n\n{t}\n\n")

        # v0.2 阶段 4 步骤 4.1:.docx 嵌入图三闸过滤 + vision 注入占位段
        # (Claude 对话层后续 Read 解出的图 + Edit 替换占位段为真实 vision 转写;转完即删 .assets/)
        va_status, va_paths, va_raw = (extract_docx_assets(src_path, target_dir)
                                        if ext == ".docx" else (None, None, None))
        if va_status == "success" and va_paths:
            with open(md_path, "a", encoding="utf-8") as f:
                f.write("\n\n## 嵌入图 vision 转写\n\n")
                f.write(f"> **vision-pending**(ingest 阶段 4 步骤 4.1 标记)。三闸过滤后保留 {len(va_paths)} 张图;原 .docx 嵌入图共 {va_raw} 张。\n")
                f.write("> Claude 对话层后续 Read 下方各 asset → Edit 本段替换为真实转写;**不单建 .vision.md**(plan §7.3 假设 6)。\n>\n")
                f.write("> 待转 asset 清单:\n")
                for p in va_paths:
                    f.write(f"> - `{p}`\n")
                f.write("\n_本段在 Claude vision 注入后会被替换为真实的图描述 / OCR / 关系流向;.assets/ 目录在 vision 完成后自动删除。_\n")

        stub_path.write_text(
            make_stub(src_path, scene, "G16", density,
                      source_abs_path=str(src_path), prefixed_name=prefixed_name,
                      vision_assets=va_paths, vision_assets_extraction=va_status,
                      vision_assets_raw_count=va_raw),
            encoding="utf-8")
        shutil.copy2(src_path, target_src)
        # v0.2 frontmatter 注入到 .md 正文(stub 不注入 — stub 自身已有元数据头)
        fm_status = "skipped"
        if frontmatter:
            fm_status = inject_frontmatter(md_path, frontmatter)
        rec = make_record(src_path, norm_path(md_path.relative_to(REPO)),
                          "INGESTED_MD", "G16", src_size, md_path.stat().st_size,
                          f"三件共存,密度 {density:.1%},frontmatter={fm_status}"
                          f"{f',嵌入表 {len(docx_tables)} 个' if docx_tables else ''}"
                          f"{f',嵌入图 {len(va_paths)} 张(原 {va_raw})' if va_paths else ''}",
                          char_density=density)
        log_action(rec)
        return rec

    # text 类直接 cp + frontmatter(若 .md)
    if ext in TEXT_EXTS:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_TEXT", "v0.2-plan-routed",
                               src_size, None, f"[dry-run] 文本类直接 cp")
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, target_src)
        fm_status = "skipped"
        if ext == ".md" and frontmatter:
            fm_status = inject_frontmatter(target_src, frontmatter)
        rec = make_record(src_path, target_rel, "INGESTED_TEXT", "v0.2-plan-routed",
                          src_size, target_src.stat().st_size, f"文本类直接 cp,frontmatter={fm_status}")
        log_action(rec)
        return rec

    # 图像类:cp + vision-pending stub
    if ext in IMAGE_EXTS:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_VISION_IMAGE", "v0.2-plan-routed",
                               src_size, None, "[dry-run] 纯图像 → vision-pending stub")
        target_dir.mkdir(parents=True, exist_ok=True)
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        stub_path.write_text(
            make_stub(src_path, scene, "V_PENDING_IMAGE",
                      source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        shutil.copy2(src_path, target_src)
        if frontmatter:
            inject_frontmatter(stub_path, frontmatter)
        rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                          "VISION_PENDING_IMAGE", "V_PENDING_IMAGE", src_size, stub_path.stat().st_size,
                          "纯图像:vision 待转,源 + stub 二件共存")
        log_action(rec)
        return rec

    # 视频:cp + vision-pending stub
    if ext in VIDEO_EXTS:
        if dry_run:
            return make_record(src_path, target_rel, "DRY_RUN_VISION_VIDEO", "v0.2-plan-routed",
                               src_size, None, "[dry-run] 视频 → vision-pending stub")
        target_dir.mkdir(parents=True, exist_ok=True)
        stub_path = target_dir / f"{prefixed_name}.stub.md"
        stub_path.write_text(
            make_stub(src_path, scene, "V_PENDING_VIDEO",
                      source_abs_path=str(src_path), prefixed_name=prefixed_name),
            encoding="utf-8")
        shutil.copy2(src_path, target_src)
        if frontmatter:
            inject_frontmatter(stub_path, frontmatter)
        rec = make_record(src_path, norm_path(stub_path.relative_to(REPO)),
                          "VISION_PENDING_VIDEO", "V_PENDING_VIDEO", src_size, stub_path.stat().st_size,
                          "视频:vision 待转,源 + stub 二件共存")
        log_action(rec)
        return rec

    rec = make_record(src_path, None, "ERROR_UNSUPPORTED_EXT", None, src_size, None,
                      f"不支持的扩展名 {ext}")
    if not dry_run:
        log_action(rec)
    return rec


def execute_plan(plan_file: Path, dry_run: bool = False) -> dict:
    """v0.2 步骤 2.3:按 AI 给的 routing_plan.json 执行迁移。"""
    if not plan_file.is_file():
        sys.stderr.write(f"ERROR: plan 文件不存在 {plan_file}\n")
        sys.exit(2)
    # v0.2.2 C-2:utf-8-sig 兼容 BOM(PowerShell Out-File 默认带 BOM)+ 普通 UTF-8;无副作用
    plan = json.loads(plan_file.read_text(encoding="utf-8-sig"))
    items = plan.get("items", [])
    if not items:
        sys.stderr.write(f"ERROR: plan 中没有 items\n")
        sys.exit(2)

    # v0.2.2 C-1:schema 校验下沉到 _validate_plan_item_paths(per-item,失败转 ERROR_INVALID_PLAN_ITEM,
    # 不再 sys.exit;单 item bad 不阻塞其他 items 处理)

    md_engine_holder = [None]
    log_records = load_ingest_log()
    results = []
    print(f"# execute-plan: {len(items)} items {'(DRY-RUN)' if dry_run else ''}")
    print(f"# AI 判断摘要: {plan.get('ai_judgment_summary', '(未提供)')}")
    if not dry_run:
        print(f"# log: {INGEST_LOG.relative_to(REPO).as_posix()}")

    for i, item in enumerate(items, 1):
        # v0.2.1 P0-2:路径边界校验在每个 item 上单独执行,失败转 ERROR_INVALID_PLAN_ITEM 不中断其他 items
        try:
            _validate_plan_item_paths(item)
        except ValueError as e:
            src_abs = item.get("src_abs", "(unknown)")
            rec = make_record(
                Path(src_abs) if isinstance(src_abs, str) else Path("(unknown)"),
                None, "ERROR_INVALID_PLAN_ITEM", "v0.2.1-P0-2-validation",
                0, None, f"plan items[{i-1}] 路径边界校验失败: {e}",
            )
            results.append(rec)
            print(f"[{i}/{len(items)}] ERROR_INVALID_PLAN_ITEM: {Path(src_abs).name if isinstance(src_abs, str) else src_abs}")
            print(f"    reason: {e}")
            if not dry_run:
                log_action(rec)
            continue

        rec = process_file_with_explicit_target(item, dry_run, md_engine_holder,
                                                 incremental=True, log_records=log_records)
        results.append(rec)
        action = rec["action"]
        name = Path(rec["source_abs_path"]).name
        print(f"[{i}/{len(items)}] {action}: {name}")
        if rec.get("target_rel_path"):
            print(f"    → {rec['target_rel_path']}")
        if rec.get("notes"):
            print(f"    notes: {rec['notes']}")

    # 汇总
    stats = defaultdict(int)
    for r in results:
        stats[r["action"]] += 1
    print()
    print(f"# ✅ 完成: " + " / ".join(f"{a}={n}" for a, n in sorted(stats.items())))

    if not dry_run:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        exec_log = REPO / "logs" / f"ingest_executed_{ts}.jsonl"
        exec_log.parent.mkdir(parents=True, exist_ok=True)
        with open(exec_log, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"# 执行明细: {exec_log.relative_to(REPO)}")

    return {"items": results, "stats": dict(stats)}


# ====================== main: 子命令分发 ======================


def main():
    parser = argparse.ArgumentParser(description="knowledge-base ingest pipeline (v0.2 AI 语义路由)")
    sub = parser.add_subparsers(dest="mode", required=True)

    scan_p = sub.add_parser("scan-only", help="扫源目录,输出 routing_request.json,不做路由判断")
    scan_p.add_argument("src_dir", type=Path)
    scan_p.add_argument("--output", type=Path, default=REPO / "logs" / "routing_request.json")

    exec_p = sub.add_parser("execute-plan", help="按 AI 给的 routing_plan.json 执行迁移 + frontmatter 注入")
    exec_p.add_argument("plan_file", type=Path)
    exec_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.mode == "scan-only":
        scan_and_write_request(args.src_dir, args.output)
    elif args.mode == "execute-plan":
        execute_plan(args.plan_file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
