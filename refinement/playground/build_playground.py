#!/usr/bin/env python3
"""Build the single-file playground: template + engine + CodeMirror CSS + examples (+ ARDiff verdicts).

usage: build_playground.py OUT.html [--examples DIR] [--report report.json ...]
  --examples  folder with <name>/<Eq|NEq>/{oldV,newV}.java (default: <repo>/examples/readable-vs-fast)
  --report    commit_check report.json files; their ARDiff verdicts are shown for the matching examples
"""
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--examples", default=os.path.join(REPO, "examples", "readable-vs-fast"))
    ap.add_argument("--report", action="append", default=[])
    ap.add_argument("--repo", default="", help="owner/name for the 'Run ARDiff on GitHub' button (issue-based runs)")
    a = ap.parse_args()

    verdicts = {}
    for rp in a.report:
        try:
            for e in json.load(open(rp)).get("entries", []):
                if e.get("verdict"):
                    verdicts[e["file"].rstrip("/").split("examples/readable-vs-fast/")[-1]] = e["verdict"]
        except (OSError, ValueError):
            pass

    examples = []
    for name in sorted(os.listdir(a.examples)):
        d = os.path.join(a.examples, name)
        if not os.path.isdir(d):
            continue
        for kind in sorted(os.listdir(d)):
            p = os.path.join(d, kind)
            if os.path.exists(os.path.join(p, "oldV.java")) and os.path.exists(os.path.join(p, "newV.java")):
                examples.append({"name": f"{name}/{kind}", "old": open(os.path.join(p, "oldV.java")).read(),
                                 "new": open(os.path.join(p, "newV.java")).read(),
                                 "ardiff": verdicts.get(f"{name}/{kind}")})
    # NEq first: the interesting ones
    examples.sort(key=lambda e: (not e["name"].endswith("/NEq"), e["name"]))

    page = open(os.path.join(HERE, "template.html")).read()
    page = page.replace("/*__CM_CSS__*/", open(os.path.join(HERE, "codemirror-5.65.16.min.css")).read())
    page = page.replace("/*__ENGINE__*/", open(os.path.join(HERE, "engine.js")).read().replace("</script", "<\\/script"))
    page = page.replace("/*__EXAMPLES__*/[]", json.dumps(examples).replace("</", "<\\/"))
    page = page.replace('/*__REPO__*/""', json.dumps(a.repo))
    open(a.out, "w").write(page)
    print(a.out, len(examples), "examples")


if __name__ == "__main__":
    main()
