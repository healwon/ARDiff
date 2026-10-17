#!/usr/bin/env python3
""""Why is this change okay?" page: for each oldV/newV pair, every change with its role in the equivalence proof.

usage: proof_report.py OUT.html PAIR_DIR...   (pair dirs = ARDiff runs made by ardiff-workflow.sh / commit_check.py)

Separate from report.html (commit_check.py); it reuses the side-by-side diff (semview) but draws proof links
instead of execution flow: change -> the earlier statements its proof needs.
"""
import html, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proofrole  # noqa: E402
import semdiff  # noqa: E402
import semview  # noqa: E402

ROLE = {
    "identity": ("holds on its own", "id", "the rewrite gives the same value without any other code"),
    "context": ("holds given shared code", "ctx", "not on its own, but the earlier shared code guarantees the same value"),
    "breaks": ("changes the result", "brk", "some input returns a different value because of this change"),
    "no-effect": ("no effect", "nof", "what it writes is never read afterwards"),
    "comment": ("comments only", "nof", "no code changed"),
    "unsupported": ("not analysed", "unk", "outside what the symbolic executor models"),
    "unknown": ("unknown", "unk", "z3 gave no answer in time"),
}


def h(s):
    return html.escape(str(s))


def fmt_inputs(d):
    return ", ".join(f"{k} = {semview._fmt(v)}" for k, v in d.items())


def pair_name(d):
    try:
        return json.load(open(os.path.join(d, "meta.json")))["file"]
    except (OSError, ValueError, KeyError):
        return os.path.basename(d)


def build_pair(d, idx, jhome):
    old_src, new_src = semdiff.read(os.path.join(d, "oldV.java")), semdiff.read(os.path.join(d, "newV.java"))
    log = semdiff.read(os.path.join(d, "debug.log"))
    ardiff = semdiff.verdict_of(log) if log else "not run"
    pr = proofrole.analyze(d)
    _, m = semdiff.target_method(os.path.join(d, "oldV.java"), "oldV")
    params = [n for _, n in m.params] if m else []

    # concrete values for each counterexample, from running the original methods
    cands = [{"inputs": {p: hk["counterexample"].get(p, 0) for p in params}, "source": f"h{k}"}
             for k, hk in enumerate(pr["hunks"]) if hk.get("counterexample")]
    runs = semdiff.run_concrete(d, cands, jhome).get("runs", []) if cands else []
    by_src = {r["source"]: r for r in runs}

    any_break = any(hk["role"] == "breaks" for hk in pr["hunks"])
    proof_verdict = "NOT EQUIVALENT" if any_break else ("EQUIVALENT" if pr["hunks"] and all(
        hk["role"] in ("identity", "context", "no-effect", "comment") for hk in pr["hunks"]) else "?")

    cards, data = [], []
    for k, hk in enumerate(pr["hunks"]):
        label, cls, desc = ROLE.get(hk["role"], ROLE["unknown"])
        old_t = "<br>".join(f"<code>{h(t)}</code>" for t in hk["old_text"]) or "<span class='muted'>(none)</span>"
        new_t = "<br>".join(f"<code>{h(t)}</code>" for t in hk["new_text"]) or "<span class='muted'>(none)</span>"
        why = []
        if hk["role"] == "context":
            for sp in hk.get("support", []):
                it = sp.get("refined_iter")
                why.append(f"<div class='sup'><span class='ln'>{sp['line']}</span><code>{h(sp['text'])}</code>"
                           + (f"<span class='itg' title='ARDiff refinement'>iter {it}</span>" if it is not None else "") + "</div>")
        elif hk["role"] == "breaks":
            run = by_src.get(f"h{k}")
            ce = hk.get("counterexample", {})
            vals = f"<span class='arr'>→</span><b>{h(run['old'])}</b><span class='arr'>/</span><b class='hl'>{h(run['new'])}</b>" if run else ""
            why.append(f"<div class='ce'><code>{h(fmt_inputs(ce))}</code>{vals}</div>")
        cards.append(f"""<button type="button" class="hk {cls}" data-hk="{k}">
<div class="hkd"><div><span class="side">old</span>{old_t}</div><div><span class="side">new</span>{new_t}</div></div>
{f'<div class="hkw">{"".join(why)}</div>' if why else ""}</button>""")
        data.append({"ol": hk["old_lines"], "nl": hk["new_lines"], "role": cls,
                     "so": [s["line"] for s in hk.get("support", [])],
                     "sn": [s["new_line"] for s in hk.get("support", []) if s.get("new_line")]})

    # side-by-side code, same structure as semview (row/cell attributes), own overlay script
    got = semview.difft_rows(old_src, new_src)
    rows, lch, rch = got or semview.fallback_rows(old_src, new_src)
    a, b = old_src.splitlines(), new_src.splitlines()
    trs = []
    for row, (l, r) in enumerate(rows):
        lc = "chg" if l is not None and lch.get(l) else ""
        rc = "chg" if r is not None and rch.get(r) else ""
        lt = semview._stmt_html(a[l], lch.get(l), "del") if l is not None else ""
        rt = semview._stmt_html(b[r], rch.get(r), "add") if r is not None else ""
        trs.append(f'<tr data-row="{row}"><td class="n">{"" if l is None else l + 1}</td><td class="g"></td>'
                   f'<td class="c L {lc}{" gap" if l is None else ""}" data-l="{"" if l is None else l + 1}">{lt}</td>'
                   f'<td class="n">{"" if r is None else r + 1}</td><td class="g"></td>'
                   f'<td class="c R {rc}{" gap" if r is None else ""}" data-r="{"" if r is None else r + 1}">{rt}</td></tr>')

    vcls = {"EQUIVALENT": "eq", "NOT EQUIVALENT": "neq"}.get
    agree = "" if proof_verdict == "?" or ardiff not in ("EQUIVALENT", "NOT EQUIVALENT") else (
        "<span class='muted'>agrees with ARDiff</span>" if ardiff == proof_verdict else
        "<span class='warn'>disagrees with ARDiff</span>")
    uid = f"p{idx}"
    statuses = pr.get("statuses") or []
    timeline = ""
    if statuses:
        steps = "".join(f"<span class='it {('ok' if s == 'UNSATISFIABLE' else 'go')}' title='{h(s)}'>{i}</span>" for i, s in enumerate(statuses))
        timeline = f"<div class='tl'><span class='muted'>ARDiff refinement</span>{steps}</div>"
    err = f"<p class='warn'>{h(pr['error'])}</p>" if pr.get("error") else ""
    return f"""<section class="pair" id="{uid}">
<div class="ph"><h2>{h(pair_name(d))}</h2>
<span class="chip {vcls(ardiff, 'unk')}">ARDiff: {h(ardiff)}</span>
<span class="chip {vcls(proof_verdict, 'unk')}">per change: {h(proof_verdict)}</span></div>
{timeline}{err}
<div class="grid"><div class="cards">{''.join(cards) or "<p class='muted'>no changed statements</p>"}</div>
<div class="code"><div class="svw"><table><tr><th></th><th></th><th>old</th><th></th><th></th><th>new</th></tr>{''.join(trs)}</table>
<svg class="links" aria-hidden="true"></svg></div>
<div class="lg"><span><i class="k hl-c"></i>selected change</span><span><i class="k hl-s"></i>shared code it relies on</span><span><i class="k lk"></i>relies on</span></div></div></div>
<script>(function(){{var D={json.dumps(data)},root=document.getElementById("{uid}");
{JS}}})();</script></section>"""


JS = r"""
var svg=root.querySelector("svg.links"), wrap=root.querySelector(".svw"), NS="http://www.w3.org/2000/svg", cur=0;
function cell(side, ln){ return root.querySelector('td.'+side+'[data-'+side.toLowerCase()+'="'+ln+'"]'); }
function anchor(td){ var st=td.querySelector(".st"); var r=(st&&st.textContent.trim()?st:td).getBoundingClientRect(); return r; }
function el(n,a){ var e=document.createElementNS(NS,n); for(var k in a) e.setAttribute(k,a[k]); return e; }
function draw(){
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  var s=D[cur]; if(!s) return; var W=wrap.getBoundingClientRect(); if(!W.width) return;
  svg.setAttribute("width",W.width); svg.setAttribute("height",W.height);
  var mk=el("marker",{id:"pa"+root.id,viewBox:"0 0 8 8",refX:"7",refY:"4",markerWidth:"6",markerHeight:"6",orient:"auto-start-reverse"});
  mk.appendChild(el("path",{d:"M0,0 L8,4 L0,8 z","class":"lkh"})); var df=el("defs",{}); df.appendChild(mk); svg.appendChild(df);
  [["L", s.so, s.ol], ["R", s.sn, s.nl]].forEach(function(p){
    var targets=p[2].map(function(l){return cell(p[0],l);}).filter(Boolean); if(!targets.length) return;
    var t=targets[0];
    p[1].forEach(function(l){
      var c=cell(p[0],l); if(!c) return;
      var ra=anchor(c), rb=anchor(t);
      var xa=ra.left-W.left-6, ya=ra.top+ra.height/2-W.top, xb=rb.left-W.left-6, yb=rb.top+rb.height/2-W.top;
      var bend=24+Math.min(60,Math.abs(yb-ya)/3), cx=Math.max(4,Math.min(xa,xb)-bend);
      svg.appendChild(el("path",{d:"M"+xa+","+ya+" C"+cx+","+ya+" "+cx+","+yb+" "+xb+","+yb,"class":"lk","marker-end":"url(#pa"+root.id+")"}));
      var tx=el("text",{x:cx-3,y:(ya+yb)/2+4,"class":"lkt","text-anchor":"end"}); tx.textContent="uses"; svg.appendChild(tx);
    });
  });
}
function pick(k){
  cur=k;
  root.querySelectorAll(".hk").forEach(function(b){ b.setAttribute("aria-pressed", +b.dataset.hk===k?"true":"false"); });
  root.querySelectorAll("td.c").forEach(function(td){ td.classList.remove("selc","sels","dim"); td.removeAttribute("data-role"); });
  var s=D[k]; if(!s) return;
  s.ol.forEach(function(l){ var c=cell("L",l); if(c){ c.classList.add("selc"); c.dataset.role=s.role; } });
  s.nl.forEach(function(l){ var c=cell("R",l); if(c){ c.classList.add("selc"); c.dataset.role=s.role; } });
  s.so.forEach(function(l){ var c=cell("L",l); if(c) c.classList.add("sels"); });
  s.sn.forEach(function(l){ var c=cell("R",l); if(c) c.classList.add("sels"); });
  draw();
}
root.querySelectorAll(".hk").forEach(function(b){ b.addEventListener("click", function(){ pick(+b.dataset.hk); }); });
window.addEventListener("resize", draw); window.addEventListener("load", draw);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);
if (window.ResizeObserver) new ResizeObserver(draw).observe(wrap);
pick(0);
"""

CSS = """
:root{--bg:#f6f6f3;--panel:#fff;--fg:#1d2128;--muted:#5f6670;--rule:#dcdcd6;--eq:#2a7d4f;--neq:#b8432f;--unk:#9a6d12;
--id:#2a7d4f;--idsoft:#e4f2e9;--ctx:#2f62a8;--ctxsoft:#e3ecf8;--brk:#b8432f;--brksoft:#f8e4df;--nof:#7b7f87;--nofsoft:#eeeeec;
--sup:#c08a1c;--supsoft:#fbf0d6;--add:#e6f3ea;--del:#f9e7e3;
--sans:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121417;--panel:#1a1d22;--fg:#e4e6ea;--muted:#9aa1ab;--rule:#2c3038;
--eq:#5cc18a;--neq:#ee7a64;--unk:#e0b04a;--id:#5cc18a;--idsoft:#18301f;--ctx:#7aa7ea;--ctxsoft:#1a2a40;--brk:#ee7a64;--brksoft:#3a1f1a;
--nof:#9aa1ab;--nofsoft:#24272d;--sup:#e8b84e;--supsoft:#352a12;--add:#163020;--del:#3a1d19;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121417;--panel:#1a1d22;--fg:#e4e6ea;--muted:#9aa1ab;--rule:#2c3038;--eq:#5cc18a;--neq:#ee7a64;--unk:#e0b04a;
--id:#5cc18a;--idsoft:#18301f;--ctx:#7aa7ea;--ctxsoft:#1a2a40;--brk:#ee7a64;--brksoft:#3a1f1a;--nof:#9aa1ab;--nofsoft:#24272d;
--sup:#e8b84e;--supsoft:#352a12;--add:#163020;--del:#3a1d19;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;line-height:1.55}
.wrap{max-width:1280px;margin:0 auto;padding-inline:16px;padding-block:24px 64px;display:grid;gap:28px}
h1{font-size:22px;margin:0}h2{font-size:16px;margin:0;font-family:var(--mono);word-break:break-all}h3{font-size:13px;margin:0 0 8px;color:var(--muted);font-weight:600;letter-spacing:.02em}
.lead{max-width:72ch;color:var(--muted);margin:6px 0 0}
code{font-family:var(--mono);font-size:12.5px}.muted{color:var(--muted)}.warn{color:var(--unk)}.hl{color:var(--neq)}
.pair{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:16px;display:grid;gap:12px;min-width:0}
.ph{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center}
.chip{font-family:var(--mono);font-size:11.5px;font-weight:600;padding:1px 9px;border-radius:99px;border:1.5px solid currentColor;white-space:nowrap}
.chip.eq{color:var(--eq)}.chip.neq{color:var(--neq)}.chip.unk{color:var(--unk)}
.tl{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:12px}.tl .muted{margin-right:6px}
.tl .it{font-family:var(--mono);font-size:11px;width:22px;text-align:center;border-radius:4px;border:1px solid var(--rule)}.tl .it.ok{border-color:var(--eq);color:var(--eq)}
.grid{display:grid;gap:14px;min-width:0}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,380px),1fr));gap:8px;min-width:0}
.cards h3{grid-column:1/-1}
.hk{display:grid;gap:6px;text-align:left;font:inherit;color:var(--fg);background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;cursor:pointer}
.hk[aria-pressed="true"].id{box-shadow:inset 4px 0 0 var(--id);border-color:var(--id)}.hk[aria-pressed="true"].ctx{box-shadow:inset 4px 0 0 var(--ctx);border-color:var(--ctx)}
.hk[aria-pressed="true"].brk{box-shadow:inset 4px 0 0 var(--brk);border-color:var(--brk)}.hk[aria-pressed="true"].nof,.hk[aria-pressed="true"].unk{box-shadow:inset 4px 0 0 var(--nof)}
.hk:focus-visible{outline:2px solid var(--ctx);outline-offset:2px}
.hk.id{box-shadow:inset 4px 0 0 var(--id)}.hk.ctx{box-shadow:inset 4px 0 0 var(--ctx)}.hk.brk{box-shadow:inset 4px 0 0 var(--brk)}.hk.nof,.hk.unk{box-shadow:inset 4px 0 0 var(--nof)}
.hkh{display:flex;justify-content:space-between;align-items:center;gap:8px}
.badge{font-size:12px;font-weight:600;padding:1px 8px;border-radius:5px}
.badge.id{background:var(--idsoft);color:var(--id)}.badge.ctx{background:var(--ctxsoft);color:var(--ctx)}.badge.brk{background:var(--brksoft);color:var(--brk)}
.badge.nof,.badge.unk{background:var(--nofsoft);color:var(--nof)}
.hkd{display:grid;gap:2px;font-size:12.5px}.hkd .side{display:inline-block;width:32px;font-size:11px;color:var(--muted)}
.hkw p{margin:4px 0;font-size:13px}.hkw ul.sup{margin:2px 0 4px;padding-left:18px}.hkw li{margin:2px 0;font-size:13px}
.ln{font-family:var(--mono);font-size:11px;color:var(--muted)}
.sup{display:flex;gap:8px;align-items:center;background:var(--supsoft);box-shadow:inset 3px 0 0 var(--sup);border-radius:4px;padding:3px 8px;font-size:12.5px}
.itg{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--sup);border:1px solid var(--sup);border-radius:4px;padding:0 5px}
.ce{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap;background:var(--brksoft);border-radius:4px;padding:3px 8px;font-family:var(--mono);font-size:12.5px}.ce .arr{color:var(--muted)}
.code{min-width:0;display:grid;gap:6px}
.svw{position:relative;overflow-x:auto;border:1px solid var(--rule);border-radius:8px}
.svw table{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:12.5px}
.svw th{font-family:var(--sans);font-size:11.5px;color:var(--muted);font-weight:500;text-align:left;padding:4px 8px;border-bottom:1px solid var(--rule)}
.svw td{padding:0 8px;line-height:28px;vertical-align:top}.svw td.n{color:var(--muted);text-align:right;width:1%;user-select:none}
.svw td.g{width:56px;min-width:56px;padding:0}.svw td.c{white-space:pre;width:49%}.svw td.R{border-left:1px solid var(--rule)}
.svw td.gap{background:repeating-linear-gradient(135deg,transparent 0 5px,var(--rule) 5px 6px)}
.svw td.L.chg{background:var(--del)}.svw td.R.chg{background:var(--add)}
.svw span.del{color:var(--neq);font-weight:600}.svw span.add{color:var(--eq);font-weight:600}
.svw td.selc[data-role=id]{background:var(--idsoft);box-shadow:inset 3px 0 0 var(--id)}.svw td.selc[data-role=ctx]{background:var(--ctxsoft);box-shadow:inset 3px 0 0 var(--ctx)}
.svw td.selc[data-role=brk]{background:var(--brksoft);box-shadow:inset 3px 0 0 var(--brk)}.svw td.selc[data-role=nof],.svw td.selc[data-role=unk]{background:var(--nofsoft)}
.svw td.sels{background:var(--supsoft);box-shadow:inset 3px 0 0 var(--sup)}
svg.links{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
svg.links .lk{fill:none;stroke:var(--sup);stroke-width:1.6}svg.links .lkh{fill:var(--sup)}svg.links .lkt{fill:var(--sup);font:600 10.5px var(--sans)}
.lg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11.5px;color:var(--muted)}
.lg .k{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;vertical-align:-2px}
.lg .hl-c{background:var(--ctxsoft);box-shadow:inset 3px 0 0 var(--ctx)}.lg .hl-s{background:var(--supsoft);box-shadow:inset 3px 0 0 var(--sup)}
.lg .lk{border-top:2px solid var(--sup);height:0;width:16px;border-radius:0}
"""


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    jhome = semdiff.java_home(None)
    sections = [build_pair(d, i, jhome) for i, d in enumerate(dirs)]
    page = f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Why Is This Change Okay</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>{CSS}</style>
<div class="wrap"><header><h1>Why is this change okay?</h1></header>
{''.join(sections)}</div>"""
    open(out, "w").write(page)
    print(out)


if __name__ == "__main__":
    main()
