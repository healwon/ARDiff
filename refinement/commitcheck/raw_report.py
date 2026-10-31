#!/usr/bin/env python3
"""ARDiff's own output, file by file, for comparing against the visualization.

usage: raw_report.py OUT.html PAIR_DIR...     (also written by unified_report.py as raw.html)
Pair k is addressed as OUT.html#u<k> (its id on the unified page) or by name, e.g. OUT.html#Overtime/NEq.
"""
import glob, html, json, os, re, sys

CAP = 200_000          # bytes shown per file
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# files of one ARDiff iteration, in reading order: verdict, formulas, then the inputs to each step
ITER_FILES = ["result.txt", "z3summary.txt", "IoldVARDiffToSolve.txt", "InewVARDiffToSolve.txt", "H1Checking.smt2",
              "IoldVARDiff.java", "InewVARDiff.java", "IoldVARDiffJPFOutput.txt", "InewVARDiffJPFOutput.txt",
              "IoldVARDiffTerminal.txt", "InewVARDiffTerminal.txt", "IoldVARDiffJPFError.txt", "InewVARDiffJPFError.txt",
              "gumtree.txt", "blocknewV.txt", "IoldVARDiff.jpf", "InewVARDiff.jpf"]


def read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            s = f.read(CAP + 1)
    except OSError:
        return None
    s = ANSI.sub("", s)
    return s[:CAP] + "\n… (cut at 200 kB)" if len(s) > CAP else s


def pair(d):
    meta = {}
    try:
        meta = json.load(open(os.path.join(d, "meta.json")))
    except (OSError, ValueError):
        pass
    groups = []
    run = [(n, read(os.path.join(d, p))) for n, p in
           [("oldV.java", "oldV.java"), ("newV.java", "newV.java")] +
           [(os.path.basename(p), os.path.relpath(p, d)) for p in sorted(glob.glob(os.path.join(d, "outputs", "*.txt")))] +
           [("debug.log", "debug.log"), ("final z3 model", "z3models/ARDiff.txt")]]
    groups.append({"name": "run", "files": [{"n": n, "t": t} for n, t in run if t is not None]})
    for it in sorted(glob.glob(os.path.join(d, "iterations", "iter_*"))):
        have = set(os.listdir(it))
        names = [f for f in ITER_FILES if f in have] + sorted(have - set(ITER_FILES))
        files = [{"n": f, "t": read(os.path.join(it, f))} for f in names if os.path.isfile(os.path.join(it, f))]
        status = ""
        for f in files:
            if f["n"] == "result.txt":
                m = re.search(r"Output : (.+)", f["t"] or "")
                status = m.group(1).strip() if m else ""
        groups.append({"name": "iteration " + str(int(os.path.basename(it)[5:])), "status": status, "files": files})
    log = read(os.path.join(d, "debug.log")) or ""
    m = re.findall(r"Output : (.+)", log)
    return {"name": meta.get("file") or os.path.basename(d), "verdict": m[-1].strip() if m else "not run", "groups": groups}


def page(dirs):
    data = [dict(pair(d), uid=f"u{i}") for i, d in enumerate(dirs)]
    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARDiff Raw Output</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>{CSS}</style>
<header class="hd"><h1>ARDiff raw output</h1>
<select id="pick" aria-label="pair">{''.join(f'<option value="{p["uid"]}">{html.escape(p["name"])}</option>' for p in data)}</select>
<span id="vd" class="chip"></span><a class="back" href="index.html">visualization →</a></header>
<div class="main"><nav id="files" aria-label="files"></nav><section class="view"><div id="fn" class="fn"></div><pre id="txt"></pre></section></div>
<script>var DATA={json.dumps(data).replace("</", "<\\/")};{JS}</script>"""


CSS = r"""
:root{--bg:#f6f6f3;--panel:#fff;--fg:#1d2128;--muted:#5f6670;--rule:#dcdcd6;--eq:#2a7d4f;--neq:#b8432f;--unk:#9a6d12;--acc:#3d6fb6;--sel:#e7eef8;
--sans:"IBM Plex Sans","Helvetica Neue",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121417;--panel:#1a1d22;--fg:#e4e6ea;--muted:#9aa1ab;--rule:#2c3038;--eq:#5cc18a;--neq:#ee7a64;--unk:#e0b04a;--acc:#7fa8e8;--sel:#223047}}
:root[data-theme="dark"]{--bg:#121417;--panel:#1a1d22;--fg:#e4e6ea;--muted:#9aa1ab;--rule:#2c3038;--eq:#5cc18a;--neq:#ee7a64;--unk:#e0b04a;--acc:#7fa8e8;--sel:#223047}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;display:flex;flex-direction:column}
.hd{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--rule)}
h1{font-size:18px;margin:0}select{font:inherit;font-family:var(--mono);font-size:13px;padding:4px 6px;background:var(--panel);color:var(--fg);border:1px solid var(--rule);border-radius:4px;max-width:100%}
.chip{font-family:var(--mono);font-size:12px;border:1px solid currentColor;border-radius:10px;padding:1px 8px}.chip.eq{color:var(--eq)}.chip.neq{color:var(--neq)}.chip.unk{color:var(--unk)}
.back{margin-left:auto;color:var(--acc);font-size:13px}
.main{flex:1;display:flex;min-height:0}
nav{width:250px;flex:none;overflow:auto;border-right:1px solid var(--rule);padding:8px 0;background:var(--panel)}
nav h3{font-size:12px;margin:10px 14px 4px;color:var(--muted);font-weight:600;display:flex;gap:6px;align-items:baseline}
nav h3 .st{font-family:var(--mono);font-weight:400;font-size:11px}nav h3 .st.eq{color:var(--eq)}nav h3 .st.neq{color:var(--neq)}
nav button{display:block;width:100%;text-align:left;border:0;background:none;color:var(--fg);font-family:var(--mono);font-size:12px;padding:3px 14px 3px 22px;cursor:pointer}
nav button:hover{background:var(--sel)}nav button[aria-pressed="true"]{background:var(--sel);box-shadow:inset 3px 0 0 var(--acc)}
nav button:focus-visible,select:focus-visible{outline:2px solid var(--acc);outline-offset:-2px}
.view{flex:1;min-width:0;display:flex;flex-direction:column}
.fn{font-family:var(--mono);font-size:12px;color:var(--muted);padding:8px 16px;border-bottom:1px solid var(--rule)}
pre{flex:1;margin:0;overflow:auto;padding:12px 16px;font-family:var(--mono);font-size:12.5px;line-height:1.5;tab-size:4}
@media (max-width:700px){.main{flex-direction:column}nav{width:auto;max-height:35vh;border-right:0;border-bottom:1px solid var(--rule)}}
"""

JS = r"""
var cur = null, sel = [0, 0];
function cls(v) { return v === "EQUIVALENT" ? "eq" : v === "NOT EQUIVALENT" ? "neq" : "unk"; }
function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function show(uid) {
  // by page id (u3) or by example name (Overtime/NEq, as the playground links)
  uid = decodeURIComponent(uid);
  cur = DATA.filter(function (p) { return p.uid === uid || p.name === uid || p.name.slice(-uid.length - 1) === "/" + uid; })[0] || (uid ? null : DATA[0]);
  if (!cur) {
    document.getElementById("vd").textContent = ""; document.getElementById("vd").className = "chip"; document.getElementById("files").innerHTML = "";
    document.getElementById("fn").textContent = uid; document.getElementById("txt").textContent = DATA.length ? "ARDiff has not been run on " + uid + " for this page." : "(no ARDiff runs)";
    return;
  }
  document.getElementById("pick").value = cur.uid;
  var vd = document.getElementById("vd"); vd.textContent = "ARDiff: " + cur.verdict; vd.className = "chip " + cls(cur.verdict);
  document.getElementById("files").innerHTML = cur.groups.map(function (g, gi) {
    return "<h3>" + esc(g.name) + (g.status ? "<span class='st " + cls(g.status) + "'>" + esc(g.status) + "</span>" : "") + "</h3>" +
      g.files.map(function (f, fi) { return "<button type='button' data-g='" + gi + "' data-f='" + fi + "'>" + esc(f.n) + "</button>"; }).join("");
  }).join("");
  document.querySelectorAll("nav button").forEach(function (b) { b.addEventListener("click", function () { open(+b.dataset.g, +b.dataset.f); }); });
  // start on ARDiff's own summary of the run when there is one
  var g0 = cur.groups[0], fi = g0.files.findIndex(function (f) { return /^ARDiff/.test(f.n); });
  open(0, fi < 0 ? 0 : fi);
}
function open(g, f) {
  sel = [g, f];
  var file = cur.groups[g] && cur.groups[g].files[f];
  document.getElementById("fn").textContent = file ? cur.groups[g].name + " / " + file.n : "";
  document.getElementById("txt").textContent = file ? (file.t || "(empty)") : "(no files)";
  document.getElementById("txt").scrollTop = 0;
  document.querySelectorAll("nav button").forEach(function (b) { b.setAttribute("aria-pressed", +b.dataset.g === g && +b.dataset.f === f ? "true" : "false"); });
}
document.getElementById("pick").addEventListener("change", function (e) { location.hash = e.target.value; });
window.addEventListener("hashchange", function () { show(location.hash.slice(1)); });
show(location.hash.slice(1));
"""


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    open(out, "w").write(page(dirs))
    print(out)


if __name__ == "__main__":
    main()
