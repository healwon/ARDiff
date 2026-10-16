"""difftastic-style side-by-side view of old/new code with ARDiff's semantic difference on top.

Syntax layer : `difft --display json` (structural diff: aligned lines + changed tokens).
               Falls back to a difflib line/token diff when difftastic is not installed.
Semantic layer: "scenarios" = inputs where old and new return different values. A scenario coming from
               a difference region (semdiff.region_analysis) also carries the symbolic path taken on each
               side; those lines are marked, and the return line shows the value each version returns.
"""
import difflib, html, json, os, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slicer  # noqa: E402

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


def _stmt_html(line, spans, cls):
    """indentation and statement in separate spans, so the flow arrows can attach to where the code starts"""
    ind = len(line) - len(line.lstrip())
    rest = [(max(0, st - ind), en - ind) for st, en in (spans or []) if en > ind]
    return f'<span class="ind">{html.escape(line[:ind])}</span><span class="st">{_code_html(line[ind:], rest, cls)}</span>'


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
    # one entry per behaviour (old value, new value); the other inputs with the same pair are listed under it
    groups = {}
    for sc in out:
        k = (str(sc["ret_old"]), str(sc["ret_new"]), sc["refuted"])
        if k in groups:
            groups[k]["more"].append(sc["inputs"])
        else:
            groups[k] = {**sc, "more": []}
    return list(groups.values())[:12]


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
    """HTML fragment: scenario picker + side-by-side diff. `rep` = semdiff report (optional).
    With line traces (rep["traces"]) the chosen input's execution is drawn as arrows next to each side."""
    got = difft_rows(old_text, new_text)
    engine = "difftastic" if got else "difflib"
    rows, lch, rch = got or fallback_rows(old_text, new_text)
    a, b = old_text.splitlines(), new_text.splitlines()

    scs = scenarios(rep) if rep else []
    traces = (rep or {}).get("traces", {})
    sc_data = []
    for k, s in enumerate(scs):
        d = {"i": k, "ret_old": _fmt(s["ret_old"]), "ret_new": _fmt(s["ret_new"])}
        t = traces.get(json.dumps(s["inputs"], sort_keys=True, default=str))
        if t:
            d["to"] = [x - 1 for x in t["old"]["lines"]]
            d["tn"] = [x - 1 for x in t["new"]["lines"]]
            # steps that actually feed the returned value (data + control dependence)
            d["so"] = slicer.dynamic_slice(a, d["to"])
            d["sn"] = slicer.dynamic_slice(b, d["tn"])
            d["cut"] = bool(t["old"].get("truncated") or t["new"].get("truncated"))
            d["ret_old"], d["ret_new"] = t["old"].get("ret") or d["ret_old"], t["new"].get("ret") or d["ret_new"]
        elif s["kind"] == "region" and s.get("aligned", True):
            op = rep["old_paths"][s["old_path"]] if s["old_path"] < len(rep.get("old_paths", [])) else None
            np_ = rep["new_paths"][s["new_path"]] if s["new_path"] < len(rep.get("new_paths", [])) else None
            d["old"], d["oret"] = _path_lines(op)
            d["new"], d["nret"] = _path_lines(np_)
        sc_data.append(d)
    any_trace = any("to" in d for d in sc_data)

    trs = []
    for row, (l, r) in enumerate(rows):
        lcls = "chg" if l is not None and lch.get(l) else ""
        rcls = "chg" if r is not None and rch.get(r) else ""
        ltxt = _stmt_html(a[l], lch.get(l), "del") if l is not None else ""
        rtxt = _stmt_html(b[r], rch.get(r), "add") if r is not None else ""
        trs.append(
            f'<tr data-row="{row}"><td class="n">{"" if l is None else l + 1}</td><td class="g gL"></td>'
            f'<td class="c L {lcls}{" gap" if l is None else ""}" data-l="{"" if l is None else l}">{ltxt}<span class="val"></span></td>'
            f'<td class="n">{"" if r is None else r + 1}</td><td class="g gR"></td>'
            f'<td class="c R {rcls}{" gap" if r is None else ""}" data-r="{"" if r is None else r}">{rtxt}<span class="val"></span></td></tr>')

    picker = stepper = ""
    if scs:
        btns = []
        for k, s in enumerate(scs):
            inp = ", ".join(f"{n} = {_fmt(v)}" for n, v in s["inputs"].items()) or "(입력 없음)"
            tag = ("실행 확인" if s["confirmed"] else "실행 결과는 같음 (추상화로 인한 차이)" if s["refuted"] else "기호 분석")
            path = (f"경로 old #{s['old_path']} · new #{s['new_path']}" if s["kind"] == "region"
                    else f"입력 출처: {s.get('source', '')}")
            more = ""
            if s.get("more"):
                others = "; ".join(", ".join(f"{n} = {_fmt(v)}" for n, v in m.items()) for m in s["more"][:30])
                more = f'<span class="tag" title="{html.escape(others)}">같은 결과인 입력 {len(s["more"])}개 더</span>'
            btns.append(
                f'<button type="button" class="sc{" weak" if s["refuted"] else ""}" data-sc="{k}">'
                f'<code>{html.escape(inp)}</code> <span class="arrow">old <b>{html.escape(sc_data[k]["ret_old"])}</b> → new '
                f'<b class="hl">{html.escape(sc_data[k]["ret_new"])}</b></span>'
                f'<span class="tag">{html.escape(tag)} · {html.escape(path)}</span>{more}</button>')
        what = "실행 흐름(화살표)과 반환값" if any_trace else "각 버전이 지나는 줄과 반환값"
        picker = (f'<div class="scs"><div class="sch">결과가 달라지는 경우 {len(scs)}가지 (old/new 반환값 조합별) · 고르면 {what}을 코드에 표시</div>'
                  f'{"".join(btns)}</div>')
        if any_trace:
            stepper = ('<div class="stp"><button type="button" class="md" aria-pressed="true">반환값에 연관된 줄만</button>'
                       '<button type="button" class="sp" aria-label="이전 단계">◀</button>'
                       '<button type="button" class="pl">▶ 따라가기</button><button type="button" class="sn" aria-label="다음 단계">▶</button>'
                       '<input type="range" class="sr" min="0" value="0" aria-label="실행 단계"><span class="sl"></span></div>')
    legend = ('<div class="lg"><span><i class="k del"></i>삭제된 토큰</span><span><i class="k add"></i>추가된 토큰</span>'
              + ('<span><i class="k run"></i>반환값에 연관된 줄 (연관 모드) / 실행된 줄 (전체 모드)</span><span><i class="k arw"></i>실행 순서 (점선 = 되돌아감, ×n = 반복 횟수)</span><span style="opacity:.5">흐린 줄 = 실행 안 됨</span>'
                 '<span><i class="k dv"></i>old/new가 처음 갈라지는 곳 (흐름이 같으면 실행된 바뀐 줄)</span><span><i class="k cur"></i>따라가기 현재 줄</span>' if any_trace else
                 '<span><i class="k cond"></i>선택한 입력이 지나는 조건</span><span><i class="k ret"></i>반환 줄</span>' if scs else "")
              + f'<span class="eng">구문 비교: {engine}</span></div>')
    script = ""
    if scs:
        script = "<script>" + _JS.replace("__DATA__", json.dumps(sc_data)).replace("__UID__", uid) + "</script>"
    return (f'<div class="sv" id="{uid}">{picker}{stepper}<div class="svt"><div class="svw"><table>'
            f'<tr><th></th><th></th><th>old</th><th></th><th></th><th>new</th></tr>{"".join(trs)}</table>'
            f'<svg class="arrows" aria-hidden="true"></svg></div></div>{legend}</div>{script}')


_JS = r"""(function(){
var D=__DATA__, root=document.getElementById("__UID__"), svg=root.querySelector("svg.arrows"), wrap=root.querySelector(".svw");
var cur=0, step=0, timer=null, mode="slice", NS="http://www.w3.org/2000/svg";
function seqs(s){   // the line sequence drawn: only the steps in the slice, or the whole run
  if (mode!=="slice" || !s.so) return [s.to, s.tn];
  return [s.so.map(function(k){return s.to[k];}), s.sn.map(function(k){return s.tn[k];})];
}
function cell(side, ln){ return root.querySelector('td.'+side+'[data-'+side.toLowerCase()+'="'+ln+'"]'); }
function rowOf(side, ln){ var td=cell(side, ln); return td ? +td.parentNode.dataset.row : -1; }
function el(name, attrs){ var e=document.createElementNS(NS, name); for (var k in attrs) e.setAttribute(k, attrs[k]); return e; }
function divergence(s){
  var n=Math.min(s.to.length, s.tn.length);
  for (var i=0;i<n;i++) if (rowOf("L", s.to[i])!==rowOf("R", s.tn[i])) return i;
  return s.to.length===s.tn.length ? -1 : n;
}
function anchor(side, ln){   // where the statement text starts on that line
  var td=cell(side, ln); if(!td) return null;
  var st=td.querySelector(".st"), r=(st && st.textContent.trim() ? st : td).getBoundingClientRect();
  return {x:r.left, y:r.top+r.height/2, row:+td.parentNode.dataset.row};
}
function draw(){
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  var s=D[cur]; if (!s || !s.to) return;
  var W=wrap.getBoundingClientRect(); if (!W.width) return;
  svg.setAttribute("width", W.width); svg.setAttribute("height", W.height);
  var defs=el("defs",{}), mk=el("marker",{id:"ah__UID__",viewBox:"0 0 8 8",refX:"7",refY:"4",markerWidth:"5",markerHeight:"5",orient:"auto-start-reverse"});
  mk.appendChild(el("path",{d:"M0,0 L8,4 L0,8 z","class":"ahd"})); defs.appendChild(mk); svg.appendChild(defs);
  var q=seqs(s);
  [["L", q[0]], ["R", q[1]]].forEach(function(p){
    var side=p[0], seq=p[1], edges={}, order=[];
    for (var i=0;i+1<seq.length;i++){ var k=seq[i]+">"+seq[i+1]; if(!edges[k]){edges[k]=0; order.push([seq[i],seq[i+1]]);} edges[k]++; }
    var minX=(root.querySelector("td.g"+side)||{getBoundingClientRect:function(){return W;}}).getBoundingClientRect().left-W.left+2;
    order.forEach(function(e){
      var A=anchor(side,e[0]), B=anchor(side,e[1]); if(!A||!B) return;
      var xa=A.x-W.left-7, xb=B.x-W.left-5, cnt=edges[e[0]+">"+e[1]], back=B.y<A.y;
      // leave from the lower half of the statement, arrive in the upper half (reversed for loops)
      var ya=A.y-W.top+(back?-4:4), yb=B.y-W.top+(back?4:-4);
      var near=!back && B.row-A.row===1;
      var bend=near ? 14 : (back ? 30 : 20) + Math.min(50, Math.abs(yb-ya)/4);
      var cx=Math.max(minX, Math.min(xa, xb)-bend);
      var d="M"+(xa-1)+","+ya+" C"+cx+","+ya+" "+cx+","+yb+" "+xb+","+yb;
      svg.appendChild(el("path",{d:d,"class":"arw"+(back?" back":""),"marker-end":"url(#ah__UID__)"}));
      if (cnt>1 && back){ var t=el("text",{x:cx-2, y:(ya+yb)/2+3,"class":"cnt","text-anchor":"end"}); t.textContent="×"+cnt; svg.appendChild(t); }
    });
  });
}
function paint(){
  var s=D[cur];
  root.querySelectorAll("td.c").forEach(function(td){ td.classList.remove("cond","ret","run","rel","dv","cur","norun"); td.querySelector(".val").textContent=""; });
  root.classList.toggle("slice", mode==="slice");
  if (s.to){
    s.to.forEach(function(l){ var td=cell("L",l); if(td) td.classList.add("run"); });
    s.tn.forEach(function(l){ var td=cell("R",l); if(td) td.classList.add("run"); });
    root.querySelectorAll("td.c:not(.run):not(.gap)").forEach(function(td){ td.classList.add("norun"); });
    var q=seqs(s);
    q[0].forEach(function(l){ var td=cell("L",l); if(td) td.classList.add("rel"); });
    q[1].forEach(function(l){ var td=cell("R",l); if(td) td.classList.add("rel"); });
    var lo=cell("L", s.to[s.to.length-1]), ln=cell("R", s.tn[s.tn.length-1]);
    if (lo) lo.querySelector(".val").textContent="⇒ "+s.ret_old+(s.cut?" (기록 일부)":"");
    if (ln) ln.querySelector(".val").textContent="⇒ "+s.ret_new;
    var dv=divergence(s);
    if (dv>=0){ var a=cell("L", s.to[Math.min(dv, s.to.length-1)]), b=cell("R", s.tn[Math.min(dv, s.tn.length-1)]); if(a) a.classList.add("dv"); if(b) b.classList.add("dv"); }
    else { root.querySelectorAll("td.c.run.chg").forEach(function(td){ td.classList.add("dv"); }); }   // same flow: the changed lines that ran made the difference
    var N=Math.max(q[0].length, q[1].length)-1, sr=root.querySelector(".sr");
    sr.max=N; if (step>N) step=N; sr.value=step;
    var co=cell("L", q[0][Math.min(step, q[0].length-1)]), cn=cell("R", q[1][Math.min(step, q[1].length-1)]);
    if (co) co.classList.add("cur"); if (cn) cn.classList.add("cur");
    root.querySelector(".sl").textContent=(mode==="slice"?"연관된 단계 ":"단계 ")+step+" / "+N+(mode==="slice"?" (전체 "+(Math.max(s.to.length,s.tn.length)-1)+"단계 중)":"")
      +(dv>=0?" · 실행 흐름이 갈라지는 곳 빨간 선":" · 실행 흐름은 같음, 실행된 바뀐 줄(빨간 선)에서 값이 달라짐");
    root.querySelector(".stp").hidden=false;
  } else {
    var st=root.querySelector(".stp"); if (st) st.hidden=true;
    [["L", s.old, s.oret, s.ret_old], ["R", s.new, s.nret, s.ret_new]].forEach(function(p){
      if (!p[1]) return;
      Object.keys(p[1]).forEach(function(l){ var td=cell(p[0], l); if (td) td.classList.add(p[1][l]); });
      if (p[2]!==null && p[2]!==undefined){ var td=cell(p[0], p[2]); if (td) td.querySelector(".val").textContent="⇒ "+p[3]; }
    });
  }
  draw();
}
function pick(k){
  cur=k; step=0; stop();
  root.querySelectorAll(".sc").forEach(function(b){ b.setAttribute("aria-pressed", +b.dataset.sc===k ? "true":"false"); });
  paint();
}
function go(n){ var s=D[cur]; if(!s.to) return; var q=seqs(s); step=Math.max(0, Math.min(Math.max(q[0].length, q[1].length)-1, n)); paint(); }
function stop(){ if (timer){ clearInterval(timer); timer=null; } var p=root.querySelector(".pl"); if (p) p.textContent="▶ 따라가기"; }
root.querySelectorAll(".sc").forEach(function(b){ b.addEventListener("click", function(){ pick(+b.dataset.sc); }); });
var md=root.querySelector(".md"); if (md) md.addEventListener("click", function(){
  mode = mode==="slice" ? "all" : "slice"; step=0; stop();
  md.setAttribute("aria-pressed", mode==="slice" ? "true" : "false");
  md.textContent = mode==="slice" ? "반환값에 연관된 줄만" : "전체 실행 흐름";
  paint();
});
var sp=root.querySelector(".sp"); if (sp){
  sp.addEventListener("click", function(){ stop(); go(step-1); });
  root.querySelector(".sn").addEventListener("click", function(){ stop(); go(step+1); });
  root.querySelector(".sr").addEventListener("input", function(e){ stop(); go(+e.target.value); });
  root.querySelector(".pl").addEventListener("click", function(){
    if (timer){ stop(); return; }
    var s=D[cur]; if (!s.to) return; var q=seqs(s), N=Math.max(q[0].length, q[1].length)-1; if (step>=N) step=-1;
    this.textContent="❚❚ 멈춤"; timer=setInterval(function(){ if (step>=N) stop(); else go(step+1); }, 450);
  });
}
window.addEventListener("resize", draw);
window.addEventListener("load", draw);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);   // column widths change once the web font arrives
if (window.ResizeObserver) new ResizeObserver(function(){ draw(); }).observe(wrap);
var det=root.closest("details"); if (det) det.addEventListener("toggle", draw);
pick(0);
})();"""


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
.svw{position:relative;min-width:100%;width:max-content}.svw table{min-width:100%}
.svw svg.arrows{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.svt td.g{width:44px;min-width:44px;padding:0}.svw td.c,.svw td.n{line-height:30px}.svt td.norun{opacity:.45}
.arrows .arw{fill:none;stroke:var(--sem);stroke-width:1.3;opacity:.85}.arrows .arw.back{stroke-dasharray:4 3}.arrows .ahd{fill:var(--sem)}
.arrows .cnt{fill:var(--sem);font:600 10px var(--mono)}
.svt td.run{background:var(--semsoft)}.sv.slice .svt td.run:not(.rel){background:none;opacity:.7}.svt td.dv{box-shadow:inset 3px 0 0 var(--neq)}
.svt td.cur{outline:2px solid var(--sem);outline-offset:-2px}
.stp{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12.5px;color:var(--muted)}
.stp button{font:inherit;color:var(--fg);background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:2px 9px;cursor:pointer}
.stp .sr{flex:1 1 160px}.stp .md[aria-pressed="true"]{border-color:var(--sem);color:var(--sem);font-weight:600}
.lg .k.run{background:var(--semsoft)}.lg .k.arw{border-top:2px solid var(--sem);height:0;width:14px;border-radius:0}
.lg .k.dv{box-shadow:inset 3px 0 0 var(--neq)}.lg .k.cur{outline:2px solid var(--sem);outline-offset:-2px}
"""
