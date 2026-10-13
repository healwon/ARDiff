#!/usr/bin/env python3
"""Build the interactive refinement viewer from run-debug.sh outputs.

usage: build_viewer.py <out.html> <benchmark dir>...
Each dir must contain debug.log and iterations/iter_NN/ (made by run-debug.sh).
"""
import difflib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS_MARK = "-----------------------The current status"
UF_NUM = re.compile(r"\b(UF_\w+)_\d+\b")


def read(p, limit=None):
    try:
        with open(p, errors="replace") as f:
            s = f.read()
    except FileNotFoundError:
        return ""
    if limit and len(s) > limit:
        s = s[:limit] + "\n... (truncated)"
    return s


def norm(s):
    return UF_NUM.sub(r"\1", s)


def changed_lines(prev, cur):
    """1-based line numbers of cur that differ from prev (UF renumbering ignored)."""
    if prev is None:
        return []
    a, b = norm(prev).splitlines(), norm(cur).splitlines()
    out = []
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out.extend(range(j1 + 1, j2 + 1))
    return out


def parse_chunk(c):
    lines = [l.strip() for l in c.splitlines()]
    body = [l for l in lines if l]
    d = {"status": None, "satcheck": None, "funcs": [], "h1": [], "h2": [], "cand": [],
         "R": [], "pick": None, "nextConcrete": None, "h1res": []}
    if body:
        d["status"] = body[0].split()[0]
    for i, l in enumerate(body):
        if l == "checking for satisfiability" and i + 1 < len(body):
            d["satcheck"] = body[i + 1]
        elif l.startswith("Functions :"):
            d["funcs"] = re.findall(r"UF_\w+", l)
        elif l in ("sat", "unsat", "unknown") and d["funcs"] and not d["h2"] and not d["cand"]:
            d["h1res"].append(l)
        elif "possible refined function based on H1" in l:
            d["h1"].append(l.split(":")[-1].strip())
        elif "refined function based on H2" in l:
            f = l.split(":")[-1].strip()
            if f not in d["h2"]:
                d["h2"].append(f)
        elif l.startswith("all possible functions from H1 and H2"):
            d["cand"] = re.findall(r"UF_\w+", l)
        elif l.startswith("R: {"):
            d["R"] = [[int(a), int(b)] for a, b in re.findall(r"(\d+)=(\d+)", l)]
        elif l.startswith("the candidate based on") or l.startswith("the random candidate statement"):
            d["pick"] = int(l.split(":")[-1].strip())
        elif re.fullmatch(r"\[[\d, ]*\]", l):
            d["nextConcrete"] = [int(x) for x in re.findall(r"\d+", l)]
    if d["status"] in ("SATISFIABLE", "UNSATISFIABLE", "UNKNOWN") and d["status"] == body[0] and len(body) > 1 \
            and body[1] in ("SATISFIABLE", "UNSATISFIABLE", "UNKNOWN") and d["satcheck"] is None:
        d["satcheck"] = body[1]
    return d


def build(dirpath):
    log = read(os.path.join(dirpath, "debug.log"))
    log = log[log.find("------ARDIFF"):] if "------ARDIFF" in log else log
    chunks = log.split(STATUS_MARK)[1:]
    parsed = [parse_chunk(c.split("\n", 1)[1] if "\n" in c else c) for c in chunks]
    itdir = os.path.join(dirpath, "iterations")
    names = sorted(os.listdir(itdir))
    first = os.path.join(itdir, names[0])
    verdict = (re.findall(r"Output : ([A-Z ]+)", log) or ["?"])[-1].strip()
    iters, prev_old, prev_new = [], None, None
    for i, n in enumerate(names):
        p = os.path.join(itdir, n)
        info = parsed[i] if i < len(parsed) else {}
        if i == 0:
            nxt = info.get("nextConcrete") or []
            concrete = [x for x in nxt if x != info.get("pick")]
        else:
            concrete = parsed[i - 1].get("nextConcrete") or []
        iold, inew = read(os.path.join(p, "IoldVARDiff.java")), read(os.path.join(p, "InewVARDiff.java"))
        iters.append({
            **{k: info.get(k) for k in ("status", "satcheck", "funcs", "h1", "h1res", "h2", "cand", "R", "pick")},
            "concrete": concrete,
            "iold": iold, "inew": inew,
            "iold_changed": changed_lines(prev_old, iold), "inew_changed": changed_lines(prev_new, inew),
            "z3": read(os.path.join(p, "z3summary.txt"), 60000),
            "jpf": read(os.path.join(p, "IoldVARDiffJPFOutput.txt"), 30000),
            "result": read(os.path.join(p, "result.txt")),
        })
        prev_old, prev_new = iold, inew
    rel = os.path.relpath(dirpath, os.path.join(HERE, "bench"))
    return {"name": rel, "verdict": verdict,
            "old": read(os.path.join(first, "oldV.java")), "new": read(os.path.join(first, "newV.java")),
            "initial": iters[0]["concrete"] if iters else [], "iters": iters}


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    data = [build(os.path.abspath(d)) for d in dirs]
    tpl = read(os.path.join(HERE, "viewer_template.html"))
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open(out, "w") as f:
        f.write(tpl.replace("/*__DATA__*/[]", blob))
    for b in data:
        print(b["name"], len(b["iters"]), b["verdict"], [it["pick"] for it in b["iters"]])


if __name__ == "__main__":
    main()
