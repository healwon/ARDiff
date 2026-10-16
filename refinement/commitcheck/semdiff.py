#!/usr/bin/env python3
"""Explain an ARDiff result: verdict, and for NOT EQUIVALENT the semantic difference.

Input is one run directory made by `ardiff-workflow.sh` (debug.log + iterations/iter_NN/).
For a NEQ verdict it collects, from the last iteration:
  1. the Z3 counterexample ARDiff stored in z3summary.txt,
  2. the symbolic paths of both versions (JPF output: path condition + return, with source lines),
  3. "difference regions": pairs (old path, new path) whose conditions overlap but whose return
     values can differ, each with a witness input (needs the z3 binary),
  4. concrete runs of the original old/new methods on witness inputs and on JPF's generated
     test inputs, to confirm the difference on real code (needs a JDK).

usage: semdiff.py RUN_DIR [--z3 PATH] [--java-home DIR] [--json OUT] [--no-z3] [--no-exec]
"""
import argparse, difflib, itertools, json, os, random, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import javasrc  # noqa: E402

INTERNAL = re.compile(r"^(REAL|INT|LONG|SHORT|BYTE|CHAR|BOOL|DOUBLE|FLOAT)_\d+$")
JAVA_PRIMS = {"int", "long", "short", "byte", "char", "double", "float", "boolean"}


def pinned(cmd):
    """Prefix with `taskset -c $CORES` (default 120-159 when the machine has those cores), like ardiff-workflow.sh."""
    cores = os.environ.get("CORES") or ("120-159" if (os.cpu_count() or 0) > 159 else "")
    return ["taskset", "-c", cores, *cmd] if cores and shutil.which("taskset") else list(cmd)


# ------------------------------------------------------------------ s-expressions
def sx_tokens(s):
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
        elif c in "()":
            yield c; i += 1
        elif c == ";":
            j = s.find("\n", i); i = n if j < 0 else j
        elif c == '"':
            j = i + 1
            while j < n and not (s[j] == '"' and s[j - 1] != "\\"):
                j += 1
            yield s[i:j + 1]; i = j + 1
        elif c == "|":
            j = s.find("|", i + 1); yield s[i:j + 1]; i = j + 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in "();":
                j += 1
            yield s[i:j]; i = j


def sx_parse_all(s):
    stack, out = [[]], None
    for t in sx_tokens(s):
        if t == "(":
            stack.append([])
        elif t == ")":
            if len(stack) == 1:
                continue          # stray paren
            x = stack.pop(); stack[-1].append(x)
        else:
            stack[-1].append(t)
    out = stack[0]
    while len(stack) > 1:           # unterminated input: close what is open
        x = stack.pop(); stack[-1].append(x)
    return out


def sx_str(x):
    if isinstance(x, list):
        return "(" + " ".join(sx_str(e) for e in x) + ")"
    return x


def sx_subst(x, env):
    if isinstance(x, str):
        return env.get(x, x)
    if x and x[0] == "let" and len(x) == 3:
        new_env = dict(env)
        for b in x[1]:
            new_env[b[0]] = sx_subst(b[1], env)
        return sx_subst(x[2], new_env)
    return [sx_subst(e, env) for e in x]


def sx_flatten(x, op):
    if isinstance(x, list) and x and x[0] == op:
        out = []
        for e in x[1:]:
            out.extend(sx_flatten(e, op))
        return out
    return [x]


def sx_symbols(x, acc=None):
    acc = set() if acc is None else acc
    if isinstance(x, list):
        for e in x:
            sx_symbols(e, acc)
    else:
        acc.add(x)
    return acc


def sx_rename(x, old, new):
    if isinstance(x, list):
        return [sx_rename(e, old, new) for e in x]
    return new if x == old else x


def sx_value(x):
    """Z3 model value -> python number/bool (None if not a plain constant)."""
    if isinstance(x, str):
        if x in ("true", "false"):
            return x == "true"
        try:
            return int(x)
        except ValueError:
            try:
                return float(x)
            except ValueError:
                return None
    if len(x) == 2 and x[0] == "-":
        v = sx_value(x[1]); return None if v is None else -v
    if len(x) == 3 and x[0] == "/":
        a, b = sx_value(x[1]), sx_value(x[2])
        return None if a is None or not b else a / b
    if len(x) == 2 and x[0] == "to_real":
        return sx_value(x[1])
    return None


# ------------------------------------------------------------------ ARDiff artefacts
def read(p):
    try:
        with open(p, errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def last_iteration(run_dir):
    it = os.path.join(run_dir, "iterations")
    names = sorted(n for n in os.listdir(it) if n.startswith("iter_")) if os.path.isdir(it) else []
    return (os.path.join(it, names[-1]), len(names)) if names else (os.path.join(run_dir, "instrumented"), 0)


def verdict_of(log):
    v = re.findall(r"Output : ([A-Z ]+)", log)
    if v:
        return v[-1].strip()
    if "Exception" in log or "error" in log.lower():
        return "ERROR"
    return "TIMEOUT"


def parse_model(z3summary):
    m = re.search(r"Model \(the counterexample[^\n]*\n(.*?)\n-{20,}", z3summary, re.S)
    if not m:
        return None
    defs = {}

    def walk(x):
        if isinstance(x, list):
            if len(x) >= 5 and x[0] == "define-fun":
                defs[x[1]] = {"args": x[2], "sort": sx_str(x[3]), "value": x[4]}
            else:
                for e in x:
                    walk(e)
    walk(sx_parse_all(m.group(1)))
    return defs


def unwrap(x):
    """ARDiff writes "(" + summary + ")": ((= Ret 1)) -> (= Ret 1)."""
    while isinstance(x, list) and len(x) == 1 and isinstance(x[0], list):
        x = x[0]
    return x


def parse_tosolve(text):
    """-> (declarations text, old summary sx, new summary sx) from *ToSolve.txt."""
    k = text.find("(assert")
    if k < 0:
        return None
    decls = text[:k]
    forms = [f for f in sx_parse_all(text[k:]) if isinstance(f, list) and f and f[0] == "assert"]
    if len(forms) < 2:
        return None
    old = unwrap(forms[0][1])
    neg = forms[1][1]                      # (not (= OLD NEW))
    if not (isinstance(neg, list) and neg[0] == "not" and isinstance(neg[1], list) and neg[1][0] == "="):
        return None
    return decls, sx_subst(old, {}), sx_subst(unwrap(neg[1][2]), {})


def parse_summaries_from_z3summary(text):
    """Fallback when *ToSolve.txt is missing: summaries printed by z3 (with let)."""
    def section(title):
        m = re.search(re.escape(title) + r"[^\n]*\n(.*?)\n-{20,}", text, re.S)
        return m.group(1) if m else None
    o = section("The Z3 formula for the old method")
    n = section("The Z3 formula for the new method")
    f = section("The final Z3 formula for constraint solving")
    if not (o and n):
        return None
    decls = ""
    if f:
        k = f.find("(assert")
        decls = f if k < 0 else f[:k]
        decls = "\n".join(l for l in decls.splitlines() if l.startswith(("(declare", "(define")))
    return decls, sx_subst(sx_parse_all(o)[0], {}), sx_subst(sx_parse_all(n)[0], {})


JPF_VAR = re.compile(r"\b([A-Za-z_$][\w$]*?)_(\d+)_SYM(?:INT|REAL|BOOL|STRING|LONG|DOUBLE|FLOAT)(?:\[[^\]]*\])?")
UF_CALL = re.compile(r"\b(UF_\w+?)_\d+_SYM(?:INT|REAL|BOOL|LONG|DOUBLE|FLOAT)\(")


def pretty_jpf(expr):
    e = UF_CALL.sub(lambda m: m.group(1) + "(", expr)
    e = JPF_VAR.sub(lambda m: "ret" if m.group(1) == "Ret" else m.group(1), e)
    e = re.sub(r"\b((?:REAL|INT|LONG|DOUBLE|FLOAT)_\d+)\[[^\]]*\]", r"\1", e)
    e = re.sub(r"\bCONST_", "", e)
    return e.strip().rstrip("&").strip()


def parse_jpf_paths(text, src_lines):
    paths = []
    for block in re.findall(r"\*+Summary\*+\n(.*?)\n\*{20,}", text, re.S):
        cons, ret = [], None
        for line in block.splitlines():
            m = re.match(r"\s*(\d+):\s*(.*)$", line)
            if not m:
                continue
            ln, expr = int(m.group(1)), m.group(2).strip()
            item = {"line": ln, "src": src_lines[ln - 1].strip() if 0 < ln <= len(src_lines) else "",
                    "expr": pretty_jpf(expr)}
            if re.match(r"Ret_\d+_SYM\w+\s*=", expr):
                item["expr"] = re.sub(r"^ret\s*=\s*", "", item["expr"])
                ret = item
            else:
                cons.append(item)
        paths.append({"constraints": cons, "ret": ret})
    return paths


def line_map(instrumented_lines, pair_lines):
    """1-based instrumented line -> 1-based line of the pair source (oldV/newV.java) with the same code."""
    def key(l):
        return re.sub(r"\s+", "", javasrc.strip_comments(l))
    a, b = [key(l) for l in instrumented_lines], [key(l) for l in pair_lines]
    out = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                if a[i1 + k]:
                    out[i1 + k + 1] = j1 + k + 1
        elif tag == "replace":
            # "x = UF_x_3(...)" stands for the original line(s) assigning x inside this block
            used = set()
            for i in range(i1, i2):
                m = re.match(r"(?:[\w$<>\[\]]+)??([A-Za-z_$][\w$]*)=UF_", a[i])
                cand = None
                if m:
                    var = m.group(1)
                    for j in range(j1, j2):
                        if j not in used and re.search(r"(?<![\w$])" + re.escape(var) + r"(?:\+|-|\*|/)?=(?!=)", b[j]):
                            cand = j; break
                if cand is None and a[i]:
                    best = max(((difflib.SequenceMatcher(None, a[i], b[j]).ratio(), j) for j in range(j1, j2) if j not in used),
                               default=(0, None))
                    cand = best[1] if best[0] >= 0.75 else None
                if cand is not None:
                    used.add(cand); out[i + 1] = cand + 1
    return out


def attach_pair_lines(paths, lmap):
    for p in paths:
        for item in p["constraints"] + ([p["ret"]] if p["ret"] else []):
            item["pair_line"] = lmap.get(item["line"])


def parse_jpf_tests(text):
    """Concrete inputs JPF generated per path (HTML table at the end of the output)."""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", text, re.S)
    out = []
    for t in tables:
        rows = re.findall(r"<tr>(.*?)</tr>", t, re.S)
        if not rows:
            continue
        head = [re.sub(r"_\d+_SYM\w+$", "", h) for h in re.findall(r"<td>(.*?)</td>", rows[0])]
        for r in rows[1:]:
            cells = re.findall(r"<td>(.*?)</td>", r)
            vals = {}
            for h, c in zip(head, cells):
                if h == "RETURN":
                    continue
                try:
                    vals[h] = float(c) if re.search(r"[.eE]", c) else int(c)
                except ValueError:
                    pass
            if vals:
                out.append(vals)
    return out


# ------------------------------------------------------------------ z3 region analysis
def find_z3(explicit=None):
    cands = [explicit, os.environ.get("ARDIFF_Z3"),
             os.path.join(HERE, "..", "..", "Implementation", "z3"), shutil.which("z3")]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return os.path.abspath(c)
    return None


def run_z3(z3, script, timeout):
    try:
        p = subprocess.run(pinned([z3, "-in", "-smt2"]), input=script, capture_output=True, text=True, timeout=timeout)
        return p.stdout
    except subprocess.TimeoutExpired as e:
        return (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")


def declared_consts(decls):
    out = {}
    for m in re.finditer(r"\(declare-fun\s+(\S+)\s+\(\s*\)\s+(\w+)\s*\)", decls):
        out[m.group(1)] = m.group(2)
    return out


def region_analysis(z3, decls, old_sx, new_sx, inputs, max_pairs=900, per_query_ms=4000):
    olds, news = sx_flatten(old_sx, "or"), sx_flatten(new_sx, "or")
    consts = declared_consts(decls)
    ret_sort = consts.get("Ret", "Real")
    shown = [v for v in inputs if v in consts] or [c for c in consts if c != "Ret" and not INTERNAL.match(c)]
    pairs = [(i, j) for i in range(len(olds)) for j in range(len(news))][:max_pairs]
    head = (f"(set-option :timeout {per_query_ms})\n{decls}\n"
            f"(declare-fun Ret__old () {ret_sort})\n(declare-fun Ret__new () {ret_sort})\n")

    def block(i, j, with_values):
        o = sx_str(sx_rename(olds[i], "Ret", "Ret__old"))
        n = sx_str(sx_rename(news[j], "Ret", "Ret__new"))
        s = f'(echo "@@{i},{j}")\n(push)\n(assert {o})\n(assert {n})\n(assert (not (= Ret__old Ret__new)))\n(check-sat)\n'
        if with_values:
            s += f"(get-value ({' '.join(shown + ['Ret__old', 'Ret__new'])}))\n"
        return s + "(pop)\n"

    timeout = 30 + len(pairs) * per_query_ms / 1000
    out = run_z3(z3, head + "".join(block(i, j, False) for i, j in pairs), timeout)
    status = {}
    for m in re.finditer(r"@@(\d+),(\d+)\s*\n\s*(sat|unsat|unknown)", out):
        status[(int(m.group(1)), int(m.group(2)))] = m.group(3)
    sat = [p for p in pairs if status.get(p) == "sat"]
    regions = []
    if sat:
        out = run_z3(z3, head + "".join(block(i, j, True) for i, j in sat), 30 + len(sat) * per_query_ms / 1000)
        chunks = re.split(r"@@(\d+),(\d+)", out)
        vals_by_pair = {}
        for k in range(1, len(chunks) - 2, 3):
            i, j, body = int(chunks[k]), int(chunks[k + 1]), chunks[k + 2]
            got = {}
            for form in sx_parse_all(body):
                if isinstance(form, list) and form and all(isinstance(e, list) and len(e) == 2 for e in form):
                    for name, val in form:
                        got[sx_str(name)] = sx_value(val) if sx_value(val) is not None else sx_str(val)
            vals_by_pair[(i, j)] = got
        for i, j in sat:
            v = vals_by_pair.get((i, j), {})
            regions.append({"old": i, "new": j,
                            "witness": {k: v[k] for k in shown if k in v},
                            "ret_old": v.get("Ret__old"), "ret_new": v.get("Ret__new")})
    unknown = sum(1 for p in pairs if status.get(p) == "unknown")
    errors = sorted(set(re.findall(r'\(error "([^"]*)"\)', out)))[:5]
    return {"n_old": len(olds), "n_new": len(news), "checked": len(pairs),
            "truncated": len(olds) * len(news) > len(pairs), "unknown": unknown, "regions": regions,
            "z3_errors": errors, "no_answer": len(pairs) - len(status)}


# ------------------------------------------------------------------ concrete execution
def java_home(explicit=None):
    if explicit:
        return explicit
    env = os.path.expanduser("~/.local/jdk8/ardiff-env.sh")
    m = re.search(r"export JAVA_HOME=(\S+)", read(env))
    return m.group(1) if m else os.environ.get("JAVA_HOME")


def java_literal(t, v):
    if t == "boolean":
        return "Boolean.TRUE" if v else "Boolean.FALSE"
    if v is None:
        v = 0
    if t in ("double", "float"):
        v = float(v)
        lit = repr(v) if v == v and abs(v) != float("inf") else "0.0"
        return f"Double.valueOf({lit})" if t == "double" else f"Float.valueOf((float){lit})"
    v = int(round(v)) if isinstance(v, float) else int(v)
    box = {"int": "Integer", "long": "Long", "short": "Short", "byte": "Byte", "char": "Character"}[t]
    lim = {"int": 2**31, "long": 2**63, "short": 2**15, "byte": 2**7, "char": 2**16}[t]
    if not (-lim <= v < lim):
        return None
    cast = {"int": "", "long": "L", "short": "", "byte": "", "char": ""}[t]
    if t in ("short", "byte", "char"):
        return f"{box}.valueOf(({t}){v})"
    return f"{box}.valueOf({v}{cast})"


def target_method(path, cls_name):
    src = read(path)
    pkg = re.search(r"^\s*package\s+([\w.]+)\s*;", src, re.M)
    for c in javasrc.parse(src):
        if c.name == cls_name and c.methods:
            return (pkg.group(1) + "." if pkg else "") + cls_name, c.methods[0]
    return None, None


def run_concrete(run_dir, candidates, jhome, timeout=30):
    """Run original oldV/newV first methods on each candidate input dict."""
    old_p, new_p = os.path.join(run_dir, "oldV.java"), os.path.join(run_dir, "newV.java")
    old_fqn, m = target_method(old_p, "oldV")
    new_fqn, _ = target_method(new_p, "newV")
    if not (m and new_fqn):
        return {"error": "oldV/newV 메서드를 찾지 못함"}
    if any(t not in JAVA_PRIMS for t, _ in m.params) or not jhome:
        return {"error": "원시 타입 파라미터가 아니거나 JDK가 없어 실행 검증을 건너뜀"}
    calls, used = [], []
    for k, cand in enumerate(candidates):
        lits = [java_literal(t, cand["inputs"].get(n)) for t, n in m.params]
        if any(l is None for l in lits):
            continue
        used.append(cand)
        calls.append(f'    run({len(used) - 1}, new Object[]{{{", ".join(lits)}}});')
    if not used:
        return {"error": "실행할 입력이 없음"}
    types = ", ".join(f"{t}.class" for t, _ in m.params)
    harness = f"""import java.lang.reflect.*;
public class ArdiffHarness {{
  static Object call(String cls, Object[] args) throws Throwable {{
    Class<?> c = Class.forName(cls);
    Method m = c.getDeclaredMethod("{m.name}", new Class<?>[]{{{types}}});
    m.setAccessible(true);
    Object recv = null;
    if (!Modifier.isStatic(m.getModifiers())) {{ Constructor<?> k = c.getDeclaredConstructor(); k.setAccessible(true); recv = k.newInstance(); }}
    try {{ return m.invoke(recv, args); }} catch (InvocationTargetException e) {{ return "EXCEPTION " + e.getCause(); }}
  }}
  static void run(int id, Object[] args) {{
    String o, n;
    try {{ o = String.valueOf(call("{old_fqn}", args)); }} catch (Throwable t) {{ o = "ERROR " + t; }}
    try {{ n = String.valueOf(call("{new_fqn}", args)); }} catch (Throwable t) {{ n = "ERROR " + t; }}
    System.out.println("@@" + id + "\\t" + o + "\\t" + n);
  }}
  public static void main(String[] a) {{
{chr(10).join(calls)}
  }}
}}
"""
    tmp = tempfile.mkdtemp(prefix="ardiff-exec-")
    try:
        with open(os.path.join(tmp, "ArdiffHarness.java"), "w") as f:
            f.write(harness)
        javac, java = os.path.join(jhome, "bin", "javac"), os.path.join(jhome, "bin", "java")
        out_dir = os.path.join(tmp, "out"); os.makedirs(out_dir)
        p = subprocess.run(pinned([javac, "-nowarn", "-d", out_dir, old_p, new_p, os.path.join(tmp, "ArdiffHarness.java")]),
                           capture_output=True, text=True, timeout=120)
        if p.returncode:
            return {"error": "컴파일 실패: " + p.stderr.strip()[:800]}
        p = subprocess.run(pinned([java, "-cp", out_dir, "ArdiffHarness"]), capture_output=True, text=True, timeout=timeout)
        res = []
        for line in p.stdout.splitlines():
            if line.startswith("@@"):
                i, o, n = line[2:].split("\t", 2)
                c = used[int(i)]
                res.append({**c, "old": o, "new": n, "differs": o != n})
        return {"runs": res, "params": [n for _, n in m.params]}
    except subprocess.TimeoutExpired:
        return {"error": f"실행 시간 초과({timeout}s): 무한 루프일 수 있음"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_traces(run_dir, inputs_list, jhome, timeout=120):
    """Executed source lines (in order) of oldV/newV for each input, via LineTracer (JDI single-stepping).
    -> list aligned with inputs_list of {"old": {"lines", "ret", "truncated"}, "new": {...}}, or {"error": ..}."""
    old_p, new_p = os.path.join(run_dir, "oldV.java"), os.path.join(run_dir, "newV.java")
    old_fqn, m = target_method(old_p, "oldV")
    new_fqn, _ = target_method(new_p, "newV")
    tools = os.path.join(jhome or "", "lib", "tools.jar")
    if not (m and new_fqn and jhome and os.path.exists(tools)):
        return {"error": "JDK 8 tools.jar 또는 메서드를 찾지 못해 실행 흐름을 기록하지 못함"}
    if any(t not in JAVA_PRIMS for t, _ in m.params):
        return {"error": "원시 타입 파라미터가 아니어서 실행 흐름을 기록하지 못함"}
    calls = []
    for inp in inputs_list:
        lits = [java_literal(t, inp.get(n)) for t, n in m.params]
        calls.append("null" if any(l is None for l in lits) else "new Object[]{" + ", ".join(lits) + "}")
    types = ", ".join(f"{t}.class" for t, _ in m.params)
    main_src = f"""import java.lang.reflect.*;
public class ArdiffTraceMain {{
  public static void main(String[] a) throws Exception {{
    Class<?> c = Class.forName(a[0].equals("old") ? "{old_fqn}" : "{new_fqn}");
    Method m = c.getDeclaredMethod("{m.name}", new Class<?>[]{{{types}}});
    m.setAccessible(true);
    Object recv = null;
    if (!Modifier.isStatic(m.getModifiers())) {{ Constructor<?> k = c.getDeclaredConstructor(); k.setAccessible(true); recv = k.newInstance(); }}
    Object[][] inputs = new Object[][]{{{", ".join(calls)}}};
    for (Object[] in : inputs) {{
      if (in == null) continue;
      try {{ m.invoke(recv, in); }} catch (Throwable t) {{ }}
    }}
  }}
}}
"""
    tmp = tempfile.mkdtemp(prefix="ardiff-trace-")
    try:
        javac, java = os.path.join(jhome, "bin", "javac"), os.path.join(jhome, "bin", "java")
        tgt, trc = os.path.join(tmp, "target"), os.path.join(tmp, "tracer")
        os.makedirs(tgt); os.makedirs(trc)
        open(os.path.join(tmp, "ArdiffTraceMain.java"), "w").write(main_src)
        p = subprocess.run(pinned([javac, "-g", "-nowarn", "-d", tgt, old_p, new_p, os.path.join(tmp, "ArdiffTraceMain.java")]),
                           capture_output=True, text=True, timeout=120)
        if p.returncode:
            return {"error": "실행 흐름용 컴파일 실패: " + p.stderr.strip()[:500]}
        p = subprocess.run(pinned([javac, "-nowarn", "-cp", tools, "-d", trc, os.path.join(HERE, "LineTracer.java")]),
                           capture_output=True, text=True, timeout=120)
        if p.returncode:
            return {"error": "LineTracer 컴파일 실패: " + p.stderr.strip()[:500]}
        segs = {}
        for side, fqn in (("old", old_fqn), ("new", new_fqn)):
            out = os.path.join(tmp, side + ".json")
            # the traced VM is started by LineTracer from the same JDK; taskset is inherited
            subprocess.run(pinned([java, "-Xmx512m", "-cp", tools + os.pathsep + trc, "LineTracer", tgt,
                                   "ArdiffTraceMain " + side, fqn, out]), capture_output=True, text=True, timeout=timeout)
            segs[side] = json.load(open(out)) if os.path.exists(out) else []
        idx, res = 0, []
        for c in calls:                       # inputs that could not be written as literals have no segment
            if c == "null":
                res.append(None); continue
            o = segs["old"][idx] if idx < len(segs["old"]) else None
            n = segs["new"][idx] if idx < len(segs["new"]) else None
            res.append({"old": o, "new": n} if o and n else None)
            idx += 1
        return {"traces": res}
    except (subprocess.TimeoutExpired, ValueError) as ex:
        return {"error": f"실행 흐름 기록 실패: {ex}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ main analysis
def analyze(run_dir, z3=None, jhome=None, use_z3=True, use_exec=True, params=None):
    run_dir = os.path.abspath(run_dir)
    log = read(os.path.join(run_dir, "debug.log"))
    verdict = verdict_of(log)
    last, n_iter = last_iteration(run_dir)
    rep = {"dir": run_dir, "verdict": verdict, "iterations": n_iter, "notes": []}
    reason = re.findall(r"Reason: (.*)", log)
    if verdict == "UNKNOWN" and reason:
        rep["reason"] = reason[-1].strip()
    if verdict not in ("NOT EQUIVALENT", "UNKNOWN"):
        return rep

    if params is None:
        _, m = target_method(os.path.join(run_dir, "oldV.java"), "oldV")
        params = [n for _, n in m.params] if m else []
    rep["params"] = params

    zsum = read(os.path.join(last, "z3summary.txt"))
    model = parse_model(zsum)
    if model:
        ufs = sorted(k for k, d in model.items() if d["args"] and k.startswith("UF_"))
        consts = {k: sx_value(d["value"]) for k, d in model.items() if not d["args"]}
        rep["counterexample"] = {
            "inputs": {k: v for k, v in consts.items() if k in params or (k != "Ret" and not INTERNAL.match(k) and not k.startswith("UF_"))},
            "ret_old": consts.get("Ret"),
            "uf_dependent": bool(ufs), "ufs": ufs}
    old_src = read(os.path.join(last, "IoldVARDiff.java")).splitlines()
    new_src = read(os.path.join(last, "InewVARDiff.java")).splitlines()
    rep["old_paths"] = parse_jpf_paths(read(os.path.join(last, "IoldVARDiffJPFOutput.txt")), old_src)
    rep["new_paths"] = parse_jpf_paths(read(os.path.join(last, "InewVARDiffJPFOutput.txt")), new_src)
    attach_pair_lines(rep["old_paths"], line_map(old_src, read(os.path.join(run_dir, "oldV.java")).splitlines()))
    attach_pair_lines(rep["new_paths"], line_map(new_src, read(os.path.join(run_dir, "newV.java")).splitlines()))
    rep["uf_remaining"] = sorted(set(re.findall(r"\bUF_\w+?(?=\()", "\n".join(old_src + new_src))) - {"UF_"})

    summ = None
    ts = [f for f in os.listdir(last) if f.endswith("ToSolve.txt")] if os.path.isdir(last) else []
    for f in sorted(ts):
        summ = parse_tosolve(read(os.path.join(last, f)))
        if summ:
            break
    summ = summ or parse_summaries_from_z3summary(zsum)

    z3 = find_z3(z3) if use_z3 else None
    if summ and z3:
        decls, old_sx, new_sx = summ
        ra = region_analysis(z3, decls, old_sx, new_sx, params)
        aligned = ra["n_old"] == len(rep["old_paths"]) and ra["n_new"] == len(rep["new_paths"])
        ra["paths_aligned"] = aligned
        if not aligned:
            rep["notes"].append("Z3 요약의 경로 수와 JPF 경로 수가 달라 경로 번호 대응이 정확하지 않을 수 있음")
        rep["regions"] = ra
        if ra["z3_errors"]:
            rep["notes"].append("z3 오류: " + " / ".join(ra["z3_errors"]))
    elif use_z3 and verdict == "NOT EQUIVALENT":
        rep["notes"].append("z3 바이너리 또는 요약 수식을 찾지 못해 차이 영역 분석을 건너뜀")

    if use_exec:
        cands, seen = [], set()

        def add(inputs, source):
            key = tuple(sorted((k, inputs.get(k)) for k in params))
            if key not in seen:
                seen.add(key); cands.append({"inputs": {k: inputs.get(k) for k in params}, "source": source})
        if rep.get("counterexample"):
            add(rep["counterexample"]["inputs"], "ARDiff 반례")
        for r in rep.get("regions", {}).get("regions", []):
            add(r["witness"], f"차이 영역 old#{r['old']} / new#{r['new']}")
        for name in ("IoldVARDiffJPFOutput.txt", "InewVARDiffJPFOutput.txt"):
            for t in parse_jpf_tests(read(os.path.join(last, name))):
                add(t, "JPF 테스트 입력 (" + ("old" if "old" in name else "new") + ")")
        _, m = target_method(os.path.join(run_dir, "oldV.java"), "oldV")
        if m:
            for t in sample_inputs(m.params, [c["inputs"] for c in cands]):
                add(t, "경계값·무작위 입력")
        ex = run_concrete(run_dir, cands[:400], java_home(jhome))
        rep["execution"] = ex
        if verdict == "UNKNOWN" and any(r["differs"] for r in ex.get("runs", [])):
            rep["exec_verdict"] = "NOT EQUIVALENT"
            rep["notes"].append("ARDiff는 판정하지 못했지만 실제 실행에서 결과가 다른 입력을 찾음")
        # line-by-line execution of the inputs the report will show
        import semview
        shown = [sc["inputs"] for sc in semview.scenarios(rep)]
        if shown:
            tr = run_traces(run_dir, shown, java_home(jhome))
            if tr.get("error"):
                rep["notes"].append(tr["error"])
            else:
                rep["traces"] = {json.dumps(i, sort_keys=True, default=str): t
                                 for i, t in zip(shown, tr["traces"]) if t}
    return rep


def sample_inputs(params, seeds, limit=300, rng=None):
    """Boundary values within ARDiff's default domain (-100..100) + neighbours of known inputs + random."""
    rng = rng or random.Random(0)
    ints = [-100, -51, -50, -11, -10, -2, -1, 0, 1, 2, 10, 11, 49, 50, 51, 99, 100]
    reals = [-100.0, -10.5, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 10.5, 100.0]
    doms = []
    for t, n in params:
        if t == "boolean":
            dom = [False, True]
        elif t in ("double", "float"):
            dom = list(reals)
        elif t in JAVA_PRIMS:
            dom = list(ints)
        else:
            return []
        for sd in seeds:
            v = sd.get(n)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                dom += [v - 1, v, v + 1] if t not in ("double", "float") else [v - 0.5, v, v + 0.5]
        doms.append((n, sorted(set(dom), key=float) if t != "boolean" else dom))
    combos = 1
    for _, d in doms:
        combos *= len(d)
    names = [n for n, _ in doms]
    if combos <= limit:
        return [dict(zip(names, c)) for c in itertools.product(*[d for _, d in doms])]
    out = [{n: 0 for n in names}]
    for n, d in doms:                       # vary one parameter at a time around 0
        out += [{**{m: 0 for m in names}, n: v} for v in d]
    while len(out) < limit:
        out.append({n: rng.choice(d) for n, d in doms})
    return out[:limit]


def to_markdown(rep, title=None):
    L = [f"### {title or os.path.basename(rep['dir'])}: **{rep['verdict']}** (iteration {rep['iterations']})"]
    if rep.get("reason"):
        L.append(f"- 이유: {rep['reason']}")
    ce = rep.get("counterexample")
    if ce:
        L.append(f"- ARDiff 반례: `{ce['inputs']}` → old 반환 `{ce['ret_old']}`" +
                 (f" (추상화된 UF {len(ce['ufs'])}개 값에 의존)" if ce["uf_dependent"] else ""))
    ra = rep.get("regions")
    if ra:
        L.append(f"- 경로: old {ra['n_old']}개, new {ra['n_new']}개 · 차이 영역 {len(ra['regions'])}개"
                 + (f" (unknown {ra['unknown']})" if ra["unknown"] else ""))
        for r in ra["regions"][:10]:
            op = rep["old_paths"][r["old"]] if r["old"] < len(rep["old_paths"]) else None
            np_ = rep["new_paths"][r["new"]] if r["new"] < len(rep["new_paths"]) else None
            L.append(f"  - old#{r['old']} 반환 `{op['ret']['expr'] if op and op['ret'] else '?'}` vs "
                     f"new#{r['new']} 반환 `{np_['ret']['expr'] if np_ and np_['ret'] else '?'}` · 예: `{r['witness']}`")
    ex = rep.get("execution")
    if ex:
        if ex.get("error"):
            L.append(f"- 실행 검증: {ex['error']}")
        else:
            diff = [r for r in ex["runs"] if r["differs"]]
            L.append(f"- 실행 검증: 입력 {len(ex['runs'])}개 중 {len(diff)}개에서 결과가 다름")
            for r in diff[:8]:
                L.append(f"  - `{r['inputs']}`: old `{r['old']}` / new `{r['new']}` ({r['source']})")
    for n in rep.get("notes", []):
        L.append(f"- 참고: {n}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--z3"); ap.add_argument("--java-home")
    ap.add_argument("--json"); ap.add_argument("--no-z3", action="store_true"); ap.add_argument("--no-exec", action="store_true")
    a = ap.parse_args()
    rep = analyze(a.run_dir, a.z3, a.java_home, not a.no_z3, not a.no_exec)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1, default=str)
    print(to_markdown(rep))


if __name__ == "__main__":
    main()
