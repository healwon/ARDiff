#!/usr/bin/env python3
"""Check whether the Java methods changed by a commit are semantically equivalent, using ARDiff.

For every method whose code changed it builds an oldV/newV pair (the method plus the same-class
helpers and fields it uses), runs ARDiff (debug mode, per-iteration snapshots), and reports
EQUIVALENT / NOT EQUIVALENT / UNKNOWN. For NOT EQUIVALENT it explains the semantic difference
from ARDiff's logs (see semdiff.py): counterexample, differing symbolic paths, concrete runs.

examples:
  commit_check.py                              # HEAD vs HEAD^ in the current repo
  commit_check.py --repo ~/proj --commit abc123
  commit_check.py --range main..feature
  commit_check.py --worktree                   # uncommitted changes vs HEAD
  commit_check.py --patch fix.diff --base HEAD
  commit_check.py --old A.java --new B.java    # two files, no git
  commit_check.py ... --no-run                 # only build pairs and report what would run

output (default ./ardiff-commit-report/): report.html, report.md, report.json, viewer.html, pairs/
"""
import argparse, difflib, html, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFINEMENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import javasrc  # noqa: E402
import semdiff  # noqa: E402
import semview  # noqa: E402

JAVA_PRIMS = semdiff.JAVA_PRIMS
PRIM_ARRAYS = {t + "[]" for t in JAVA_PRIMS}


# ------------------------------------------------------------------ collecting file versions
def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and p.returncode:
        sys.exit(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


def show(repo, ref, path):
    p = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def changed_java(repo, base, head=None, cached=False):
    """[(old_path, new_path, status)] for .java files between base and head (head None = working tree/index)."""
    args = ["diff", "--name-status", "-M"] + (["--cached"] if cached else []) + [base] + ([head] if head else [])
    out = git(repo, *args, "--", "*.java")
    res = []
    for line in out.splitlines():
        parts = line.split("\t")
        st = parts[0][0]
        if st == "R":
            res.append((parts[1], parts[2], "R"))
        elif st in "MAD":
            res.append((parts[1], parts[1], st))
    return res


def versions_from_git(a):
    repo = os.path.abspath(a.repo)
    if a.range:
        base, head = a.range.split("..", 1)
        head = head or "HEAD"
        files = changed_java(repo, base, head)
        get_new = lambda p: show(repo, head, p)
        label = f"{base}..{head}"
    elif a.worktree or a.staged:
        base = "HEAD"
        files = changed_java(repo, base, cached=a.staged)
        if a.staged:
            get_new = lambda p: show(repo, "", p)       # ":path" = index
        else:
            get_new = lambda p: open(os.path.join(repo, p)).read() if os.path.exists(os.path.join(repo, p)) else None
        label = "staged vs HEAD" if a.staged else "working tree vs HEAD"
    else:
        head = a.commit or "HEAD"
        parents = git(repo, "rev-list", "--parents", "-n", "1", head).split()
        base = parents[1] if len(parents) > 1 else git(repo, "hash-object", "-t", "tree", "/dev/null").strip()
        files = changed_java(repo, base, head)
        get_new = lambda p: show(repo, head, p)
        subj = git(repo, "log", "-1", "--format=%h %s", head).strip()
        label = subj
    out = []
    for old_p, new_p, st in files:
        out.append({"path": new_p, "old_path": old_p, "status": st,
                    "old": None if st == "A" else show(repo, base, old_p),
                    "new": None if st == "D" else get_new(new_p)})
    return label, out


def versions_from_patch(a, work):
    repo = os.path.abspath(a.repo)
    patch = os.path.abspath(a.patch)
    text = open(patch).read()
    paths = []
    for m in re.finditer(r"^diff --git a/(\S+) b/(\S+)", text, re.M):
        if m.group(2).endswith(".java"):
            paths.append((m.group(1), m.group(2)))
    if not paths:
        for m in re.finditer(r"^\+\+\+ (?:b/)?(\S+)", text, re.M):
            if m.group(1).endswith(".java"):
                paths.append((m.group(1), m.group(1)))
    tree = os.path.join(work, "patch-tree")
    shutil.rmtree(tree, ignore_errors=True)
    os.makedirs(tree)
    for old_p, _ in paths:
        src = show(repo, a.base, old_p)
        if src is not None:
            os.makedirs(os.path.dirname(os.path.join(tree, old_p)) or tree, exist_ok=True)
            open(os.path.join(tree, old_p), "w").write(src)
    # stop git from finding an enclosing repo (out dir is often inside one), so the patch applies to `tree`
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(tree))
    p = subprocess.run(["git", "apply", "--verbose", "--include=*.java", patch], cwd=tree, capture_output=True, text=True, env=env)
    if "Skipped patch" in p.stderr:
        sys.exit(f"patch paths did not match files under {tree}: {p.stderr.strip()}")
    if p.returncode:
        sys.exit(f"patch does not apply on {a.base}: {p.stderr.strip()}")
    out = []
    for old_p, new_p in paths:
        newf = os.path.join(tree, new_p)
        out.append({"path": new_p, "old_path": old_p, "status": "M",
                    "old": show(repo, a.base, old_p),
                    "new": open(newf).read() if os.path.exists(newf) else None})
    return f"{os.path.basename(patch)} on {a.base}", out


def versions_from_files(a):
    # two standalone files usually have different class names (e.g. oldV/newV): match methods by signature only
    return f"{a.old} → {a.new}", [{"path": a.new, "old_path": a.old, "status": "M", "ignore_class": True,
                                   "old": open(a.old).read(), "new": open(a.new).read()}]


# ------------------------------------------------------------------ method pairing
def methods_by_key(src, ignore_class=False):
    if src is None:
        return {}, {}
    classes = javasrc.parse(src)
    return ({(m.signature if ignore_class else m.key): (m, c) for c in classes for m in c.methods},
            {c.name: c for c in classes})


def helper_closure(method, cls):
    """Same-class methods transitively called from `method` (by simple name)."""
    by_name = {}
    for m in cls.methods:
        by_name.setdefault(m.name, []).append(m)
    seen, todo, out = {method.key}, [method], []
    while todo:
        cur = todo.pop()
        for n in javasrc.called_names(cur):
            for h in by_name.get(n, []):
                if h.key not in seen:
                    seen.add(h.key); out.append(h); todo.append(h)
    return out


def imports_of(src):
    return [l.strip() for l in src.splitlines() if re.match(r"\s*import\s+[\w.*]+\s*;", l)]


def wrap(src, method, cls, new_name, pkg):
    helpers = helper_closure(method, cls)
    fields = []
    for m in [method] + helpers:
        for f in javasrc.referenced_fields(m, cls):
            if f not in fields:
                fields.append(f)

    def rename(t):
        return re.sub(r"(?<![\w$.])" + re.escape(cls.name) + r"\s*\.", new_name + ".", t)
    body = ["    " + rename(m.text) for m in [method] + helpers]
    # own package per pair: ARDiff compiles to <package>.instrumented.IoldVARDiff, so parallel runs must not share it
    lines = [f"package {pkg};"] + imports_of(src) + ["", f"public class {new_name} {{"]
    lines += ["    " + f for f in fields] + ([""] if fields else [])
    for b in body:
        lines += [b, ""]
    lines.append("}")
    return "\n".join(lines) + "\n", [h.key for h in helpers], fields


def preflight(m_old, m_new, fields_old, fields_new):
    issues, warns = [], []
    if m_old.ret.strip() == "void":
        issues.append("반환값이 없는(void) 메서드는 ARDiff가 비교할 수 없음")
    for t, n in m_old.params:
        if javasrc.norm_type(t) not in JAVA_PRIMS | PRIM_ARRAYS:
            issues.append(f"파라미터 `{t} {n}`: ARDiff는 원시 타입 위주로만 지원")
    if m_old.ret.strip() not in JAVA_PRIMS:
        warns.append(f"반환 타입 `{m_old.ret}`: 원시 타입이 아니면 판정이 부정확할 수 있음")
    for f in set(fields_old) | set(fields_new):
        if "static" not in f.split("=")[0] or "final" not in f.split("=")[0]:
            warns.append(f"필드 `{f}`: 상수가 아닌 필드는 기본값으로 초기화된 상태로 분석됨")
    if not m_old.is_static:
        warns.append("인스턴스 메서드: 기본 생성자로 만든 객체에서 호출하는 것으로 분석됨")
    return issues, warns


def compile_check(pair_dir, jhome):
    if not jhome:
        return None
    javac = os.path.join(jhome, "bin", "javac")
    out = os.path.join(pair_dir, ".compile")
    os.makedirs(out, exist_ok=True)
    p = subprocess.run(semdiff.pinned([javac, "-nowarn", "-d", out, "oldV.java", "newV.java"]), cwd=pair_dir,
                       capture_output=True, text=True, timeout=120)
    shutil.rmtree(out, ignore_errors=True)
    return None if p.returncode == 0 else p.stderr.strip()


def slug(s):
    return re.sub(r"[^\w.-]+", "_", s)[:80]


def build_pairs(files, out_dir, only=None, jhome=None, do_compile=True):
    pairs_dir = os.path.join(out_dir, "pairs")
    shutil.rmtree(pairs_dir, ignore_errors=True)
    os.makedirs(pairs_dir)
    entries = []
    for f in files:
        try:
            olds, old_classes = methods_by_key(f["old"], f.get("ignore_class", False))
            news, new_classes = methods_by_key(f["new"], f.get("ignore_class", False))
        except ValueError as ex:
            entries.append({"file": f["path"], "method": "(파일 전체)", "state": "skipped",
                            "reason": f"Java 소스를 해석하지 못함: {ex}"})
            continue
        # renamed class (e.g. `class A` -> `class B` in the same file): pair leftover methods by signature
        # when the signature is unique among the leftovers on both sides
        renamed = {}
        lo = [k for k in olds if k not in news]
        ln = [k for k in news if k not in olds]
        for ko in lo:
            sig = olds[ko][0].signature
            cand_n = [kn for kn in ln if news[kn][0].signature == sig]
            cand_o = [k for k in lo if olds[k][0].signature == sig]
            if len(cand_n) == 1 and len(cand_o) == 1:
                renamed[ko] = cand_n[0]
        for ko, kn in renamed.items():
            news[ko] = news.pop(kn)
        for key in sorted(set(olds) | set(news)):
            if only and not re.search(only, key):
                continue
            e = {"file": f["path"], "method": key if key not in renamed else f"{key} → {renamed[key]}"}
            if key not in olds or key not in news:
                e.update(state="skipped", reason="추가된 메서드" if key not in olds else "삭제된 메서드")
                entries.append(e); continue
            (mo, co), (mn, cn) = olds[key], news[key]
            if mo.text == mn.text:
                continue                                    # unchanged
            e["old_lines"] = [mo.start_line, mo.end_line]
            e["new_lines"] = [mn.start_line, mn.end_line]
            e["old_text"], e["new_text"] = mo.text, mn.text
            e["diff"] = "".join(difflib.unified_diff(mo.text.splitlines(True), mn.text.splitlines(True),
                                                     "old", "new", n=3))
            if mo.normalized() == mn.normalized():
                e["note"] = "주석·공백만 바뀜"            # still run ARDiff: the verdict should come from the tool
            pkg = f"ardiffcc.p{len(entries):03d}"
            old_src, helpers_o, fields_o = wrap(f["old"], mo, co, "oldV", pkg)
            new_src, helpers_n, fields_n = wrap(f["new"], mn, cn, "newV", pkg)
            issues, warns = preflight(mo, mn, fields_o, fields_n)
            e.update(helpers_old=helpers_o, helpers_new=helpers_n, warnings=warns,
                     params=[n for _, n in mo.params])
            if issues:
                e.update(state="skipped", reason="; ".join(issues)); entries.append(e); continue
            d = os.path.join(pairs_dir, f"{len(entries):03d}_{slug(key)}")
            os.makedirs(d)
            open(os.path.join(d, "oldV.java"), "w").write(old_src)
            open(os.path.join(d, "newV.java"), "w").write(new_src)
            e["dir"] = d
            err = compile_check(d, jhome) if do_compile else None
            if err:
                e.update(state="skipped", reason="감싼 클래스가 컴파일되지 않음 (다른 클래스나 필드에 의존)", compile_error=err[:2000])
            else:
                e["state"] = "ready"
            json.dump(e, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False, indent=1)
            entries.append(e)
    return entries


# ------------------------------------------------------------------ running + analysis
def run_ardiff(entries, a):
    dirs = [e["dir"] for e in entries if e["state"] == "ready"]
    if not dirs:
        return
    env = dict(os.environ)
    cmd = [os.path.join(REFINEMENT, "ardiff-workflow.sh"), "rundir", *dirs]
    print(f"[commit-check] running ARDiff on {len(dirs)} method(s)…", file=sys.stderr)
    subprocess.run(cmd, env=env, check=False)


def analyze(entries, a, jhome):
    for e in entries:
        if e["state"] != "ready":
            continue
        if a.no_run:
            e["state"] = "not-run"; continue
        rep = semdiff.analyze(e["dir"], a.z3, jhome, not a.no_z3, not a.no_exec, params=e.get("params"))
        e["state"] = "done"
        e["verdict"] = rep["verdict"]
        e["analysis"] = rep
        if rep.get("exec_verdict"):
            e["exec_verdict"] = rep["exec_verdict"]


# ------------------------------------------------------------------ reports
VCLASS = {"EQUIVALENT": "eq", "NOT EQUIVALENT": "neq", "UNKNOWN": "unk"}


def summary_counts(entries):
    c = {}
    for e in entries:
        k = e.get("verdict") if e["state"] == "done" else {"skipped": "SKIPPED", "not-run": "NOT RUN"}.get(e["state"], e["state"])
        c[k] = c.get(k, 0) + 1
    return c


def write_markdown(path, label, entries):
    L = [f"## ARDiff commit check: {label}", ""]
    L.append(" · ".join(f"{k} {v}" for k, v in summary_counts(entries).items()) or "바뀐 메서드 없음")
    L.append("")
    L.append("| 메서드 | 파일 | 결과 |")
    L.append("|---|---|---|")
    for e in entries:
        res = e.get("verdict") or e["state"]
        if e.get("exec_verdict"):
            res += " (실행 결과는 다름)"
        if e["state"] == "skipped":
            res = f"건너뜀: {e['reason']}"
        L.append(f"| `{e['method']}` | {e['file']} | {res} |")
    for e in entries:
        if e.get("analysis") and (e["verdict"] == "NOT EQUIVALENT" or e.get("exec_verdict")):
            L += ["", semdiff.to_markdown(e["analysis"], e["method"])]
    open(path, "w").write("\n".join(L) + "\n")


def h(s):
    return html.escape(str(s))


def diff_html(d):
    rows = []
    for line in d.splitlines():
        if line.startswith(("---", "+++")):
            continue
        cls = "add" if line.startswith("+") else "del" if line.startswith("-") else "hunk" if line.startswith("@@") else ""
        rows.append(f'<div class="dl {cls}">{h(line) or "&nbsp;"}</div>')
    return f'<div class="diff">{"".join(rows)}</div>'


def path_html(p, title):
    if not p:
        return f"<div class='muted'>{title}: 경로 정보 없음</div>"
    cons = "".join(f"<li><span class='ln'>L{c['line']}</span> <code>{h(c['src'])}</code><div class='expr'>{h(c['expr'])}</div></li>"
                   for c in p["constraints"])
    ret = p.get("ret")
    r = (f"<div class='ret'><span class='ln'>L{ret['line']}</span> <code>{h(ret['src'])}</code> → <b>{h(ret['expr'])}</b></div>"
         if ret else "")
    return f"<div class='path'><div class='ptitle'>{title}</div><ul>{cons or '<li class=muted>조건 없음</li>'}</ul>{r}</div>"


def neq_html(rep):
    out = []
    ex = rep.get("execution") or {}
    out.append("<details><summary class='muted'>근거 자세히 (실행 결과 표, 기호 경로, ARDiff 반례)</summary>")
    if ex.get("runs"):
        diff = [r for r in ex["runs"] if r["differs"]]
        same = len(ex["runs"]) - len(diff)
        params = ex.get("params", [])
        head = "".join(f"<th>{h(p)}</th>" for p in params)
        rows = "".join("<tr>" + "".join(f"<td>{h(r['inputs'].get(p))}</td>" for p in params) +
                       f"<td>{h(r['old'])}</td><td class='hl'>{h(r['new'])}</td><td class='muted'>{h(r['source'])}</td></tr>"
                       for r in diff[:30])
        out.append(f"<h4>실제 실행으로 확인한 차이 <span class='muted'>(입력 {len(ex['runs'])}개 중 {len(diff)}개 다름, {same}개 같음)</span></h4>")
        out.append(f"<div class='scroll'><table class='plain'><tr>{head}<th>old 결과</th><th>new 결과</th><th>입력 출처</th></tr>{rows}</table></div>"
                   if diff else "<p class='muted'>시도한 입력에서는 결과가 같았음. 아래 차이 영역은 추상화(UF) 때문에 생긴 것일 수 있음.</p>")
    elif ex.get("error"):
        out.append(f"<p class='muted'>실행 검증 건너뜀: {h(ex['error'])}</p>")
    ra = rep.get("regions")
    if ra:
        out.append(f"<h4>차이 영역 <span class='muted'>(old 경로 {ra['n_old']}개 × new 경로 {ra['n_new']}개 중 조건이 겹치는데 반환값이 다를 수 있는 쌍 {len(ra['regions'])}개"
                   + (f", 판정 불가 {ra['unknown']}개" if ra["unknown"] else "") + ")</span></h4>")
        for r in ra["regions"][:12]:
            op = rep["old_paths"][r["old"]] if r["old"] < len(rep.get("old_paths", [])) else None
            np_ = rep["new_paths"][r["new"]] if r["new"] < len(rep.get("new_paths", [])) else None
            w = ", ".join(f"{k} = {v}" for k, v in r["witness"].items()) or "(입력 없음)"
            out.append(f"<div class='region'><div class='wit'>예시 입력: <code>{h(w)}</code> → old <b>{h(r['ret_old'])}</b> / new <b class='hl'>{h(r['ret_new'])}</b></div>"
                       f"<div class='pp'>{path_html(op, 'old 경로 #' + str(r['old']))}{path_html(np_, 'new 경로 #' + str(r['new']))}</div></div>")
        if len(ra["regions"]) > 12:
            out.append(f"<p class='muted'>외 {len(ra['regions']) - 12}개는 report.json 참고</p>")
    ce = rep.get("counterexample")
    if ce:
        out.append(f"<p class='muted'>ARDiff가 찾은 반례: <code>{h(ce['inputs'])}</code>, old 반환 {h(ce['ret_old'])}"
                   + (f". 이 반례는 아직 추상화된 공통 코드(UF {len(ce['ufs'])}개)의 임의 값에 기대고 있어 실제 실행 결과와 다를 수 있음." if ce["uf_dependent"] else ".")
                   + "</p>")
    out.append("</details>")
    for n in rep.get("notes", []):
        out.append(f"<p class='muted'>참고: {h(n)}</p>")
    return "".join(out)


CSS = """
:root{--bg:#f5f6f8;--panel:#fff;--fg:#1a2130;--muted:#5e6879;--rule:#d8dde6;--eq:#23824f;--neq:#bf3a2b;--unk:#b07a12;
--add:#e3f4e8;--del:#fbe6e3;--hl:#bf3a2b;--sem:#6b3fb3;--semsoft:#efe6fb;--sans:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11151c;--panel:#192029;--fg:#e2e7ef;--muted:#98a2b3;--rule:#2b3340;
--eq:#4fbf82;--neq:#ec6e5f;--unk:#e0b04a;--add:#173323;--del:#3d1d1a;--hl:#ec6e5f;--sem:#b892f0;--semsoft:#2e2342;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#11151c;--panel:#192029;--fg:#e2e7ef;--muted:#98a2b3;--rule:#2b3340;--eq:#4fbf82;--neq:#ec6e5f;--unk:#e0b04a;
--add:#173323;--del:#3d1d1a;--hl:#ec6e5f;--sem:#b892f0;--semsoft:#2e2342;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;line-height:1.55}
.wrap{max-width:1100px;margin:0 auto;padding-inline:16px;padding-block:24px 56px;display:grid;gap:16px}
h1{font-size:20px;margin:0}h3{font-size:15px;margin:0;font-family:var(--mono);word-break:break-all}h4{font-size:13.5px;margin:14px 0 6px}
code,.mono{font-family:var(--mono);font-size:12.5px}.muted{color:var(--muted)}
.counts{display:flex;flex-wrap:wrap;gap:8px}.chip{font-family:var(--mono);font-size:12px;font-weight:600;padding:1px 9px;border-radius:99px;border:1.5px solid currentColor;white-space:nowrap}
.eq{color:var(--eq)}.neq{color:var(--neq)}.unk,.skip,.notrun{color:var(--unk)}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;min-width:0}
.card.neq{border-left:4px solid var(--neq)}.card.eq{border-left:4px solid var(--eq)}
.head{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;justify-content:space-between}
.diff{font-family:var(--mono);font-size:12px;border:1px solid var(--rule);border-radius:6px;overflow-x:auto;margin-top:10px}
.dl{white-space:pre;padding:0 10px}.dl.add{background:var(--add)}.dl.del{background:var(--del)}.dl.hunk{color:var(--muted)}
table.plain{border-collapse:collapse;font-size:13px}.plain td,.plain th{border-bottom:1px solid var(--rule);padding:4px 10px;text-align:left;font-family:var(--mono);font-size:12px}
.plain th{font-family:var(--sans);font-weight:500;color:var(--muted)}details{margin-top:8px}summary{cursor:pointer}.hl{color:var(--hl);font-weight:600}.scroll{overflow-x:auto}
.region{border:1px solid var(--rule);border-radius:6px;padding:8px 10px;margin-bottom:8px}.wit{margin-bottom:6px}
.pp{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}@media(max-width:760px){.pp{grid-template-columns:minmax(0,1fr)}}
.path ul{margin:4px 0;padding-left:16px}.path li{margin:2px 0}.ptitle{font-size:12px;color:var(--muted)}
.expr{font-family:var(--mono);font-size:11.5px;color:var(--muted);word-break:break-all}.ln{font-family:var(--mono);font-size:11px;color:var(--muted)}
.ret{font-size:12.5px;word-break:break-all}a{color:inherit}
"""


def write_html(path, label, entries, viewer_ok):
    counts = summary_counts(entries)
    chips = "".join(f"<span class='chip {VCLASS.get(k, 'skip')}'>{h(k)} {v}</span>" for k, v in counts.items())
    cards = []
    viewer_names = [os.path.basename(e["dir"]) for e in entries if e.get("analysis") and e["analysis"].get("iterations")]
    for e in entries:
        v = e.get("verdict") if e["state"] == "done" else {"skipped": "SKIPPED", "not-run": "NOT RUN"}.get(e["state"], e["state"])
        vc = VCLASS.get(v, "skip")
        rep = e.get("analysis") or {}
        meta = []
        if rep.get("iterations"):
            meta.append(f"refinement iteration {rep['iterations']}")
            if viewer_ok and os.path.basename(e["dir"]) in viewer_names:
                meta.append(f"<a href='viewer.html#b{viewer_names.index(os.path.basename(e['dir']))}'>refinement 과정 보기</a>")
        if e.get("reason"):
            meta.append(h(e["reason"]))
        if e.get("note"):
            meta.append(h(e["note"]))
        if rep.get("reason"):
            meta.append("이유: " + h(rep["reason"]))
        body = ""
        if e.get("dir") and os.path.exists(os.path.join(e["dir"], "oldV.java")):
            otext = open(os.path.join(e["dir"], "oldV.java")).read()
            ntext = open(os.path.join(e["dir"], "newV.java")).read()
        else:
            otext, ntext = e.get("old_text"), e.get("new_text")
        if otext is not None and ntext is not None:
            show_sem = v == "NOT EQUIVALENT" or e.get("exec_verdict")
            body += semview.render(otext, ntext, rep if show_sem else None, uid=f"sv{len(cards)}")
        elif e.get("diff"):
            body += diff_html(e["diff"])
        for w in e.get("warnings", []):
            body += f"<p class='muted'>주의: {h(w)}</p>"
        if e.get("compile_error"):
            body += f"<details><summary class='muted'>컴파일 오류</summary><pre class='mono'>{h(e['compile_error'])}</pre></details>"
        if v == "NOT EQUIVALENT" or e.get("exec_verdict"):
            body += neq_html(rep)
        elif v == "UNKNOWN" and rep.get("execution", {}).get("runs"):
            body += f"<p class='muted'>실제 실행: 입력 {len(rep['execution']['runs'])}개에서 old/new 결과가 모두 같았음 (동등하다는 증명은 아님)</p>"
        extra = "<span class='chip neq'>실행 결과 다름</span>" if e.get("exec_verdict") else ""
        cards.append(f"<section class='card {vc}{' neq' if e.get('exec_verdict') else ''}'><div class='head'><h3>{h(e['method'])}</h3><span>{extra} <span class='chip {vc}'>{h(v)}</span></span></div>"
                     f"<div class='muted'>{h(e['file'])}{' · ' if meta else ''}{' · '.join(meta)}</div>{body}</section>")
    page = f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARDiff Commit Check</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>{CSS}{semview.CSS}</style>
<div class="wrap">
<header><h1>ARDiff Commit Check</h1><div class="muted">{h(label)}</div></header>
<div class="counts">{chips or "<span class='muted'>바뀐 메서드 없음</span>"}</div>
{''.join(cards)}
</div>"""
    open(path, "w").write(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--commit", help="commit to check against its first parent (default HEAD)")
    src.add_argument("--range", help="BASE..HEAD")
    src.add_argument("--worktree", action="store_true", help="uncommitted changes vs HEAD")
    src.add_argument("--staged", action="store_true", help="staged changes vs HEAD")
    src.add_argument("--patch", help="unified diff file, applied on --base")
    src.add_argument("--old", help="old .java file (use with --new)")
    ap.add_argument("--new")
    ap.add_argument("--base", default="HEAD", help="base ref for --patch (default HEAD)")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", default="ardiff-commit-report")
    ap.add_argument("--only", help="regex on Class.method(sig) to limit methods")
    ap.add_argument("--no-run", action="store_true", help="build pairs only, do not run ARDiff")
    ap.add_argument("--no-compile-check", action="store_true")
    ap.add_argument("--no-z3", action="store_true", help="skip difference-region analysis")
    ap.add_argument("--no-exec", action="store_true", help="skip concrete runs of old/new")
    ap.add_argument("--z3"); ap.add_argument("--java-home")
    ap.add_argument("--cores"); ap.add_argument("--jobs"); ap.add_argument("--timeout"); ap.add_argument("--heap")
    a = ap.parse_args()

    for k in ("cores", "jobs", "timeout", "heap"):      # shared with ardiff-workflow.sh and semdiff.pinned
        if getattr(a, k):
            os.environ[k.upper()] = str(getattr(a, k))
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    if a.old:
        if not a.new:
            ap.error("--old needs --new")
        label, files = versions_from_files(a)
    elif a.patch:
        label, files = versions_from_patch(a, out)
    else:
        label, files = versions_from_git(a)

    jhome = semdiff.java_home(a.java_home)
    entries = build_pairs(files, out, a.only, jhome, not a.no_compile_check)
    print(f"[commit-check] {label}: {len(entries)} changed method(s), "
          f"{sum(e['state'] == 'ready' for e in entries)} runnable", file=sys.stderr)
    if not a.no_run:
        run_ardiff(entries, a)
    analyze(entries, a, jhome)

    run_dirs = [e["dir"] for e in entries if e.get("analysis", {}).get("iterations")]
    viewer_ok = False
    if run_dirs:
        p = subprocess.run([sys.executable, os.path.join(REFINEMENT, "build_viewer.py"), os.path.join(out, "viewer.html"), *run_dirs],
                           capture_output=True, text=True)
        viewer_ok = p.returncode == 0
    json.dump({"label": label, "entries": entries}, open(os.path.join(out, "report.json"), "w"),
              ensure_ascii=False, indent=1, default=str)
    write_markdown(os.path.join(out, "report.md"), label, entries)
    write_html(os.path.join(out, "report.html"), label, entries, viewer_ok)
    print(open(os.path.join(out, "report.md")).read())
    print(f"[commit-check] report: {os.path.join(out, 'report.html')}", file=sys.stderr)
    if any(e.get("verdict") == "NOT EQUIVALENT" or e.get("exec_verdict") for e in entries):
        sys.exit(2)


if __name__ == "__main__":
    main()
