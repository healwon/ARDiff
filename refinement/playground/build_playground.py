#!/usr/bin/env python3
"""Build the single-file playground: template + engine + CodeMirror CSS + examples (+ ARDiff verdicts).

usage: build_playground.py OUT.html [--examples [LABEL=]DIR ...] [--report report.json ...]
  --examples  folder with <name>/<Eq|NEq>/{oldV,newV}.java, repeatable; each is a group in the example menu
              (default: <repo>/examples/same-old). Examples of the second and later folders are named LABEL/<name>/<kind>
  --pick      names (e.g. EvenSum,Overtime) to keep from the first --examples folder; the rest are left out
  --benchmarks folder of benchmarks (e.g. <repo>/benchmarks): each subfolder becomes a group, pairs found at any depth
  --eval      folder of evaluation tasks (<task>/{oldV,newV,fixedV}.java + task.json): builds the task page instead;
              the reference fix is not embedded, only how many tokens it changes
  --report    commit_check report.json files; their ARDiff verdicts are shown for the matching examples
"""
import argparse, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


TOKRE = re.compile(r"[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|\S")


def changed_tokens(a, b):
    """tokens deleted + inserted to turn a into b (comments ignored); the page counts edits the same way"""
    strip = lambda s: re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", " ", s)
    ta, tb = TOKRE.findall(strip(a)), TOKRE.findall(strip(b))
    import difflib
    return sum((i2 - i1) + (j2 - j1) for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes() if op != "equal")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--examples", action="append", default=[])
    ap.add_argument("--pick", default="")
    ap.add_argument("--benchmarks", default="")
    ap.add_argument("--eval", default="")
    ap.add_argument("--report", action="append", default=[])
    ap.add_argument("--repo", default="", help="owner/name for the 'Run ARDiff on GitHub' button (issue-based runs)")
    ap.add_argument("--z3", default="", help="folder with the browser z3 assets (build_z3_assets.sh); copied next to OUT as z3/ to enable ARDiff-lite")
    a = ap.parse_args()

    verdicts = {}
    for rp in a.report:
        try:
            for e in json.load(open(rp)).get("entries", []):
                if e.get("verdict"):
                    verdicts["/".join(e["file"].rstrip("/").split("/")[-2:])] = e["verdict"]
        except (OSError, ValueError):
            pass

    specs = [s.split("=", 1) if "=" in s else (os.path.basename(os.path.normpath(s)), s)
             for s in (a.examples or [os.path.join(REPO, "examples", "same-old")])]
    if a.benchmarks:
        specs += [(b, os.path.join(a.benchmarks, b)) for b in sorted(os.listdir(a.benchmarks), key=str.lower)
                  if os.path.isdir(os.path.join(a.benchmarks, b))]
    pick = {x for x in a.pick.split(",") if x}
    examples = []
    for gi, (label, root) in enumerate(specs):
        group = []
        for d, subdirs, files in os.walk(root):
            subdirs.sort()
            if "oldV.java" not in files or "newV.java" not in files:
                continue
            subdirs[:] = []
            rel = os.path.relpath(d, root).replace(os.sep, "/")
            if gi == 0 and pick and rel.split("/")[0] not in pick:
                continue
            group.append({"name": (f"{label}/" if gi else "") + rel, "group": label,
                          "old": open(os.path.join(d, "oldV.java")).read(), "new": open(os.path.join(d, "newV.java")).read(),
                          "ardiff": verdicts.get("/".join(rel.split("/")[-2:]))})
        # NEq first: the interesting ones
        examples += sorted(group, key=lambda e: (not re.search(r"(^|/)NEq(/|$)", e["name"]), e["name"].lower()))

    evals = None
    if a.eval:
        examples, evals = [], {}
        for t in sorted(os.listdir(a.eval)):
            d = os.path.join(a.eval, t)
            if not os.path.exists(os.path.join(d, "task.json")):
                continue
            meta = json.load(open(os.path.join(d, "task.json")))
            old, new = open(os.path.join(d, "oldV.java")).read(), open(os.path.join(d, "newV.java")).read()
            fixed = open(os.path.join(d, "fixedV.java")).read().replace("fixedV", "newV")
            examples.append({"name": t, "group": "tasks", "old": old, "new": new})
            evals[t] = dict(meta, refTokens=changed_tokens(new, fixed))

    page = open(os.path.join(HERE, "template.html")).read()
    page = page.replace("/*__EVAL__*/null", json.dumps(evals).replace("</", "<\\/"))
    page = page.replace("/*__CM_CSS__*/", open(os.path.join(HERE, "codemirror-5.65.16.min.css")).read())
    page = page.replace("/*__ENGINE__*/", open(os.path.join(HERE, "engine.js")).read().replace("</script", "<\\/script"))
    page = page.replace("/*__EXAMPLES__*/[]", json.dumps(examples).replace("</", "<\\/"))
    page = page.replace('/*__REPO__*/""', json.dumps(a.repo))
    page = page.replace("/*__LITE__*/", open(os.path.join(HERE, "ardifflite.js")).read().replace("</script", "<\\/script"))
    coi = ""
    if a.z3:
        import shutil
        out_dir = os.path.dirname(os.path.abspath(a.out))
        z3dir = os.path.join(out_dir, "z3")
        os.makedirs(z3dir, exist_ok=True)
        for f in ("z3-built.js", "z3-built.wasm", "z3-built.worker.js", "z3lite-bundle.js"):
            shutil.copy(os.path.join(a.z3, f), z3dir)
        # the service worker must sit next to the page: it re-serves it with COOP/COEP so SharedArrayBuffer works
        shutil.copy(os.path.join(a.z3, "coi-serviceworker.min.js"), out_dir)
        coi = '<script src="coi-serviceworker.min.js"></script>'
    page = page.replace("/*__COI__*/", coi)
    open(a.out, "w").write(page)
    print(a.out, len(examples), "examples")


if __name__ == "__main__":
    main()
