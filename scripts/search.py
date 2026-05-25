"""search.py - knowledge-base ripgrep 包装器(≤200 行)
对应 CLAUDE.md 第 2 节工作流步骤 3-4(ripgrep + 上下文)。LLM(Claude Code 会话)做步骤 0-1-2-5-6。
用法(v0.2 PARA 重构):
  python scripts/search.py --terms "词1,词2,词3" [--scope projects|areas|resources|archives|all]
                          [--project <项目名>] [--context 20] [--max-files 8] [--no-stub] [--regex]

scope 语义(v0.2):
  - projects(默认)/ areas / resources:对应 corpus/01-projects / 02-areas / 03-resources
  - archives:对应 corpus/04-archives(用户显式打开才扫,默认不在 all 内)
  - all:全扫 P+A+R(默认不含 archives,匹配 CLAUDE.md 5 节"跨corpus盘点"语义)

--project <名> 限定到 corpus/01-projects/<名>/(精度提升,scope 自动隐含 projects)。
默认走 --fixed-strings 字面匹配;需正则用 --regex。
rg 路径解析:Windows 优先 tools/rg.exe(bundled);其他平台或 bundled 不存在时 fallback 系统 PATH。
"""
import argparse, json, platform, shutil, subprocess, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# v0.2 PARA 重构:SCENE_MAP v0.1 → BUCKET_MAP v0.2
BUCKET_MAP = {
    "projects": "01-projects",
    "areas": "02-areas",
    "resources": "03-resources",
    "archives": "04-archives",
}
# all 默认不含 archives(沿 CLAUDE.md 5 节"跨corpus盘点"约定)
ALL_BUCKETS = ["projects", "areas", "resources"]
CORPUS = Path(__file__).resolve().parent.parent / "corpus"
REPO = CORPUS.parent

LLM_RULES = """## ⚠ stub 命中处理规则(LLM 必读)

`.stub.md` 是 binary 素材(docx/pdf/xlsx/pptx)的元数据卡片。**先读 stub 内"状态"字段判断类别**:

- **G16(三件共存:源 + stub + .md)**:正文已转 markdown,在同目录 `<同名>.md` 兄弟文件。
  - ✅ stub 仅作元数据索引,**优先读 .md 正文回答**;若 .md 未在本次命中而 stub 命中,需 grep 同目录 .md
  - 本场景**不触发** R2/stub 禁令
- **G15 / G18(永久 stub,无 .md)**:正文未入库。
  - ✅ 允许说: "该问题相关素材是 docx/pptx/pdf,正文未入库;文件位于 [源路径],建议直接打开查看"
  - ❌ 严禁说: "根据这次会议讨论了 X" / "根据这份文档,结论是 Y" / 任何对未入库正文内容的推断
  - 该规则同步于 tests/查询记录.md 预期风险 R2(docx/xlsx 转 md 基建缺失)
"""

def resolve_rg_path():
    """rg 路径解析:Windows 优先仓库内 tools/rg.exe(bundled,固定版本可复现),
    其他平台或 bundled 不存在时 fallback 系统 PATH 的 rg。都没有报错。
    返回 (path, source) — source 为 'bundled' 或 'system PATH'。"""
    # bundled 仅 Windows 适用(tools/rg.exe 是 Windows x86_64 二进制)
    if platform.system() == "Windows":
        repo_rg = REPO / "tools" / "rg.exe"
        if repo_rg.is_file():
            return str(repo_rg), "bundled"
    # 非 Windows 或 bundled 不存在 → 系统 PATH 的 rg
    sys_rg = shutil.which("rg")
    if sys_rg:
        return sys_rg, "system PATH"
    sys.stderr.write("ERROR: 未找到 ripgrep。\n")
    sys.stderr.write("  优先位置:tools/rg.exe(仅 Windows;仓库自带,推荐)\n")
    sys.stderr.write("  fallback:系统 PATH 中的 rg(macOS: brew install ripgrep / Linux: apt install ripgrep)\n")
    sys.stderr.write("  如果是 Windows 首次试用,执行 install.bat 或 install.ps1 验证仓库完整性。\n")
    sys.exit(2)


def parse_args():
    p = argparse.ArgumentParser(description="knowledge-base search (v0.2 PARA)")
    p.add_argument("--scope", default="projects",
                   help="PARA scope: projects(默认) / areas / resources / archives / all"
                        "(all=P+A+R,不含 archives;archives 需显式指定)")
    p.add_argument("--project", type=str, default=None,
                   help="限定到某个项目(corpus/01-projects/<名>/),scope 自动隐含 projects")
    p.add_argument("--terms", required=True, help="逗号分隔检索词列表")
    p.add_argument("--context", type=int, default=20)
    p.add_argument("--max-files", type=int, default=8)
    p.add_argument("--no-stub", action="store_true")
    p.add_argument("--regex", action="store_true",
                   help="启用 rg 正则模式(默认 --fixed-strings 字面匹配,对括号/星号/方括号等检索词安全)")
    p.add_argument("--deep", action="store_true",
                   help="包含 .shelved/** 与 .archive/**(默认排除);用于追溯过程材料/旧版本/素材(v0.3)")
    return p.parse_args()


def resolve_dirs(scope, project=None):
    """v0.2 PARA scope 解析。--project 优先级最高,scope 自动隐含 projects。"""
    if project is not None:
        proj_dir = CORPUS / BUCKET_MAP["projects"] / project
        if not proj_dir.is_dir():
            sys.stderr.write(f"ERROR: 项目 '{project}' 不存在于 corpus/01-projects/\n")
            sys.stderr.write(f"  可用项目:\n")
            projects_root = CORPUS / BUCKET_MAP["projects"]
            if projects_root.is_dir():
                for p in sorted(projects_root.iterdir()):
                    if p.is_dir():
                        sys.stderr.write(f"    - {p.name}\n")
            sys.exit(1)
        return [proj_dir]
    if scope == "all":
        return [CORPUS / BUCKET_MAP[k] for k in ALL_BUCKETS]
    if scope not in BUCKET_MAP:
        sys.stderr.write(f"ERROR: 未知 scope '{scope}' (须 projects/areas/resources/archives/all)\n")
        sys.exit(2)
    return [CORPUS / BUCKET_MAP[scope]]


def check_rg_proc(proc, terms, args):
    """rg returncode 三态:0 = 有命中,1 = 无命中(正常),>=2 = rg 真出错。
    >=2 时报错停,避免静默吞错当 0 命中(典型场景:正则模式下检索词语法错误)。"""
    if proc.returncode in (0, 1):
        return
    sys.stderr.write(f"\nERROR: ripgrep 出错 (returncode={proc.returncode})\n")
    sys.stderr.write(f"  检索词: {terms}\n")
    sys.stderr.write(f"  命令: {' '.join(repr(a) if ' ' in a else a for a in args)}\n")
    sys.stderr.write(f"  stderr:\n")
    for line in (proc.stderr or "").splitlines():
        sys.stderr.write(f"    {line}\n")
    sys.stderr.write(f"\n  提示: 默认走 --fixed-strings 字面匹配。"
                     f"若用 --regex 模式,检查正则语法;否则去掉 --regex 即可\n")
    sys.exit(2)


def run_rg(rg, terms, dirs, context, regex=False, no_stub=False, deep=False):
    """v0.2.1 P1-8: --no-stub 在 rg 参数层加 --glob '!*.stub.md',
    避免后处理过滤后 per_term_hits 与 files 计数不一致(误导 LLM 回退判断)。

    v0.3 阶段 3:默认 glob 加 !.shelved/**(沿用 !.archive/** 同款);--deep 时
    两个排除都不加,允许命中 .shelved/.archive 内容(追溯过程材料/旧版本/素材)。"""
    args = [rg, "--json", "-i", "-C", str(context),
            "--glob", "!.references.md"]
    if not deep:
        args.extend([
            "--glob", "!.shelved/**",   # v0.3 新增
            "--glob", "!.archive/**",   # v0.2.x 沿用
        ])
    if no_stub:
        args.extend(["--glob", "!*.stub.md"])
    if not regex:
        args.append("--fixed-strings")
    for t in terms:
        args.extend(["-e", t])
    args.extend([str(d) for d in dirs])
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    check_rg_proc(proc, terms, args)
    events = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def per_term_hits(rg, terms, dirs, regex=False, no_stub=False, deep=False):
    """v0.2.1 P1-8: 同 run_rg 透传 --no-stub,确保 per_term_hits 与 files 共享 glob。
    v0.3 阶段 3:同步 --deep 排除策略(默认排除 .shelved/.archive,--deep 包含)。"""
    hits = {}
    for t in terms:
        args = [rg, "-l", "-i",
                "--glob", "!.references.md"]
        if not deep:
            args.extend([
                "--glob", "!.shelved/**",   # v0.3 新增
                "--glob", "!.archive/**",   # v0.2.x 沿用
            ])
        if no_stub:
            args.extend(["--glob", "!*.stub.md"])
        if not regex:
            args.append("--fixed-strings")
        args.extend(["-e", t])
        args.extend([str(d) for d in dirs])
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
        check_rg_proc(proc, [t], args)
        hits[t] = sum(1 for l in proc.stdout.splitlines() if l.strip())
    return hits


def group(events):
    files, cur = {}, None
    for e in events:
        t = e.get("type")
        if t == "begin":
            cur = e["data"]["path"].get("text")
            if cur: files.setdefault(cur, [])
        elif t in ("match", "context") and cur:
            d = e["data"]
            files[cur].append((d.get("line_number", 0), d["lines"].get("text", "").rstrip("\n"), t == "match"))
        elif t == "end":
            cur = None
    return files


def to_rel(abs_path):
    try:
        return str(Path(abs_path).resolve().relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(abs_path).replace("\\", "/")


def render_text(path, lines):
    rel = to_rel(path)
    n = sum(1 for _, _, m in lines if m)
    blocks, cur, last = [], [], -10
    for ln, txt, m in lines:
        if ln - last > 1 and cur:
            blocks.append(cur); cur = []
        cur.append((ln, txt, m)); last = ln
    if cur: blocks.append(cur)
    omit = 0
    if n > 5:
        head, h = [], 0
        for b in blocks:
            head.append(b); h += sum(1 for _, _, m in b if m)
            if h >= 3: break
        tail, t = [], 0
        for b in reversed(blocks[len(head):]):
            tail.insert(0, b); t += sum(1 for _, _, m in b if m)
            if t >= 2: break
        omit = n - h - t
        if omit > 0: blocks = head + [None] + tail
    note = f",已截断:前 3 + 后 2,中间省略 {omit}" if omit > 0 else ""
    out = [f"### {rel}", f"({n} 处命中{note})\n", "```"]
    for i, b in enumerate(blocks):
        if i > 0: out.append("---")
        if b is None: out.append(f"... (省略 {omit} 处命中) ..."); continue
        for ln, txt, m in b:
            out.append(f"{'>>>' if m else '   '} L{ln:>5}: {txt}")
    out.append("```")
    return "\n".join(out)


def is_g16_stub(path):
    try:
        return "已转 markdown 正文" in Path(path).read_text(encoding="utf-8")
    except Exception:
        return False


def render_stub(path, lines, is_g16=False):
    rel = to_rel(path)
    matched = sorted({ln for ln, _, m in lines if m})
    label = ("**配套元数据**(三件共存,正文在同目录 .md)" if is_g16
             else "⚠ **正文未入库**(stub)")
    out = [f"### {rel}", f"{label},命中行号: {matched}\n"]
    try:
        content = Path(path).read_text(encoding="utf-8").rstrip()
        out += ["```markdown", content, "```"]
    except Exception as e:
        out.append(f"(读取失败: {e})")
    return "\n".join(out)


def main():
    args = parse_args()
    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    if not terms:
        sys.stderr.write("ERROR: --terms 为空\n")
        sys.exit(2)
    rg, rg_source = resolve_rg_path()
    dirs = resolve_dirs(args.scope, args.project)
    for d in dirs:
        if not d.is_dir():
            sys.stderr.write(f"ERROR: corpus 子目录不存在 {d}\n")
            sys.exit(2)
    # v0.3 阶段 3 步骤 3.2:默认排除 .shelved/.archive,显式提示用户如何追溯
    if not args.deep:
        print("# ℹ 默认检索已排除 .shelved/** 与 .archive/**;如需追溯过程材料/旧版本/素材,加 --deep 重跑")
    events = run_rg(rg, terms, dirs, args.context, regex=args.regex,
                    no_stub=args.no_stub, deep=args.deep)
    files = group(events)
    for p in list(files):
        if len(files[p]) > 200:
            files[p] = files[p][:200]
    # v0.2.1 P1-8: --no-stub 已在 rg 层过滤,这里 stubs 必为空集
    stubs = {p: l for p, l in files.items() if p.endswith(".stub.md")}
    texts = {p: l for p, l in files.items() if not p.endswith(".stub.md")}
    text_trim = stub_trim = False
    if len(texts) > args.max_files:
        texts = {k: texts[k] for k in list(texts)[:args.max_files]}
        text_trim = True
    if len(stubs) > args.max_files:
        stubs = {k: stubs[k] for k in list(stubs)[:args.max_files]}
        stub_trim = True
    if args.project:
        label = f"项目 '{args.project}'"
    elif args.scope == "all":
        label = "全扫 P+A+R(不含 archives)"
    else:
        label = f"{args.scope} ({BUCKET_MAP[args.scope]})"
    total = len(texts) + len(stubs)
    print("# 检索结果\n")
    print(f"- **scope**: {label}")
    print(f"- **检索词**: {' | '.join(terms)}  (匹配模式: {'regex' if args.regex else 'fixed-strings'})")
    print(f"- **rg 路径**: {rg}  (来源: {rg_source})")
    print(f"- **命中文件**: {total} (正文 {len(texts)} + stub {len(stubs)})\n")
    print("---\n")
    print(f"## 一、正文命中({len(texts)} 份)\n")
    if texts:
        for p, l in texts.items():
            print(render_text(p, l))
            print()
    else:
        print("(无)\n")
    is_g16_map = {p: is_g16_stub(p) for p in stubs}
    g16_n = sum(1 for v in is_g16_map.values() if v)
    other_n = len(stubs) - g16_n
    if g16_n and other_n:
        print(f"## 二、stub 命中({len(stubs)} 份:配套元数据 G16 共 {g16_n} + 正文未入库 G15/G18/其他 共 {other_n})\n")
    elif g16_n:
        print(f"## 二、stub 命中({len(stubs)} 份,**配套元数据**:三件共存,正文在同目录 .md)\n")
    else:
        print(f"## 二、stub 命中({len(stubs)} 份,⚠ **正文未入库**)\n")
    if stubs:
        for p, l in stubs.items():
            print(render_stub(p, l, is_g16_map[p]))
            print()
    else:
        print("(无)\n")
    print("## 三、未命中检索词\n")
    term_hits = per_term_hits(rg, terms, dirs, regex=args.regex,
                              no_stub=args.no_stub, deep=args.deep)
    zero_terms = [t for t, n in term_hits.items() if n == 0]
    if not zero_terms:
        print("— 本次所有检索词均有命中\n")
    else:
        for t in terms:
            n = term_hits[t]
            icon = "✅" if n > 0 else "❌"
            print(f"- {icon} `{t}`: {n} 份")
        print()
        print(f"⚠ **未命中检索词**: {' | '.join(zero_terms)}")
        if len(zero_terms) == len(terms):
            print(f"- 全部 {len(terms)} 个检索词均未命中,搜索范围: {', '.join(to_rel(str(d)) for d in dirs)}")
            print(f"- 建议: Claude Code 会话生成更宽泛同义词重试一次(对应 CLAUDE.md 步骤 6 回退判断);仍无果则告知用户'未找到相关内容',严禁编造\n")
        else:
            print(f"- 部分检索词无命中({len(zero_terms)}/{len(terms)});若关键概念未命中,Claude Code 会话考虑同义词替换重试\n")
    if text_trim or stub_trim:
        print("---\n## ⚠ 命中文件超 max-files 上限")
        if text_trim: print(f"- 正文命中超 {args.max_files},已截断")
        if stub_trim: print(f"- stub 命中超 {args.max_files},已截断")
        print(f"- 如需展开请加 `--max-files N`,或先收窄检索词\n")
    print("---\n" + LLM_RULES)


if __name__ == "__main__":
    main()
