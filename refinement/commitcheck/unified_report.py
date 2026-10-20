#!/usr/bin/env python3
"""One view that links the four layers around each change:
structural diff (difftastic) - old/new correspondence - execution flow (JDI traces) - analysis evidence
(per-change proof role, the shared code it relies on, the ARDiff refinement step that established it,
counterexamples confirmed by running the code).

usage: unified_report.py OUT.html PAIR_DIR...      (ARDiff runs made by ardiff-workflow.sh / commit_check.py)
Writes OUT.html plus viewers/<pair>.html (refinement viewer) next to it.
"""
import html, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proofrole  # noqa: E402
import semdiff  # noqa: E402
import semview  # noqa: E402
import slicer  # noqa: E402

ROLE = {"identity": ("holds on its own", "id"), "context": ("holds given shared code", "ctx"),
        "breaks": ("changes the result", "brk"), "compensated": ("undone by a later change", "cmp"),
        "no-effect": ("no effect", "nof"), "comment": ("comments only", "nof"),
        "unsupported": ("not analysed", "unk"), "unknown": ("unknown", "unk")}


def h(s):
    return html.escape(str(s))


def fmt(d):
    return ", ".join(f"{k} = {semview._fmt(v)}" for k, v in d.items())


def pair_name(d):
    try:
        return json.load(open(os.path.join(d, "meta.json")))["file"]
    except (OSError, ValueError, KeyError):
        return os.path.basename(d)


def src_title(src):
    """tooltip text for where an input came from"""
    if src == "ARDiff counterexample":
        return "ARDiff counterexample: the input z3 found where old and new differ"
    m = re.match(r"ARDiff path \((old|new)\) #(\d+)", src)
    if m:
        return f"ARDiff (JPF) test input for path {m.group(2)} of the {m.group(1)} version"
    return src


def example_input(m):
    vals = {"double": 2.5, "float": 2.5, "boolean": True}
    return {n: vals.get(t, 7) for t, n in m.params}


def build_pair(d, idx, jhome, out_dir):
    old_src, new_src = semdiff.read(os.path.join(d, "oldV.java")), semdiff.read(os.path.join(d, "newV.java"))
    a, b = old_src.splitlines(), new_src.splitlines()
    log = semdiff.read(os.path.join(d, "debug.log"))
    ardiff = semdiff.verdict_of(log) if log else "not run"
    pr = proofrole.analyze(d)
    _, m = semdiff.target_method(os.path.join(d, "oldV.java"), "oldV")
    params = [n for _, n in m.params] if m else []

    # inputs to run: only what ARDiff produced — its counterexample (z3 model) and JPF's test input for every
    # symbolic path it explored (last refinement iteration, old and new)
    last, _ = semdiff.last_iteration(d)
    cands, seen = [], set()

    def add(inp, src):
        # JPF prints an out-of-range sentinel (e.g. Long.MIN_VALUE) for inputs a path does not constrain: use 0
        full = {p_: (v if v is not None and not (isinstance(v, int) and not -2**31 <= v < 2**31) else 0)
                for p_, v in ((q, inp.get(q)) for q in params)}
        key = json.dumps(full, sort_keys=True)
        if params and key not in seen:
            seen.add(key); cands.append({"inputs": full, "source": src})
    model = semdiff.parse_model(semdiff.read(os.path.join(last, "z3summary.txt"))) or {}
    ce = {k: semdiff.sx_value(v["value"]) for k, v in model.items() if not v["args"] and k in params}
    if ce:
        add(ce, "ARDiff counterexample")
    for side in ("old", "new"):
        for n, t in enumerate(semdiff.parse_jpf_tests(semdiff.read(os.path.join(last, f"I{side}VARDiffJPFOutput.txt")))):
            add(t, f"ARDiff path ({side}) #{n + 1}")
    executed = semdiff.run_concrete(d, cands[:80], jhome).get("runs", []) if cands else []
    n_exec, n_diff = len(executed), sum(r["differs"] for r in executed)
    show = [r for r in executed if r["differs"]][:8] + [r for r in executed if not r["differs"]][:4]
    # inputs ARDiff did not produce that show a difference (from the per-change analysis, confirmed by running):
    # shown only on request. Used when none of ARDiff's own inputs differs.
    extra = []
    if n_diff == 0:      # ARDiff said EQUIVALENT, or none of its own inputs exposes the difference it reported
        xc = [{"inputs": {p_: hk["counterexample"].get(p_, 0) for p_ in params}, "source": "missed by ARDiff", "hunk": k}
              for k, hk in enumerate(pr["hunks"]) if hk.get("counterexample")]
        xr = semdiff.run_concrete(d, xc, jhome).get("runs", []) if xc else []
        extra = [dict(r, hidden=True) for r in xr if r["differs"]]
    show += extra
    traces = semdiff.run_traces(d, [r["inputs"] for r in show], jhome).get("traces", []) if show else []
    runs = []
    for j, r in enumerate(show):
        t = traces[j] if j < len(traces) else None
        if not t:
            continue
        to, tn = [x - 1 for x in t["old"]["lines"]], [x - 1 for x in t["new"]["lines"]]
        runs.append({"label": fmt(r["inputs"]), "src": r["source"], "differs": r["differs"], "hunk": r.get("hunk"),
                     "hidden": bool(r.get("hidden")),
                     "to": to, "tn": tn, "so": slicer.dynamic_slice(a, to), "sn": slicer.dynamic_slice(b, tn),
                     "ret_old": t["old"].get("ret"), "ret_new": t["new"].get("ret"),
                     "cut": bool(t["old"].get("truncated") or t["new"].get("truncated"))})

    picked, statuses = proofrole.refinement_steps(d, a)
    iters = [{"i": i, "status": s, "lines": sorted(l for l, it in picked.items() if it == i)} for i, s in enumerate(statuses)]

    hunks = []
    for k, hk in enumerate(pr["hunks"]):
        label, cls = ROLE.get(hk["role"], ROLE["unknown"])
        hunks.append({"ol": hk["old_lines"], "nl": hk["new_lines"], "role": cls, "label": label,
                      "bounded": hk.get("bounded"), "why": hk.get("why"), "smt_div_only": hk.get("smt_div_only"), "cby": [c for c in hk.get("compensated_by", [])],
                      "uses": hk.get("uses_changes", []) if hk["role"] in ("context", "compensated") else [],
                      "old": hk["old_text"], "new": hk["new_text"],
                      "sup": [{"l": s["line"], "nl": s.get("new_line"), "text": s["text"], "it": s.get("refined_iter")}
                              for s in hk.get("support", [])],
                      # differing ARDiff runs that actually execute this (result-changing) change
                      "runs": [j for j, r in enumerate(runs) if r["differs"] and hk["role"] == "breaks" and (
                          r.get("hunk") == k if r["hidden"] else
                          any(l - 1 in r["to"] for l in hk["old_lines"]) or any(l - 1 in r["tn"] for l in hk["new_lines"]))]})
    example_runs = [j for j, r in enumerate(runs) if not r["hidden"]]
    hidden_runs = [j for j, r in enumerate(runs) if r["hidden"]]

    any_break = any(x["role"] == "brk" for x in hunks)
    per_change = "NOT EQUIVALENT" if any_break else ("EQUIVALENT" if hunks and all(x["role"] in ("id", "ctx", "nof", "cmp") for x in hunks) else "?")
    run_diff = n_diff > 0

    # refinement viewer for this pair
    vrel = None
    if os.path.isdir(os.path.join(d, "iterations")):
        os.makedirs(os.path.join(out_dir, "viewers"), exist_ok=True)
        target = os.path.join(out_dir, "viewers", f"{idx:02d}.html")
        p = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "build_viewer.py"), target, d], capture_output=True, text=True)
        vrel = f"viewers/{idx:02d}.html" if p.returncode == 0 else None

    got = semview.difft_rows(old_src, new_src)
    rows, lch, rch = got or semview.fallback_rows(old_src, new_src)
    trs = []
    for row, (l, r) in enumerate(rows):
        lc = "chg" if l is not None and lch.get(l) else ""
        rc = "chg" if r is not None and rch.get(r) else ""
        lt = semview._stmt_html(a[l], lch.get(l), "del") if l is not None else ""
        rt = semview._stmt_html(b[r], rch.get(r), "add") if r is not None else ""
        trs.append(f'<tr data-row="{row}"><td class="n">{"" if l is None else l + 1}</td><td class="g"></td>'
                   f'<td class="c L {lc}{" gap" if l is None else ""}" data-l="{"" if l is None else l + 1}">{lt}<span class="val"></span></td>'
                   f'<td class="n">{"" if r is None else r + 1}</td><td class="g"></td>'
                   f'<td class="c R {rc}{" gap" if r is None else ""}" data-r="{"" if r is None else r + 1}">{rt}<span class="val"></span></td></tr>')

    def code_lines(ls):
        return "<br>".join(f"<code>{h(t)}</code>" for t in ls) or "<span class='muted'>(none)</span>"

    cards = [f"<p class='muted'>{h(pr['error'])}</p>"] if pr.get("error") else []
    for k, hk in enumerate(hunks):
        ev = []
        for s in hk["sup"]:
            it = f"<span class='itg'>iter {s['it']}</span>" if s["it"] is not None else ""
            ev.append(f"<span class='ev sup' data-act='proof' data-hk='{k}'><span class='evk'>relies on</span><code>{h(s['text'])}</code>{it}</span>")
        for j in hk["runs"]:
            r = runs[j]
            ev.append(f"<span class='ev run{' hid df' if r['hidden'] else ''}' role='button' tabindex='0' data-act='run' data-run='{j}' title='{h(src_title(r['src']))}'"
                      f"{' hidden' if r['hidden'] else ''}>{'<span class=evk>missed by ARDiff</span>' if r['hidden'] else ''}"
                      f"<code>{h(r['label'])}</code><b>{h(r['ret_old'])}</b><span class='muted'>/</span><b class='hl'>{h(r['ret_new'])}</b></span>")
        tags = []
        if hk.get("bounded"):
            tags.append(f"<span class='tag'>loops ≤ {hk['bounded']}</span>")
        if hk.get("uses"):
            tags.append("<span class='tag ctx'>relies on " + ", ".join(f"#{c + 1}" for c in hk["uses"]) + "</span>")
        if hk.get("cby"):
            tags.append("<span class='tag cmp'>undone by " + ", ".join(f"#{c + 1}" for c in hk["cby"]) + "</span>")
        if hk.get("smt_div_only"):
            tags.append("<span class='tag warn' title='ARDiff encodes Java / as SMT div, which rounds down; Java truncates toward zero'>equal under SMT div (ARDiff) · not under Java /</span>")
        if hk.get("why") and hk["role"] == "unk":
            tags.append(f"<span class='tag'>{h(hk['why'])}</span>")
        ev = ([f"<div class='tags'><span class='num'>#{k + 1}</span>{''.join(tags)}</div>"]) + ev
        cards.append(f"""<div class="hk {hk['role']}" data-hk="{k}" role="button" tabindex="0" title="{h(hk['label'])}">
<div class="hkd"><div><span class="side">old</span>{code_lines(hk['old'])}</div><div><span class="side">new</span>{code_lines(hk['new'])}</div></div>
{f'<div class="evs">{"".join(ev)}</div>' if ev else ""}</div>""")
    ex_chips = "".join(f"<span class='ev run{' df' if runs[j]['differs'] else ''}' role='button' tabindex='0' data-act='run' data-run='{j}' title='{h(src_title(runs[j]['src']))}'>"
                       f"<code>{h(runs[j]['label'])}</code><b>{h(runs[j]['ret_old'])}</b><span class='muted'>/</span><b class='{'hl' if runs[j]['differs'] else ''}'>{h(runs[j]['ret_new'])}</b></span>"
                       for j in example_runs)
    if ex_chips:
        ex_chips = f"<span class='exh'>Inputs</span>{ex_chips}"
    if hidden_runs:
        hid = "".join(f"<span class='ev run hid df' hidden role='button' tabindex='0' data-act='run' data-run='{j}' title='per-change counterexample, not produced by ARDiff'>"
                      f"<span class='evk'>missed by ARDiff</span><code>{h(runs[j]['label'])}</code><b>{h(runs[j]['ret_old'])}</b>"
                      f"<span class='muted'>/</span><b class='hl'>{h(runs[j]['ret_new'])}</b></span>" for j in hidden_runs)
        ex_chips += (f"<button type='button' class='showmiss' aria-pressed='false'>show inputs ARDiff missed ({len(hidden_runs)})</button>{hid}")
    tl = "".join(f"<button type='button' class='it {'ok' if it['status'] == 'UNSATISFIABLE' else ''}' data-it='{it['i']}' "
                 f"title='{h(it['status'])}'>{it['i']}</button>" for it in iters)
    vcls = {"EQUIVALENT": "eq", "NOT EQUIVALENT": "neq"}.get
    uid = f"u{idx}"
    data = {"hunks": hunks, "runs": runs, "iters": iters}
    SUMMARY.append({"uid": uid, "name": pair_name(d), "ardiff": ardiff, "iters": len(statuses)})
    vkey = {"EQUIVALENT": "eq", "NOT EQUIVALENT": "neq"}.get(ardiff, "unk")
    return f"""<section class="pair" id="{uid}" data-v="{vkey}">
<div class="ph"><h2>{h(pair_name(d))}</h2>
<span class="chip {vcls(ardiff, 'unk')}">ARDiff: {h(ardiff)}</span></div>
<div class="tl"><span class="muted">ARDiff refinement</span>{tl}{f"<a class='vw' href='{vrel}'>open refinement viewer</a>" if vrel else ""}</div>
<div class="cards">{''.join(cards) or "<p class='muted'>no changed statements</p>"}{f'<div class="exs">{ex_chips}</div>' if ex_chips else ""}</div>
<div class="svw"><table><tr><th></th><th></th><th>old</th><th></th><th></th><th>new</th></tr>{''.join(trs)}</table><svg class="ov" aria-hidden="true"></svg></div>
<div class="bar"><span class="mode"></span><button type="button" class="tg" hidden>all steps</button></div>
<div class="lg"><span><i class="k selc"></i>change</span><span><i class="k sels"></i>shared code it relies on</span><span><i class="k lk"></i>relies on</span>
<span><i class="k ref"></i>made concrete by ARDiff</span><span><i class="k fl"></i>execution (steps that reach the result)</span><span><i class="k dv"></i>runs diverge</span></div>
<script>(function(){{var D={json.dumps(data)},root=document.getElementById("{uid}");{JS}}})();</script></section>"""


JS = r"""
var svg=root.querySelector("svg.ov"), wrap=root.querySelector(".svw"), NS="http://www.w3.org/2000/svg";
var st={hk:0, run:null, it:null, all:false};
function cell(side, ln){ return root.querySelector('td.'+side+'[data-'+side.toLowerCase()+'="'+ln+'"]'); }
function rect(td){ var s=td.querySelector(".st"); return (s&&s.textContent.trim()?s:td).getBoundingClientRect(); }
function el(n,a){ var e=document.createElementNS(NS,n); for(var k in a) e.setAttribute(k,a[k]); return e; }
function marker(id, cls){ var m=el("marker",{id:id,viewBox:"0 0 8 8",refX:"7",refY:"4",markerWidth:"5",markerHeight:"5",orient:"auto-start-reverse"}); m.appendChild(el("path",{d:"M0,0 L8,4 L0,8 z","class":cls})); return m; }
function curve(A,B,W,bendBase,cls,mk,label){
  var ra=rect(A), rb=rect(B), back=rb.top<ra.top;
  var sx=wrap.scrollLeft, sy=wrap.scrollTop;   // the svg scrolls with the table: measure in content coordinates
  var xa=ra.left-W.left-7+sx, xb=rb.left-W.left-5+sx, ya=ra.top+ra.height/2-W.top+sy+(back?-4:4), yb=rb.top+rb.height/2-W.top+sy+(back?4:-4);
  var near=!back && (+B.parentNode.dataset.row - +A.parentNode.dataset.row)===1;
  var bend=near?14:bendBase+Math.min(50,Math.abs(yb-ya)/4), cx=Math.max(3,Math.min(xa,xb)-bend);
  svg.appendChild(el("path",{d:"M"+xa+","+ya+" C"+cx+","+ya+" "+cx+","+yb+" "+xb+","+yb,"class":cls+(back?" back":""),"marker-end":"url(#"+mk+")"}));
  if(label){ var t=el("text",{x:cx-3,y:(ya+yb)/2+3,"class":cls+"t","text-anchor":"end"}); t.textContent=label; svg.appendChild(t); }
}
function seq(r, side){ var t=side==="L"?r.to:r.tn, s=side==="L"?r.so:r.sn; return st.all?t:s.map(function(k){return t[k];}); }
function rowOf(side, l){ var c=cell(side,l+1); return c?+c.parentNode.dataset.row:-1; }
function draw(){
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  var W=wrap.getBoundingClientRect(); if(!W.width) return;
  svg.setAttribute("width",wrap.scrollWidth); svg.setAttribute("height",wrap.scrollHeight);
  var df=el("defs",{}); df.appendChild(marker("mk"+root.id+"p","lkh")); df.appendChild(marker("mk"+root.id+"f","flh")); svg.appendChild(df);
  if(st.run!==null){
    var r=D.runs[st.run];
    ["L","R"].forEach(function(side){
      var q=seq(r,side), edges={}, order=[];
      for(var i=0;i+1<q.length;i++){ var k=q[i]+">"+q[i+1]; if(!edges[k]){edges[k]=0; order.push([q[i],q[i+1]]);} edges[k]++; }
      order.forEach(function(e){ var A=cell(side,e[0]+1), B=cell(side,e[1]+1); if(A&&B){ var c=edges[e[0]+">"+e[1]]; curve(A,B,W,(rect(B).top<rect(A).top)?30:20,"fl","mk"+root.id+"f", c>1&&rect(B).top<rect(A).top?"×"+c:""); } });
    });
    return;
  }
  var hk=D.hunks[st.hk]; if(!hk) return;
  [["L","l",hk.ol],["R","nl",hk.nl]].forEach(function(p){
    var tgt=p[2].map(function(l){return cell(p[0],l);}).filter(Boolean)[0]; if(!tgt) return;
    hk.sup.forEach(function(s){ var ln=p[1]==="l"?s.l:s.nl; var c=ln&&cell(p[0],ln); if(c) curve(c,tgt,W,24,"lk","mk"+root.id+"p","uses"); });
  });
}
function paint(){
  root.querySelectorAll("td.c").forEach(function(td){ td.classList.remove("selc","sels","ref","fl","flx","dv","norun"); td.removeAttribute("data-role"); td.querySelector(".val").textContent=""; });
  root.querySelectorAll(".hk").forEach(function(c){ c.setAttribute("aria-pressed", (+c.dataset.hk===st.hk && st.run===null)?"true":"false"); });
  root.querySelectorAll(".ev.run").forEach(function(c){ c.setAttribute("aria-pressed", +c.dataset.run===st.run?"true":"false"); });
  root.querySelectorAll(".it").forEach(function(c){ c.setAttribute("aria-pressed", "false"); c.classList.remove("hot"); });
  var mode=root.querySelector(".mode"), tg=root.querySelector(".tg");
  if(st.run!==null){
    var r=D.runs[st.run];
    r.to.forEach(function(l){ var c=cell("L",l+1); if(c) c.classList.add("flx"); });
    r.tn.forEach(function(l){ var c=cell("R",l+1); if(c) c.classList.add("flx"); });
    seq(r,"L").forEach(function(l){ var c=cell("L",l+1); if(c) c.classList.add("fl"); });
    seq(r,"R").forEach(function(l){ var c=cell("R",l+1); if(c) c.classList.add("fl"); });
    root.querySelectorAll("td.c:not(.flx):not(.gap)").forEach(function(td){ td.classList.add("norun"); });
    var lo=cell("L", r.to[r.to.length-1]+1), ln=cell("R", r.tn[r.tn.length-1]+1);
    if(lo) lo.querySelector(".val").textContent="⇒ "+r.ret_old; if(ln) ln.querySelector(".val").textContent="⇒ "+r.ret_new;
    var n=Math.min(r.to.length,r.tn.length), dv=-1;
    for(var i=0;i<n;i++) if(rowOf("L",r.to[i])!==rowOf("R",r.tn[i])){ dv=i; break; }
    if(dv<0 && r.ret_old!==r.ret_new) root.querySelectorAll("td.c.fl.chg").forEach(function(td){ td.classList.add("dv"); });
    if(dv>=0){ var x=cell("L",r.to[dv]+1), y=cell("R",r.tn[dv]+1); if(x) x.classList.add("dv"); if(y) y.classList.add("dv"); }
    if(r.hunk!==null){ var hk=D.hunks[r.hunk]; hk.ol.forEach(function(l){ var c=cell("L",l); if(c){c.classList.add("selc"); c.dataset.role=hk.role;} }); hk.nl.forEach(function(l){ var c=cell("R",l); if(c){c.classList.add("selc"); c.dataset.role=hk.role;} }); }
    mode.innerHTML="<b>"+r.src+"</b> "+r.label+" &nbsp; old <b>"+r.ret_old+"</b> / new <b>"+r.ret_new+"</b>";
    tg.hidden=false; tg.textContent=st.all?"steps that reach the result":"all steps";
  } else if(st.it!==null){
    var it=D.iters[st.it];
    it.lines.forEach(function(l){ var c=cell("L",l); if(c) c.classList.add("ref"); });
    var bt=root.querySelector('.it[data-it="'+st.it+'"]'); if(bt) bt.setAttribute("aria-pressed","true");
    mode.innerHTML="<b>ARDiff iteration "+st.it+"</b> &nbsp; "+(it.status||"")+(it.lines.length?" &nbsp; refined line "+it.lines.join(", "):"");
    tg.hidden=true;
  } else {
    var hk2=D.hunks[st.hk];
    if(hk2){
      hk2.ol.forEach(function(l){ var c=cell("L",l); if(c){c.classList.add("selc"); c.dataset.role=hk2.role;} });
      hk2.nl.forEach(function(l){ var c=cell("R",l); if(c){c.classList.add("selc"); c.dataset.role=hk2.role;} });
      hk2.sup.forEach(function(s){ var c=cell("L",s.l); if(c) c.classList.add("sels"); if(s.nl){ var d=cell("R",s.nl); if(d) d.classList.add("sels"); }
        if(s.it!==null){ var b=root.querySelector('.it[data-it="'+s.it+'"]'); if(b) b.classList.add("hot"); } });
      mode.innerHTML="<b>change</b> &nbsp; "+hk2.label;
    }
    tg.hidden=true;
  }
  draw();
}
root.querySelectorAll(".hk").forEach(function(c){ c.addEventListener("click", function(e){ if(e.target.closest(".ev.run")) return; st.hk=+c.dataset.hk; st.run=null; st.it=null; paint(); }); });
root.querySelectorAll(".ev.run").forEach(function(c){ var go=function(e){ e.stopPropagation(); st.run=(st.run===+c.dataset.run)?null:+c.dataset.run; st.it=null; paint(); };
  c.addEventListener("click", go); c.addEventListener("keydown", function(e){ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); go(e); } }); });
root.querySelectorAll(".hk").forEach(function(c){ c.addEventListener("keydown", function(e){ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); c.click(); } }); });
root.querySelectorAll(".it").forEach(function(b){ b.addEventListener("click", function(){ st.it=(st.it===+b.dataset.it)?null:+b.dataset.it; st.run=null; paint(); }); });
root.querySelector(".tg").addEventListener("click", function(){ st.all=!st.all; paint(); });
var sm=root.querySelector(".showmiss"); if(sm) sm.addEventListener("click", function(){
  var on=sm.getAttribute("aria-pressed")!=="true"; sm.setAttribute("aria-pressed", on?"true":"false");
  root.querySelectorAll(".ev.run.hid").forEach(function(c){ c.hidden=!on; });
  if(!on && st.run!==null && D.runs[st.run].hidden){ st.run=null; }
  paint();
});
window.addEventListener("resize", draw); window.addEventListener("load", draw);
if(document.fonts){ if(document.fonts.ready) document.fonts.ready.then(draw); if(document.fonts.addEventListener) document.fonts.addEventListener("loadingdone", draw); }
setTimeout(draw, 400); setTimeout(draw, 1500);
if(window.ResizeObserver) new ResizeObserver(draw).observe(wrap.querySelector("table"));
if(window.ResizeObserver) new ResizeObserver(draw).observe(wrap);
paint();
"""

CSS = """
:root{--bg:#f6f6f3;--panel:#fff;--fg:#1d2128;--muted:#5f6670;--rule:#dcdcd6;--eq:#2a7d4f;--neq:#b8432f;--unk:#9a6d12;
--id:#2a7d4f;--idsoft:#e4f2e9;--ctx:#2f62a8;--ctxsoft:#e3ecf8;--brk:#b8432f;--brksoft:#f8e4df;--nof:#7b7f87;--nofsoft:#eeeeec;
--cmp:#0f7c86;--cmpsoft:#dff2f3;--sup:#c08a1c;--supsoft:#fbf0d6;--flow:#6b3fb3;--flowsoft:#efe6fb;--add:#e6f3ea;--del:#f9e7e3;
--sans:"IBM Plex Sans","Helvetica Neue",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121417;--panel:#1a1d22;--fg:#e4e6ea;--muted:#9aa1ab;--rule:#2c3038;
--eq:#5cc18a;--neq:#ee7a64;--unk:#e0b04a;--id:#5cc18a;--idsoft:#18301f;--ctx:#7aa7ea;--ctxsoft:#1a2a40;--brk:#ee7a64;--brksoft:#3a1f1a;
--nof:#9aa1ab;--nofsoft:#24272d;--cmp:#4fc0c9;--cmpsoft:#14313a;--sup:#e8b84e;--supsoft:#352a12;--flow:#b892f0;--flowsoft:#2e2342;--add:#163020;--del:#3a1d19;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121417;--panel:#1a1d22;--fg:#e4e6ea;--muted:#9aa1ab;--rule:#2c3038;--eq:#5cc18a;--neq:#ee7a64;--unk:#e0b04a;
--id:#5cc18a;--idsoft:#18301f;--ctx:#7aa7ea;--ctxsoft:#1a2a40;--brk:#ee7a64;--brksoft:#3a1f1a;--nof:#9aa1ab;--nofsoft:#24272d;--cmp:#4fc0c9;--cmpsoft:#14313a;
--sup:#e8b84e;--supsoft:#352a12;--flow:#b892f0;--flowsoft:#2e2342;--add:#163020;--del:#3a1d19;color-scheme:dark}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;line-height:1.5}
.wrap{max-width:1280px;margin:0 auto;padding-inline:16px;padding-block:24px 64px;display:grid;gap:28px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:0;font-family:var(--mono);word-break:break-all}
code{font-family:var(--mono);font-size:12.5px}.muted{color:var(--muted)}.hl{color:var(--neq)}
.pair{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:16px;display:grid;gap:12px;min-width:0}
.ph{display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center}
.sum{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:16px;display:grid;gap:12px;min-width:0}
.sumt{overflow-x:auto}.sumt table{border-collapse:collapse;width:100%;font-size:13px}
.sumt th{font-weight:500;color:var(--muted);text-align:left;font-size:12px;padding:4px 10px;border-bottom:1px solid var(--rule)}
.sumt td{padding:4px 10px;border-bottom:1px solid var(--rule);font-family:var(--mono);font-size:12.5px}.sumt td.num{text-align:right}
.sumt a{color:inherit}
.flt{display:flex;flex-wrap:wrap;gap:6px}.flt button{font:inherit;font-size:12px;color:var(--fg);background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:2px 10px;cursor:pointer}
.flt button[aria-pressed="true"]{border-color:var(--fg);font-weight:600}.flt button:focus-visible{outline:2px solid var(--ctx);outline-offset:2px}.okm{color:var(--eq);font-weight:700}.bad{color:var(--neq);font-weight:700}
.chip{font-family:var(--mono);font-size:11.5px;font-weight:600;padding:1px 9px;border-radius:99px;border:1.5px solid currentColor;white-space:nowrap}
.chip.eq{color:var(--eq)}.chip.neq{color:var(--neq)}.chip.unk{color:var(--unk)}
.tl{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:12px}.tl>.muted{margin-right:6px}
.tl .it{font:inherit;font-family:var(--mono);font-size:11px;min-width:24px;padding:1px 4px;background:var(--panel);color:var(--fg);border:1px solid var(--rule);border-radius:4px;cursor:pointer}
.tl .it.ok{border-color:var(--eq);color:var(--eq)}.tl .it.hot{background:var(--supsoft);border-color:var(--sup);color:var(--sup);font-weight:600}
.tl .it[aria-pressed="true"]{outline:2px solid var(--sup);outline-offset:1px}
.tl .vw{margin-left:10px;color:var(--muted);font-size:12px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,400px),1fr));gap:8px}
.hk{display:grid;gap:8px;text-align:left;background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;cursor:pointer}
.hk.cmp{box-shadow:inset 4px 0 0 var(--cmp)}.svw td.selc[data-role=cmp]{background:var(--cmpsoft);box-shadow:inset 3px 0 0 var(--cmp)}
.tags{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.tags .num{font-family:var(--mono);font-size:11px;color:var(--muted)}
.tag{font-family:var(--mono);font-size:11px;border:1px solid var(--rule);border-radius:4px;padding:0 5px;color:var(--muted)}.tag.cmp{border-color:var(--cmp);color:var(--cmp)}.tag.warn{border-color:var(--unk);color:var(--unk)}.tag.ctx{border-color:var(--ctx);color:var(--ctx)}
.hk.id{box-shadow:inset 4px 0 0 var(--id)}.hk.ctx{box-shadow:inset 4px 0 0 var(--ctx)}.hk.brk{box-shadow:inset 4px 0 0 var(--brk)}.hk.nof,.hk.unk{box-shadow:inset 4px 0 0 var(--nof)}
.hk[aria-pressed="true"]{border-color:var(--fg)}.hk:focus-visible,.ev:focus-visible{outline:2px solid var(--ctx);outline-offset:2px}
.hkd{display:grid;gap:2px;font-size:12.5px}.hkd .side{display:inline-block;width:32px;font-size:11px;color:var(--muted)}
.evs,.exs{display:flex;flex-direction:column;gap:4px}.exs{grid-column:1/-1;flex-direction:row;flex-wrap:wrap;align-items:center}
.exs .showmiss{font:inherit;font-size:11.5px;color:var(--unk);background:var(--panel);border:1px dashed var(--unk);border-radius:6px;padding:1px 8px;cursor:pointer}
.exs .showmiss[aria-pressed="true"]{border-style:solid}
.exs .exh{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-right:4px}.ev.run.df{box-shadow:inset 3px 0 0 var(--neq)}
.ev{display:flex;gap:8px;align-items:center;border-radius:4px;padding:3px 8px;font-size:12.5px}
.ev .evk{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);min-width:56px}
.ev.sup{background:var(--supsoft);box-shadow:inset 3px 0 0 var(--sup)}
.ev.run{background:var(--flowsoft);box-shadow:inset 3px 0 0 var(--flow);cursor:pointer;font-family:var(--mono)}
.ev.run[aria-pressed="true"]{outline:2px solid var(--flow);outline-offset:-1px}
.itg{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--sup);border:1px solid var(--sup);border-radius:4px;padding:0 5px}
.svw{position:relative;overflow-x:auto;border:1px solid var(--rule);border-radius:8px}
.svw table{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:12.5px}
.svw th{font-family:var(--sans);font-size:11.5px;color:var(--muted);font-weight:500;text-align:left;padding:4px 8px;border-bottom:1px solid var(--rule)}
.svw td{padding:0 8px;line-height:28px;vertical-align:top}.svw td.n{color:var(--muted);text-align:right;width:1%;user-select:none}
.svw td.g{width:56px;min-width:56px;padding:0}.svw td.c{white-space:pre;width:49%}.svw td.R{border-left:1px solid var(--rule)}
.svw td.gap{background:repeating-linear-gradient(135deg,transparent 0 5px,var(--rule) 5px 6px)}
.svw td.L.chg{background:var(--del)}.svw td.R.chg{background:var(--add)}
.svw span.del{color:var(--neq);font-weight:600}.svw span.add{color:var(--eq);font-weight:600}
.svw td.fl{background:var(--flowsoft)}.svw td.norun{opacity:.4}
.svw td.selc[data-role=id]{background:var(--idsoft);box-shadow:inset 3px 0 0 var(--id)}.svw td.selc[data-role=ctx]{background:var(--ctxsoft);box-shadow:inset 3px 0 0 var(--ctx)}
.svw td.selc[data-role=brk]{background:var(--brksoft);box-shadow:inset 3px 0 0 var(--brk)}.svw td.selc[data-role=nof],.svw td.selc[data-role=unk]{background:var(--nofsoft)}
.svw td.sels{background:var(--supsoft);box-shadow:inset 3px 0 0 var(--sup)}.svw td.ref{background:var(--supsoft);outline:2px dashed var(--sup);outline-offset:-2px}
.svw td.dv{box-shadow:inset 3px 0 0 var(--neq)}
.svw .val{margin-left:14px;color:var(--flow);font-weight:600;font-family:var(--sans)}
svg.ov{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
svg.ov .lk{fill:none;stroke:var(--sup);stroke-width:1.6}svg.ov .lkh{fill:var(--sup)}svg.ov .lkt{fill:var(--sup);font:600 10.5px var(--sans)}
svg.ov .fl{fill:none;stroke:var(--flow);stroke-width:1.3;opacity:.85}svg.ov .fl.back{stroke-dasharray:4 3}svg.ov .flh{fill:var(--flow)}svg.ov .flt{fill:var(--flow);font:600 10px var(--mono)}
.bar{display:flex;gap:10px;align-items:center;font-size:12.5px;min-height:24px}
.bar .tg{font:inherit;font-size:12px;color:var(--fg);background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:1px 8px;cursor:pointer}
.lg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11.5px;color:var(--muted)}
.lg .k{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;vertical-align:-2px}
.lg .selc{background:var(--ctxsoft);box-shadow:inset 3px 0 0 var(--ctx)}.lg .sels{background:var(--supsoft);box-shadow:inset 3px 0 0 var(--sup)}
.lg .lk{border-top:2px solid var(--sup);height:0;width:16px;border-radius:0}.lg .ref{outline:2px dashed var(--sup);outline-offset:-2px}
.lg .fl{border-top:2px solid var(--flow);height:0;width:16px;border-radius:0}.lg .dv{box-shadow:inset 3px 0 0 var(--neq)}
"""


SUMMARY = []


def expected(name):
    parts = name.replace("\\", "/").split("/")
    return "NOT EQUIVALENT" if "NEq" in parts else "EQUIVALENT" if "Eq" in parts else None


def summary_html():
    vc = {"EQUIVALENT": "eq", "NOT EQUIVALENT": "neq"}
    counts = {}
    for r in SUMMARY:
        counts[r["ardiff"]] = counts.get(r["ardiff"], 0) + 1
    exp_known = [r for r in SUMMARY if expected(r["name"]) and r["ardiff"] in vc]
    right = sum(1 for r in exp_known if expected(r["name"]) == r["ardiff"])
    chips = "".join(f"<span class='chip {vc.get(k, 'unk')}'>ARDiff: {h(k)} {v}</span>" for k, v in counts.items())
    if exp_known:
        chips += f"<span class='chip unk'>matches expected {right}/{len(exp_known)}</span>"
    rows = []
    for r in SUMMARY:
        e = expected(r["name"])
        ok = "" if not e or r["ardiff"] not in vc else ("<span class='okm'>✓</span>" if e == r["ardiff"] else "<span class='bad'>✗</span>")
        rows.append(f"<tr data-v='{vc.get(r['ardiff'], 'unk')}'><td><a href='#{r['uid']}'>{h(r['name'])}</a></td><td><span class='chip {vc.get(r['ardiff'], 'unk')}'>{h(r['ardiff'])}</span></td>"
                    f"<td class='num'>{r['iters'] or ''}</td><td>{h(e or '')}</td><td>{ok}</td></tr>")
    filt = ("<div class='flt' role='group' aria-label='filter by ARDiff result'>"
            "<button type='button' data-f='' aria-pressed='true'>all</button>"
            "<button type='button' data-f='neq' aria-pressed='false'>NOT EQUIVALENT</button>"
            "<button type='button' data-f='eq' aria-pressed='false'>EQUIVALENT</button>"
            + ("<button type='button' data-f='unk' aria-pressed='false'>other</button>" if any(r["ardiff"] not in vc for r in SUMMARY) else "")
            + "</div>")
    script = """<script>(function(){var bs=document.querySelectorAll('.flt button');
bs.forEach(function(b){b.addEventListener('click',function(){var f=b.dataset.f;
bs.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});
document.querySelectorAll('.sumt tr[data-v], section.pair[data-v]').forEach(function(el){el.hidden=!!f&&el.dataset.v!==f;});
window.dispatchEvent(new Event('resize'));});});})();</script>"""
    return (f"<section class='sum'><div class='ph'>{chips}</div>{filt}<div class='sumt'><table><tr><th>pair</th><th>ARDiff</th>"
            f"<th>refinement iterations</th><th>expected (folder name)</th><th></th></tr>{''.join(rows)}</table></div></section>{script}")


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    out_dir = os.path.dirname(os.path.abspath(out))
    jhome = semdiff.java_home(None)
    sections = [build_pair(d, i, jhome, out_dir) for i, d in enumerate(dirs)]
    page = f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Software Regression Visualization</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="wrap"><header><h1>Software Regression Visualization</h1></header>
{summary_html()}
{''.join(sections)}</div>"""
    open(out, "w").write(page)
    print(out)


if __name__ == "__main__":
    main()
