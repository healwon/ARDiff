"""difftastic-style side-by-side view of old/new code with ARDiff's semantic difference on top.

Syntax layer : `difft --display json` (structural diff: aligned lines + changed tokens).
               Falls back to a difflib line/token diff when difftastic is not installed.
Semantic layer: "scenarios" = inputs where old and new return different values. A scenario coming from
               a difference region (semdiff.region_analysis) also carries the symbolic path taken on each
               side; those lines are marked, and the return line shows the value each version returns.
"""
import difflib, html, json, os, re, shutil, subprocess, tempfile

DIFFT_ENV = {"DFT_UNSTABLE": "yes"}
TOKEN = re.compile(r"[A-Za-z_$][\w$]*|\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|\S")


def find_difft():
    for c in (os.environ.get("DIFFT"), shutil.which("difft")):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _same_class(text):
    # oldV/newV differ only by name: give both the same 4-char name so the class line is not "changed"
    return re.sub(r"\b(?:oldV|newV)\b", "SAME", text)


def difft_rows(old_text, new_text):
    """[(lhs_line|None, rhs_line|None)], {line: [(start,end)]} for lhs and rhs (0-based lines, char offsets)."""
    exe = find_difft()
    if not exe:
        return None
    tmp = tempfile.mkdtemp(prefix="ardiff-difft-")
    try:
        a, b = os.path.join(tmp, "old.java"), os.path.join(tmp, "new.java")
        open(a, "w").write(_same_class(old_text)); open(b, "w").write(_same_class(new_text))
        p = subprocess.run([exe, "--display", "json", "--color", "never", a, b], capture_output=True, text=True,
                           env={**os.environ, **DIFFT_ENV}, timeout=60)
        j = json.loads(p.stdout)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n_old, n_new = len(old_text.splitlines()), len(new_text.splitlines())
    if j.get("status") == "unchanged" or "aligned_lines" not in j:
        return [(i, i) for i in range(max(n_old, n_new))], {}, {}
    lch, rch = {}, {}
    for chunk in j.get("chunks", []):
        for item in chunk:
            for side, store, lines in (("lhs", lch, old_text.splitlines()), ("rhs", rch, new_text.splitlines())):
                s = item.get(side)
                if not s:
                    continue
                ln = s["line_number"]
                line = lines[ln] if ln < len(lines) else ""
                raw = line.encode()
                for c in s.get("changes", []):   # difft offsets are bytes
                    st = len(raw[:c["start"]].decode(errors="ignore")); en = len(raw[:c["end"]].decode(errors="ignore"))
                    store.setdefault(ln, []).append((st, en))
    rows = [(l, r) for l, r in j["aligned_lines"] if (l is None or l < n_old) and (r is None or r < n_new)]
    return rows, lch, rch


def fallback_rows(old_text, new_text):
    a, b = old_text.splitlines(), new_text.splitlines()
    rows, lch, rch = [], {}, {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            rows += [(i1 + k, j1 + k) for k in range(i2 - i1)]
            continue
        n = max(i2 - i1, j2 - j1)
        for k in range(n):
            l = i1 + k if i1 + k < i2 else None
            r = j1 + k if j1 + k < j2 else None
            rows.append((l, r))
            if l is not None and r is not None:
                lt, rt = list(TOKEN.finditer(a[l])), list(TOKEN.finditer(b[r]))
                sm = difflib.SequenceMatcher(None, [t.group() for t in lt], [t.group() for t in rt], autojunk=False)
                for op, x1, x2, y1, y2 in sm.get_opcodes():
                    if op != "equal":
                        lch.setdefault(l, []).extend((t.start(), t.end()) for t in lt[x1:x2])
                        rch.setdefault(r, []).extend((t.start(), t.end()) for t in rt[y1:y2])
            else:
                if l is not None:
                    lch.setdefault(l, []).extend((t.start(), t.end()) for t in TOKEN.finditer(a[l]))
                if r is not None:
                    rch.setdefault(r, []).extend((t.start(), t.end()) for t in TOKEN.finditer(b[r]))
    return rows, lch, rch


def _code_html(line, spans, cls):
    if not spans:
        return html.escape(line) or " "
    out, pos = [], 0
    for st, en in sorted(spans):
        if st < pos:
            st = pos
        if en <= st:
            continue
        out.append(html.escape(line[pos:st]))
        out.append(f'<span class="{cls}">{html.escape(line[st:en])}</span>')
        pos = en
    out.append(html.escape(line[pos:]))
    return "".join(out) or " "


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def scenarios(rep):
    """Inputs where old and new differ, best evidence first."""
    out, seen = [], set()
    runs = (rep.get("execution") or {}).get("runs", [])
    run_by_inputs = {json.dumps(r["inputs"], sort_keys=True): r for r in runs}
    regions = (rep.get("regions") or {}).get("regions", [])
    aligned = (rep.get("regions") or {}).get("paths_aligned", True)
    for r in regions:
        key = json.dumps({k: r["witness"].get(k) for k in rep.get("params", r["witness"].keys())}, sort_keys=True)
        run = run_by_inputs.get(key)
        sc = {"inputs": r["witness"], "kind": "region", "old_path": r["old"], "new_path": r["new"],
              "ret_old": _fmt(run["old"] if run else r["ret_old"]), "ret_new": _fmt(run["new"] if run else r["ret_new"]),
              "confirmed": bool(run and run["differs"]), "refuted": bool(run and not run["differs"]),
              "aligned": aligned}
        seen.add(key)
        out.append(sc)
    for r in runs:
        key = json.dumps(r["inputs"], sort_keys=True)
        if r["differs"] and key not in seen:
            seen.add(key)
            out.append({"inputs": r["inputs"], "kind": "exec", "ret_old": r["old"], "ret_new": r["new"],
                        "confirmed": True, "refuted": False, "source": r["source"]})
    rank = lambda s: (0 if s["confirmed"] and s["kind"] == "region" else 1 if s["confirmed"] else 2 if not s["refuted"] else 3)
    out.sort(key=rank)
    return out[:40]


def _path_lines(path):
    """{pair_line(0-based): role} for one symbolic path: 'cond' or 'ret'."""
    if not path:
        return {}, None
    marks = {}
    for c in path["constraints"]:
        if c.get("pair_line"):
            marks[c["pair_line"] - 1] = "cond"
    ret = path.get("ret")
    rl = ret["pair_line"] - 1 if ret and ret.get("pair_line") else None
    if rl is not None:
        marks[rl] = "ret"
    return marks, rl


def render(old_text, new_text, rep=None, uid="v"):
    """HTML fragment: scenario picker + side-by-side diff. `rep` = semdiff report (optional)."""
    got = difft_rows(old_text, new_text)
    engine = "difftastic" if got else "difflib"
    rows, lch, rch = got or fallback_rows(old_text, new_text)
    a, b = old_text.splitlines(), new_text.splitlines()

    scs = scenarios(rep) if rep else []
    sc_data = []
    for k, s in enumerate(scs):
        d = {"i": k, "ret_old": s["ret_old"], "ret_new": s["ret_new"]}
        if s["kind"] == "region" and s.get("aligned", True):
            op = rep["old_paths"][s["old_path"]] if s["old_path"] < len(rep.get("old_paths", [])) else None
            np_ = rep["new_paths"][s["new_path"]] if s["new_path"] < len(rep.get("new_paths", [])) else None
            d["old"], d["oret"] = _path_lines(op)
            d["new"], d["nret"] = _path_lines(np_)
        sc_data.append(d)

    trs = []
    for l, r in rows:
        lcls = "chg" if l is not None and lch.get(l) else ""
        rcls = "chg" if r is not None and rch.get(r) else ""
        ltxt = _code_html(a[l], lch.get(l), "del") if l is not None else ""
        rtxt = _code_html(b[r], rch.get(r), "add") if r is not None else ""
        trs.append(
            f'<tr><td class="n">{"" if l is None else l + 1}</td>'
            f'<td class="c L {lcls}{" gap" if l is None else ""}" data-l="{"" if l is None else l}">{ltxt}<span class="val"></span></td>'
            f'<td class="n">{"" if r is None else r + 1}</td>'
            f'<td class="c R {rcls}{" gap" if r is None else ""}" data-r="{"" if r is None else r}">{rtxt}<span class="val"></span></td></tr>')

    picker = ""
    if scs:
        btns = []
        for k, s in enumerate(scs):
            inp = ", ".join(f"{n} = {_fmt(v)}" for n, v in s["inputs"].items()) or "(입력 없음)"
            tag = ("실행 확인" if s["confirmed"] else "실행 결과는 같음 (추상화로 인한 차이)" if s["refuted"] else "기호 분석")
            path = (f"경로 old #{s['old_path']} · new #{s['new_path']}" if s["kind"] == "region"
                    else f"입력 출처: {s.get('source', '')}")
            btns.append(
                f'<button type="button" class="sc{" weak" if s["refuted"] else ""}" data-sc="{k}">'
                f'<code>{html.escape(inp)}</code> <span class="arrow">old <b>{html.escape(_fmt(s["ret_old"]))}</b> → new '
                f'<b class="hl">{html.escape(_fmt(s["ret_new"]))}</b></span>'
                f'<span class="tag">{html.escape(tag)} · {html.escape(path)}</span></button>')
        picker = (f'<div class="scs"><div class="sch">결과가 달라지는 입력 {len(scs)}개 · 고르면 각 버전이 지나는 줄과 반환값을 코드에 표시</div>'
                  f'{"".join(btns)}</div>')
    legend = ('<div class="lg"><span><i class="k del"></i>삭제된 토큰</span><span><i class="k add"></i>추가된 토큰</span>'
              + ('<span><i class="k cond"></i>선택한 입력이 지나는 조건</span><span><i class="k ret"></i>반환 줄</span>' if scs else "")
              + f'<span class="eng">구문 비교: {engine}</span></div>')
    script = ""
    if scs:
        script = f"""<script>(function(){{
var D={json.dumps(sc_data)}, root=document.getElementById("{uid}");
function pick(k){{
  var s=D[k];
  root.querySelectorAll(".sc").forEach(function(b){{b.setAttribute("aria-pressed", b.dataset.sc==k?"true":"false");}});
  root.querySelectorAll("td.c").forEach(function(td){{td.classList.remove("cond","ret");td.querySelector(".val").textContent="";}});
  function mark(side, lines, retLine, val){{
    if(!lines) return;
    Object.keys(lines).forEach(function(ln){{var td=root.querySelector('td.'+side+'[data-'+side.toLowerCase()+'="'+ln+'"]'); if(td) td.classList.add(lines[ln]);}});
    if(retLine!==null&&retLine!==undefined){{var td=root.querySelector('td.'+side+'[data-'+side.toLowerCase()+'="'+retLine+'"]'); if(td) td.querySelector(".val").textContent="⇒ "+val;}}
  }}
  mark("L", s.old, s.oret, s.ret_old); mark("R", s.new, s.nret, s.ret_new);
}}
root.querySelectorAll(".sc").forEach(function(b){{b.addEventListener("click",function(){{pick(+b.dataset.sc);}});}});
pick(0);
}})();</script>"""
    return (f'<div class="sv" id="{uid}">{picker}<div class="svt"><table>'
            f'<tr><th></th><th>old</th><th></th><th>new</th></tr>{"".join(trs)}</table></div>{legend}</div>{script}')


CSS = """
.sv{margin-top:10px;display:grid;gap:8px}
.svt{overflow-x:auto;border:1px solid var(--rule);border-radius:6px}
.svt table{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:12px}
.svt th{font-family:var(--sans);font-size:11.5px;color:var(--muted);font-weight:500;text-align:left;padding:4px 8px;border-bottom:1px solid var(--rule)}
.svt td{border:0;padding:0 8px;vertical-align:top}
.svt td.n{color:var(--muted);text-align:right;width:1%;user-select:none;padding:0 4px 0 10px}
.svt td.c{white-space:pre;width:49%;font-family:var(--mono);font-size:12px}
.svt td.R{border-left:1px solid var(--rule)}
.svt td.gap{background:repeating-linear-gradient(135deg,transparent 0 5px,var(--rule) 5px 6px)}
.svt td.L.chg{background:var(--del)}.svt td.R.chg{background:var(--add)}
.svt span.del{color:var(--neq);font-weight:600}.svt span.add{color:var(--eq);font-weight:600}
.svt td.cond{box-shadow:inset 3px 0 0 var(--sem)}.svt td.ret{box-shadow:inset 3px 0 0 var(--sem);background:var(--semsoft)}
.svt .val{margin-left:14px;color:var(--sem);font-weight:600;font-family:var(--sans)}
.scs{display:grid;gap:5px}.sch{font-size:12.5px;color:var(--muted)}
.sc{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;text-align:left;font:inherit;color:var(--fg);background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:5px 10px;cursor:pointer}
.sc[aria-pressed="true"]{border-color:var(--sem);box-shadow:inset 3px 0 0 var(--sem)}
.sc.weak{opacity:.6}.sc .tag{font-size:11.5px;color:var(--muted)}.sc:focus-visible{outline:2px solid var(--sem);outline-offset:2px}
.lg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11.5px;color:var(--muted)}
.lg .k{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.lg .k.del{background:var(--del)}.lg .k.add{background:var(--add)}.lg .k.cond{box-shadow:inset 3px 0 0 var(--sem)}.lg .k.ret{background:var(--semsoft);box-shadow:inset 3px 0 0 var(--sem)}
.lg .eng{margin-left:auto}
"""
