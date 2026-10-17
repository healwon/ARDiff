""""Why is this change okay?" — the role each change plays in the equivalence proof.

For every change (hunk) between oldV and newV, using a small symbolic executor (straight-line code, if/else,
ternaries, Math.min/max/abs, Java int division) and z3:

  identity     the rewrite holds on its own, for any values of the variables it reads
  context      it holds only given earlier (unchanged) statements; `support` lists the smallest such set
               and, when ARDiff's refinement log is available, the iteration in which ARDiff made that
               statement concrete (i.e. the proof needed exactly that fact)
  breaks       it changes a value that reaches the result; `counterexample` shows inputs and both values
  no-effect    nothing it writes is read afterwards
  comment      only comments/whitespace differ
  unsupported  loops, calls, ... outside what the executor models

Each verdict is about the change in the context of everything before it (earlier changes included).
"""
import difflib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import javasrc  # noqa: E402
import semdiff  # noqa: E402

TYPES = {"int": "Int", "long": "Int", "short": "Int", "byte": "Int", "char": "Int",
         "double": "Real", "float": "Real", "boolean": "Bool"}


class Unsupported(Exception):
    pass


# ------------------------------------------------------------------ tokens
TOK = re.compile(r"\s*(?:(?P<num>\d+\.\d*(?:[eE][-+]?\d+)?[dDfF]?|\d*\.\d+(?:[eE][-+]?\d+)?[dDfF]?|\d+[eE][-+]?\d+[dDfF]?|\d+[lLdDfF]?)"
                 r"|(?P<id>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
                 r"|(?P<op>>>>=|<<=|>>=|>>>|\+\+|--|&&|\|\||==|!=|<=|>=|\+=|-=|\*=|/=|%=|<<|>>|[-+*/%<>=!?:;,(){}\[\]&|^~]))")


def tokenize(src, first_line):
    """src: comment-free text. -> [(kind, text, line)]"""
    out, pos, line = [], 0, first_line
    while pos < len(src):
        m = TOK.match(src, pos)
        if not m or m.end() == pos:
            if src[pos:].strip() == "":
                break
            raise Unsupported(f"token at {src[pos:pos + 20]!r}")
        line += src.count("\n", pos, m.start(m.lastgroup))
        out.append((m.lastgroup, m.group(m.lastgroup), line))
        line += src.count("\n", m.start(m.lastgroup), m.end())
        pos = m.end()
    return out


# ------------------------------------------------------------------ parser
class P:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else (None, None, None)

    def take(self, text=None):
        tok = self.peek()
        if tok[0] is None or (text is not None and tok[1] != text):
            raise Unsupported(f"expected {text!r}, got {tok[1]!r}")
        self.i += 1
        return tok

    def at(self, text):
        return self.peek()[1] == text

    # statements -------------------------------------------------------
    def block_items(self, end="}"):
        items = []
        while self.peek()[0] is not None and not self.at(end):
            items.append(self.stmt())
        return items

    def stmt(self):
        kind, text, line = self.peek()
        if text == "{":
            self.take("{"); body = self.block_items(); last = self.take("}")[2]
            return {"k": "block", "body": body, "l0": line, "l1": last}
        if text == "if":
            self.take("if"); self.take("("); cond = self.expr(); self.take(")")
            then = self.stmt(); els = None
            if self.at("else"):
                self.take("else"); els = self.stmt()
            return {"k": "if", "cond": cond, "then": then, "else": els, "l0": line, "l1": (els or then)["l1"]}
        if text == "for":
            self.take("for"); self.take("(")
            init = self.simple_list(";") if not self.at(";") else self.take(";") and None
            cond = self.expr() if not self.at(";") else ("bool", "true")
            self.take(";")
            update = self.simple_list(")") if not self.at(")") else self.take(")") and None
            body = self.stmt()
            return {"k": "loop", "init": init, "cond": cond, "update": update, "body": body, "l0": line, "l1": body["l1"]}
        if text == "while":
            self.take("while"); self.take("("); cond = self.expr(); self.take(")")
            body = self.stmt()
            return {"k": "loop", "init": None, "cond": cond, "update": None, "body": body, "l0": line, "l1": body["l1"]}
        if text == "do":
            self.take("do"); body = self.stmt(); self.take("while"); self.take("("); cond = self.expr(); self.take(")")
            end = self.take(";")[2]
            return {"k": "loop", "init": None, "cond": cond, "update": None, "body": body, "do": True, "l0": line, "l1": end}
        if text in ("++", "--") and self.peek(1)[0] == "id":
            st = self.simple(";")
            st["l0"] = line
            return st
        if text in ("switch", "try", "throw", "break", "continue"):
            raise Unsupported(f"'{text}' statement")
        if text == "return":
            self.take("return"); e = self.expr(); end = self.take(";")[2]
            return {"k": "return", "e": e, "l0": line, "l1": end}
        if text == "final":
            self.take("final"); kind, text, line = self.peek()
        if kind == "id" and text in TYPES and self.peek(1)[0] == "id":
            self.take(); decls = []
            while True:
                name = self.take()[1]
                init = None
                if self.at("="):
                    self.take("="); init = self.expr()
                decls.append((name, init))
                if self.at(","):
                    self.take(","); continue
                break
            end = self.take(";")[2]
            return {"k": "decl", "type": TYPES[text], "vars": decls, "l0": line, "l1": end}
        if kind == "id" and self.peek(1)[1] in ("=", "+=", "-=", "*=", "/=", "%="):
            name = self.take()[1]; op = self.take()[1]; e = self.expr(); end = self.take(";")[2]
            if op != "=":
                e = ("bin", op[0], ("var", name), e)
            return {"k": "assign", "name": name, "e": e, "l0": line, "l1": end}
        if kind == "id" and self.peek(1)[1] in ("++", "--"):
            name = self.take()[1]; op = self.take()[1]; end = self.take(";")[2]
            return {"k": "assign", "name": name, "e": ("bin", op[0], ("var", name), ("num", "1")), "l0": line, "l1": end}
        if text == ";":
            self.take(";")
            return {"k": "block", "body": [], "l0": line, "l1": line}
        raise Unsupported(f"statement starting with {text!r}")

    def simple_list(self, term):
        """comma-separated simple statements (for-loop header) as one block."""
        line = self.peek()[2]
        items = [self.simple(",;)")]
        while self.t[self.i - 1][1] == ",":
            items.append(self.simple(",;)"))
        if self.t[self.i - 1][1] != term:
            raise Unsupported("for header")
        return items[0] if len(items) == 1 else {"k": "block", "body": items, "l0": line, "l1": items[-1]["l1"]}

    def take_any(self, terms):
        tok = self.peek()
        if tok[1] is None or tok[1] not in terms:
            raise Unsupported(f"expected one of {terms!r}, got {tok[1]!r}")
        self.i += 1
        return tok

    def simple(self, term):
        """declaration / assignment / x++ without the trailing ';' (for-loop header), then `term`."""
        kind, text, line = self.peek()
        if kind == "id" and text in TYPES and self.peek(1)[0] == "id":
            self.take(); name = self.take()[1]; init = None
            if self.at("="):
                self.take("="); init = self.expr()
            end = (self.take_any(term) if len(term) > 1 else self.take(term))[2]
            return {"k": "decl", "type": TYPES[text], "vars": [(name, init)], "l0": line, "l1": end}
        if text in ("++", "--"):
            op = self.take()[1]; name = self.take()[1]
            end = (self.take_any(term) if len(term) > 1 else self.take(term))[2]
            return {"k": "assign", "name": name, "e": ("bin", op[0], ("var", name), ("num", "1")), "l0": line, "l1": end}
        name = self.take()[1]
        op = self.take()[1]
        if op in ("++", "--"):
            e = ("bin", op[0], ("var", name), ("num", "1"))
        elif op in ("=", "+=", "-=", "*=", "/=", "%="):
            e = self.expr()
            if op != "=":
                e = ("bin", op[0], ("var", name), e)
        else:
            raise Unsupported(f"loop header {op}")
        end = (self.take_any(term) if len(term) > 1 else self.take(term))[2]
        return {"k": "assign", "name": name, "e": e, "l0": line, "l1": end}

    # expressions (precedence climbing) --------------------------------
    BIN = [("||",), ("&&",), ("|",), ("^",), ("&",), ("==", "!="), ("<", ">", "<=", ">="), ("+", "-"), ("*", "/", "%")]

    def expr(self):
        c = self.binary(0)
        if self.at("?"):
            self.take("?"); a = self.expr(); self.take(":"); b = self.expr()
            return ("ite", c, a, b)
        return c

    def binary(self, lvl):
        if lvl == len(self.BIN):
            return self.unary()
        left = self.binary(lvl + 1)
        while self.peek()[1] in self.BIN[lvl]:
            op = self.take()[1]
            left = ("bin", op, left, self.binary(lvl + 1))
        return left

    def unary(self):
        t = self.peek()[1]
        if t in ("-", "+", "!"):
            self.take()
            e = self.unary()
            return ("neg", e) if t == "-" else ("not", e) if t == "!" else e
        if t == "(" and self.peek(1)[1] in TYPES and self.peek(2)[1] == ")":
            self.take("("); ty = self.take()[1]; self.take(")")
            return ("cast", TYPES[ty], self.unary())
        return self.primary()

    def primary(self):
        kind, text, _ = self.peek()
        if text == "(":
            self.take("("); e = self.expr(); self.take(")")
            return e
        if kind == "num":
            self.take()
            return ("num", text)
        if text in ("true", "false"):
            self.take()
            return ("bool", text)
        if kind == "id" and self.peek(1)[1] == "=":
            self.take(); self.take("=")
            return ("assignx", text, self.expr())
        if kind == "id":
            self.take()
            if self.at("("):
                self.take("("); args = []
                while not self.at(")"):
                    args.append(self.expr())
                    if self.at(","):
                        self.take(",")
                self.take(")")
                return ("call", text, args)
            return ("var", text)
        raise Unsupported(f"expression at {text!r}")


# ------------------------------------------------------------------ to SMT
PRELUDE = """(define-fun jdiv ((a Int) (b Int)) Int (ite (>= a 0) (ite (> b 0) (div a b) (- (div a (- b)))) (ite (> b 0) (- (div (- a) b)) (div (- a) (- b)))))
(define-fun jmod ((a Int) (b Int)) Int (- a (* b (jdiv a b))))
(define-fun jtrunc ((x Real)) Int (ite (>= x 0.0) (to_int x) (- (to_int (- x)))))
"""


class Sym:
    """Compiles AST to SMT text against an environment {var: (sort, term)}."""

    UNROLL = 20           # loop iterations unrolled (ARDiff's default bound is 5); terms stay linear via `defs`

    def __init__(self, smt_div=False, ret_sort="Real"):
        # smt_div: model Java int / and % with SMT div/mod (rounding down), as ARDiff's translation does;
        # Java itself truncates toward zero (jdiv/jmod)
        self.smt_div = smt_div
        self.ret_sort = ret_sort
        self.defs = []        # (name, sort, term): fresh constants that keep unrolled terms small
        self.assume = []      # loop-bound assumptions (the loop exits within UNROLL iterations)
        self.ufs = {}         # name -> (arg sorts, result sort) for calls we do not model
        self.bounded = False

    MAX_TERM = 200            # longer terms get their own constant, so nothing is ever copied twice
    MAX_TOTAL = 4_000_000     # bytes of SMT per check; beyond this the code is reported as too large

    def fresh(self, sort, term, hint):
        name = f"d{len(self.defs)}_{hint}"
        self.defs.append((name, sort, term))
        self.total = getattr(self, "total", 0) + len(term)
        if self.total > self.MAX_TOTAL:
            raise Unsupported("formula too large")
        return name

    def share(self, sort, term, hint="t"):
        """the term itself if short, otherwise a fresh constant defined as the term"""
        return term if len(term) <= self.MAX_TERM else self.fresh(sort, term, re.sub(r"\W", "", hint)[:12] or "t")

    def mk_ite(self, sort, c, a, b, hint):
        if a == b:
            return a
        return self.share(sort, f"(ite {c} {a} {b})", hint)

    def num(self, text):
        t = text.rstrip("lLdDfF")
        if re.search(r"[.eE]", t) or text[-1:] in "dDfF":
            v = float(t)
            return "Real", (f"{v!r}" if v >= 0 else f"(- {-v!r})").replace("e", "E") if "e" in repr(v) else (f"{v}" if v >= 0 else f"(- {-v})")
        return "Int", t

    def ev(self, e, env):
        k = e[0]
        if k == "num":
            return self.num(e[1])
        if k == "bool":
            return "Bool", e[1]
        if k == "var":
            if e[1] not in env:
                raise Unsupported(f"unknown variable {e[1]}")
            return env[e[1]]
        if k == "neg":
            s, t = self.ev(e[1], env)
            return s, f"(- {t})"
        if k == "not":
            s, t = self.ev(e[1], env)
            return "Bool", f"(not {t})"
        if k == "cast":
            s, t = self.ev(e[2], env)
            if e[1] == "Int" and s == "Real":
                return "Int", f"(jtrunc {t})"
            if e[1] == "Real" and s == "Int":
                return "Real", f"(to_real {t})"
            return s, t
        if k == "ite":
            cs, ct = self.ev(e[1], env)
            (sa, ta), (sb, tb) = self.ev(e[2], env), self.ev(e[3], env)
            sort, ta, tb = self.unify(sa, ta, sb, tb)
            return sort, f"(ite {ct} {ta} {tb})"
        if k == "call":
            name, args = e[1].split(".")[-1], [self.ev(a, env) for a in e[2]]
            if e[1] in ("Math.min", "Math.max") and len(args) == 2:
                sort, a, b = self.unify(*args[0], *args[1])
                return sort, f"(ite ({'<=' if name == 'min' else '>='} {a} {b}) {a} {b})"
            if e[1] == "Math.abs" and len(args) == 1:
                s, a = args[0]
                return s, f"(ite (>= {a} 0) {a} (- {a}))" if s == "Int" else f"(ite (>= {a} 0.0) {a} (- {a}))"
            # any other call: an uninterpreted function, the same one on both sides (as ARDiff abstracts code)
            sig = "_".join(sa[0] for sa in args)
            fname = "uf_" + re.sub(r"\W", "_", e[1]) + (f"_{sig}" if sig else "")
            self.ufs[fname] = ([sa[0] for sa in args], "Real")
            return "Real", (f"({fname} {' '.join(sa[1] for sa in args)})" if args else fname)
        if k == "bin":
            op = e[1]
            (sa, ta), (sb, tb) = self.ev(e[2], env), self.ev(e[3], env)
            if op in ("&&", "||"):
                return "Bool", f"({'and' if op == '&&' else 'or'} {ta} {tb})"
            if op in ("&", "|", "^"):
                if sa == "Bool" and sb == "Bool":
                    return "Bool", {"&": f"(and {ta} {tb})", "|": f"(or {ta} {tb})", "^": f"(xor {ta} {tb})"}[op]
                raise Unsupported("bitwise operator")
            sort, ta, tb = self.unify(sa, ta, sb, tb)
            if op in ("==", "!="):
                eq = f"(= {ta} {tb})"
                return "Bool", eq if op == "==" else f"(not {eq})"
            if op in ("<", ">", "<=", ">="):
                return "Bool", f"({op} {ta} {tb})"
            if op in ("+", "-", "*"):
                return sort, f"({op} {ta} {tb})"
            if op == "/":
                if sort == "Int":
                    return "Int", f"({'div' if self.smt_div else 'jdiv'} {ta} {tb})"
                return "Real", f"(/ {ta} {tb})"
            if op == "%":
                if sort == "Int":
                    return "Int", f"({'mod' if self.smt_div else 'jmod'} {ta} {tb})"
                raise Unsupported("real %")
        raise Unsupported(f"expression {k}")

    @staticmethod
    def unify(sa, ta, sb, tb):
        if sa == sb:
            return sa, ta, tb
        if {sa, sb} == {"Int", "Real"}:
            return "Real", (f"(to_real {ta})" if sa == "Int" else ta), (f"(to_real {tb})" if sb == "Int" else tb)
        raise Unsupported(f"mixed {sa}/{sb}")

    def run(self, stmts, env, sorts, havoc=None):
        """Execute statements in place on env {var: (sort, term)}. env carries "__done"/"__ret" for early returns.
        havoc: ids of statements whose effect is replaced by fresh symbols (to find which statements a proof needs)."""
        for s in stmts:
            done = env.get("__done", ("Bool", "false"))[1]
            before = dict(env)
            self.step(s, env, sorts, havoc)
            if done != "false":
                # statements after a return do nothing
                for v in set(env):
                    if v in before and env[v] != before[v]:
                        env[v] = (env[v][0], self.mk_ite(env[v][0], done, before[v][1], env[v][1], v))
        return env

    def hoist(self, e, env, sorts):
        """execute `x = e` sub-expressions (left to right) and replace them by x."""
        if isinstance(e, tuple):
            if e[0] == "assignx":
                inner = self.hoist(e[2], env, sorts)
                if e[1] not in sorts:
                    raise Unsupported(f"assignment to {e[1]}")
                self.assign(env, sorts, e[1], *self.ev(inner, env))
                return ("var", e[1])
            return tuple(self.hoist(x, env, sorts) if isinstance(x, (tuple, list)) else x for x in e)
        if isinstance(e, list):
            return [self.hoist(x, env, sorts) for x in e]
        return e

    def assign(self, env, sorts, name, so, t):
        want = sorts[name]
        if so != want:
            t = f"(to_real {t})" if want == "Real" and so == "Int" else f"(jtrunc {t})" if want == "Int" and so == "Real" else t
        env[name] = (want, self.share(want, t, name))

    def step(self, s, env, sorts, havoc):
        if havoc is not None and id(s) in havoc:
            if s["k"] == "decl":                 # the variable still exists, only its value is unknown
                for name, _ in s["vars"]:
                    sorts[name] = s["type"]
            for v in defs_of(s):
                if v in sorts:
                    env[v] = (sorts[v], f"h{len(havoc)}_{id(s) % 100000}_{v}")
                    HAVOCS[env[v][1]] = sorts[v]
            return
        k = s["k"]
        if k == "block":
            self.run(s["body"], env, sorts, havoc)
        elif k == "decl":
            for name, init in s["vars"]:
                sorts[name] = s["type"]
                if init is not None:
                    self.assign(env, sorts, name, *self.ev(init, env))
                else:
                    env[name] = (s["type"], "0" if s["type"] == "Int" else "0.0" if s["type"] == "Real" else "false")
        elif k == "assign":
            if s["name"] not in sorts:
                raise Unsupported(f"assignment to {s['name']}")
            self.assign(env, sorts, s["name"], *self.ev(self.hoist(s["e"], env, sorts), env))
        elif k == "if":
            _, c = self.ev(self.hoist(s["cond"], env, sorts), env)
            e1, e2 = dict(env), dict(env)
            self.run([s["then"]], e1, sorts, havoc)
            if s["else"]:
                self.run([s["else"]], e2, sorts, havoc)
            self.merge(env, c, e1, e2)
        elif k == "loop":
            self.bounded = True
            if s["init"]:
                self.step(s["init"], env, sorts, havoc)
            if s.get("do"):
                self.run([s["body"]], env, sorts, havoc)
            for _ in range(self.UNROLL):
                _, c = self.ev(self.hoist(s["cond"], env, sorts), env)
                c = f"(and {c} (not {env['__done'][1]}))" if env.get("__done", ("Bool", "false"))[1] != "false" else c
                body = dict(env)
                self.run([s["body"]] + ([s["update"]] if s["update"] else []), body, sorts, havoc)
                self.merge(env, c, body, dict(env))
            _, c = self.ev(self.hoist(s["cond"], env, sorts), env)
            self.assume.append(f"(or (not {c}) {env.get('__done', ('Bool', 'false'))[1]})")
        elif k == "return":
            so, t = self.ev(self.hoist(s["e"], env, sorts), env)
            if so != self.ret_sort:
                t = f"(to_real {t})" if self.ret_sort == "Real" and so == "Int" else t
            env["__ret"] = (self.ret_sort, t)
            env["__done"] = ("Bool", "true")

    def merge(self, env, c, e1, e2):
        c = self.share("Bool", c, "c")
        for v in set(e1) | set(e2):
            if v in e1 and v in e2:
                env[v] = e1[v] if e1[v] == e2[v] else (e1[v][0], self.mk_ite(e1[v][0], c, e1[v][1], e2[v][1], v))


HAVOCS = {}


def has_return(s):
    if s is None:
        return False
    k = s["k"]
    if k == "return":
        return True
    if k == "block":
        return any(has_return(x) for x in s["body"])
    if k == "if":
        return has_return(s["then"]) or has_return(s["else"])
    if k == "loop":
        return has_return(s["body"])
    return False


def defs_of(s):
    k = s["k"]
    if k == "decl":
        return [n for n, _ in s["vars"]]
    if k == "assign":
        return [s["name"]]
    if k == "block":
        return [v for x in s["body"] for v in defs_of(x)]
    if k == "if":
        return defs_of(s["then"]) + (defs_of(s["else"]) if s["else"] else [])
    if k == "loop":
        return (defs_of(s["init"]) if s["init"] else []) + defs_of(s["body"]) + (defs_of(s["update"]) if s["update"] else [])
    return []


def vars_in(node):
    out = set()
    if isinstance(node, tuple):
        if node[0] == "var":
            out.add(node[1])
        for x in node[1:]:
            out |= vars_in(x)
    elif isinstance(node, dict):
        for k, x in node.items():
            if k not in ("l0", "l1", "k", "type"):
                out |= vars_in(x)
    elif isinstance(node, list):
        for x in node:
            out |= vars_in(x)
    return out


# ------------------------------------------------------------------ z3
def z3_check(z3, consts, claim, getv, timeout=8, defs=(), assume=(), ufs=None):
    """claim: Bool term that must be valid (under defs/assume). -> ("valid"|"invalid"|"unknown", model dict)"""
    decl = "".join(f"(declare-fun {n} () {s})\n" for n, s in sorted(consts.items()))
    decl += "".join(f"(declare-fun {n} ({' '.join(a)}) {r})\n" for n, (a, r) in sorted((ufs or {}).items()))
    decl += "".join(f"(declare-fun {n} () {so})\n" for n, so, _ in defs)
    decl += "".join(f"(assert (= {n} {t}))\n" for n, _, t in defs)
    decl += "".join(f"(assert {x})\n" for x in assume)
    q = (f"(set-option :timeout {timeout * 1000})\n{PRELUDE}{decl}(assert (not {claim}))\n(check-sat)\n"
         + (f"(get-value ({' '.join(getv)}))\n" if getv else ""))
    try:
        p = subprocess.run(semdiff.pinned([z3, "-in", "-smt2"]), input=q, capture_output=True, text=True, timeout=timeout + 10)
        out = p.stdout
    except subprocess.TimeoutExpired:
        return "unknown", {}
    first = out.strip().split("\n", 1)[0] if out.strip() else ""
    if first == "unsat":
        if assume:
            # valid only matters if some input actually finishes the loops within the unroll bound
            q2 = f"(set-option :timeout {timeout * 1000})\n{PRELUDE}{decl}(check-sat)\n"
            try:
                p2 = subprocess.run(semdiff.pinned([z3, "-in", "-smt2"]), input=q2, capture_output=True, text=True, timeout=timeout + 10)
                if p2.stdout.strip().split("\n", 1)[0] != "sat":
                    return "vacuous", {}
            except subprocess.TimeoutExpired:
                return "unknown", {}
        return "valid", {}
    if first != "sat":
        return "unknown", {}
    model = {}
    rest = out.strip().split("\n", 1)[1] if "\n" in out.strip() else ""
    for form in semdiff.sx_parse_all(rest):
        if isinstance(form, list):
            for pair in form:
                if isinstance(pair, list) and len(pair) == 2:
                    v = semdiff.sx_value(pair[1])
                    model[semdiff.sx_str(pair[0])] = v if v is not None else semdiff.sx_str(pair[1])
    return "invalid", model


# ------------------------------------------------------------------ method model
def method_model(src, cls):
    m = None
    for c in javasrc.parse(src):
        if c.methods and (c.name == cls or m is None):
            m = c.methods[0]
            if c.name == cls:
                break
    if m is None:
        raise Unsupported("no method")
    clean = javasrc.strip_comments(src)
    start = src.index(m.body) if m.body in src else None
    if start is None:
        raise Unsupported("method body not found")
    body = clean[start:start + len(m.body)]
    first_line = src.count("\n", 0, start) + 1
    p = P(tokenize(body, first_line))
    stmts = p.block_items(end=None)
    params = [(n, TYPES.get(javasrc.norm_type(t))) for t, n in m.params]
    if any(s is None for _, s in params):
        raise Unsupported("non-primitive parameter")
    return {"stmts": stmts, "params": params, "ret": TYPES.get(m.ret.strip(), "Real")}


def top_index(stmts, l0, l1):
    """indices of top-level statements whose span intersects lines [l0, l1]."""
    return [i for i, s in enumerate(stmts) if s["l0"] <= l1 and s["l1"] >= l0]


def hunks(old_lines, new_lines):
    key = lambda l: re.sub(r"\s+", " ", re.sub(r"\b(?:oldV|newV)\b", "V", l)).strip()
    a, b = [key(l) for l in old_lines], [key(l) for l in new_lines]
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append((i1 + 1, i2, j1 + 1, j2))      # 1-based inclusive ranges; empty when i1+1 > i2
    return out


def refinement_steps(run_dir, pair_old_lines):
    """pair-file line (1-based) -> iteration in which ARDiff's refinement picked it (made it concrete)."""
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import build_viewer
    except ImportError:
        return {}, []
    log = semdiff.read(os.path.join(run_dir, "debug.log"))
    if "------ARDIFF" not in log:
        return {}, []
    log = log[log.find("------ARDIFF"):]
    chunks = log.split(build_viewer.STATUS_MARK)[1:]
    parsed = [build_viewer.parse_chunk(c.split("\n", 1)[1] if "\n" in c else c) for c in chunks]
    inst = semdiff.read(os.path.join(run_dir, "iterations", "iter_00", "oldV.java")).splitlines()
    lmap = semdiff.line_map(inst, pair_old_lines)
    picked = {}
    for i, it in enumerate(parsed):
        if it.get("pick") and lmap.get(it["pick"]) and lmap[it["pick"]] not in picked:
            picked[lmap[it["pick"]]] = i
    statuses = [it.get("status") for it in parsed]
    return picked, statuses


def analyze(run_dir, z3=None):
    """-> {"hunks": [...], "error": str?}"""
    z3 = semdiff.find_z3(z3)
    old_src = semdiff.read(os.path.join(run_dir, "oldV.java"))
    new_src = semdiff.read(os.path.join(run_dir, "newV.java"))
    ol, nl = old_src.splitlines(), new_src.splitlines()
    if not z3:
        return {"error": "z3를 찾지 못함", "hunks": []}
    try:
        mo, mn = method_model(old_src, "oldV"), method_model(new_src, "newV")
    except Unsupported as ex:
        return {"error": f"증명 역할 분석을 지원하지 않는 코드: {ex}", "hunks": []}
    picked, statuses = refinement_steps(run_dir, ol)
    so, sn = mo["stmts"], mn["stmts"]

    # group line hunks by the top-level statements they touch
    groups = []
    for (a0, a1, b0, b1) in hunks(ol, nl):
        io, in_ = top_index(so, a0, max(a0, a1)) if a1 >= a0 else [], top_index(sn, b0, max(b0, b1)) if b1 >= b0 else []
        if not io and not in_:
            continue                                      # outside the method body (class line, comments around it)
        if not io:
            io_pos = sum(1 for s in so if s["l1"] < a0)
            io = []
        else:
            io_pos = io[0]
        if not in_:
            in_pos = sum(1 for s in sn if s["l1"] < b0)
        else:
            in_pos = in_[0]
        g = {"old_idx": io, "new_idx": in_, "old_pos": io_pos, "new_pos": in_pos, "lines": [(a0, a1, b0, b1)]}
        if groups and (set(io) & set(groups[-1]["old_idx"]) or set(in_) & set(groups[-1]["new_idx"])):
            last = groups[-1]
            last["old_idx"] = sorted(set(last["old_idx"]) | set(io)); last["new_idx"] = sorted(set(last["new_idx"]) | set(in_))
            last["lines"].append((a0, a1, b0, b1))
        else:
            groups.append(g)

    out, i = [], 0
    while i < len(groups):
        g = groups[i]
        h = analyze_group(g, mo, mn, ol, nl, z3, picked)
        # e.g. a declaration removed in one hunk and its use rewritten in the next: judge them together
        while h.get("why") == "variable not defined on both sides" and i + 1 < len(groups):
            i += 1
            n = groups[i]
            g = {"old_idx": sorted(set(g["old_idx"]) | set(n["old_idx"]) | set(range(g["old_pos"], (max(n["old_idx"]) + 1) if n["old_idx"] else n["old_pos"]))),
                 "new_idx": sorted(set(g["new_idx"]) | set(n["new_idx"]) | set(range(g["new_pos"], (max(n["new_idx"]) + 1) if n["new_idx"] else n["new_pos"]))),
                 "old_pos": g["old_pos"], "new_pos": g["new_pos"], "lines": g["lines"] + n["lines"]}
            h = analyze_group(g, mo, mn, ol, nl, z3, picked)
        out.append(h)
        i += 1
    # which earlier changes a change reads from (e.g. a hoisted value, a flipped sign)
    for k, h in enumerate(out):
        reads = set(h.get("reads", []))
        h["uses_changes"] = [j for j in range(k) if reads & set(out[j].get("writes", []))]
    overall = whole_program(mo, mn, z3)
    if overall == "valid":
        # a change that alters intermediate values but whose effect a later change undoes
        for k, h in enumerate(out):
            if h.get("role") == "breaks":
                h["role"] = "compensated"
                h["intermediate_example"] = h.pop("counterexample", None)   # values differ here, not in the result
                h["compensated_by"] = [j for j in range(k + 1, len(out)) if out[j].get("role") not in ("identity", "comment", "no-effect")]
    return {"hunks": out, "statuses": statuses, "overall": overall}


def whole_program(mo, mn, z3):
    """Do old and new return the same value for every input (loops unrolled, calls uninterpreted)?"""
    try:
        sym = Sym(ret_sort=mo["ret"])
        envs = []
        for m in (mo, mn):
            env = {n: (s_, n) for n, s_ in m["params"]}
            env["__done"], env["__ret"] = ("Bool", "false"), (mo["ret"], "ret_none")
            sym.run(m["stmts"], env, {n: s_ for n, s_ in m["params"]})
            envs.append(env)
        sort, a, b = sym.unify(*envs[0]["__ret"], *envs[1]["__ret"])
        consts = {n: s_ for n, s_ in mo["params"]}
        consts["ret_none"] = mo["ret"]
        res, _ = z3_check(z3, consts, f"(= {a} {b})", [], defs=sym.defs, assume=sym.assume, ufs=sym.ufs)
        return res
    except Unsupported:
        return "unsupported"


def analyze_group(g, mo, mn, ol, nl, z3, picked):
    so, sn = mo["stmts"], mn["stmts"]
    hold = [so[i] for i in g["old_idx"]]
    hnew = [sn[i] for i in g["new_idx"]]
    o_end = (max(g["old_idx"]) + 1) if g["old_idx"] else g["old_pos"]
    n_end = (max(g["new_idx"]) + 1) if g["new_idx"] else g["new_pos"]
    pre_o, pre_n = so[:g["old_pos"]], sn[:g["new_pos"]]
    suf_o, suf_n = so[o_end:], sn[n_end:]
    old_rng = [l for (a0, a1, _, _) in g["lines"] for l in range(a0, a1 + 1)]
    new_rng = [l for (_, _, b0, b1) in g["lines"] for l in range(b0, b1 + 1)]
    h = {"old_lines": old_rng, "new_lines": new_rng,
         "old_text": [ol[l - 1].strip() for l in old_rng], "new_text": [nl[l - 1].strip() for l in new_rng]}
    strip = lambda ls: [re.sub(r"\s+", "", javasrc.strip_comments(x)) for x in ls]
    if strip(h["old_text"]) == strip(h["new_text"]):
        h["role"] = "comment"
        return h

    written = set(v for s in hold + hnew for v in defs_of(s))
    h["writes"] = sorted(written)
    h["reads"] = sorted(vars_in(hold) | vars_in(hnew))
    read_after = vars_in(suf_o) | vars_in(suf_n)
    live = sorted(v for v in written if v in read_after)
    returns_here = any(has_return(s) for s in hold + hnew)
    if returns_here:
        live = live + ["__done", "__ret"]
    h["live"] = [v for v in live if not v.startswith("__")]
    if not live:
        h["role"] = "no-effect"
        return h

    def claim(env_o, env_n, sym):
        parts = []
        for v in live:
            if v not in env_o or v not in env_n:
                return None
            sort, a, b = sym.unify(env_o[v][0], env_o[v][1], env_n[v][0], env_n[v][1])
            parts.append(f"(= {a} {b})")
        return "(and " + " ".join(parts) + ")" if len(parts) > 1 else parts[0]

    def env_for(prefix, model, sym, havoc=None, fresh=False):
        env = {n: (s, n) for n, s in model["params"]}
        env["__done"], env["__ret"] = ("Bool", "false"), (mo["ret"], "ret_none")
        sorts = {n: s for n, s in model["params"]}
        if fresh:
            # every variable the hunk touches starts as an unconstrained symbol (no context)
            Sym(ret_sort=mo["ret"]).run(prefix, dict(env), sorts)          # only to collect declared sorts
            for v, s in sorts.items():
                env[v] = (s, f"v0_{v}")
            return env, sorts
        sym.run(prefix, env, sorts, havoc)
        return env, sorts

    def check(fresh=False, havoc_o=None, havoc_n=None, smt_div=False, timeout=8):
        HAVOCS.clear()
        sym = Sym(smt_div, mo["ret"])
        eo, so_ = env_for(pre_o, mo, sym, havoc_o, fresh)
        en, sn_ = env_for(pre_n, mn, sym, havoc_n, fresh)
        if fresh:
            for v in set(so_) | set(sn_):
                if v not in eo and v in sn_:
                    eo[v] = (sn_[v], f"v0_{v}"); so_[v] = sn_[v]
                if v not in en and v in so_:
                    en[v] = (so_[v], f"v0_{v}"); sn_[v] = so_[v]
        sym.run(hold, eo, so_)
        sym.run(hnew, en, sn_)
        c = claim(eo, en, sym)
        if c is None:
            raise Unsupported("variable not defined on both sides")
        consts = {n: s for n, s in mo["params"]}
        consts["ret_none"] = mo["ret"]
        if fresh:
            consts.update({f"v0_{v}": s for v, s in {**so_, **sn_}.items()})
        consts.update(HAVOCS)
        getv = [n for n, _ in mo["params"]] + ([f"v0_{v}" for v in vars_in(hold + hnew) if f"v0_{v}" in consts] if fresh else [])
        getv += [t for v in live for t in (eo[v][1], en[v][1])][:0]
        res, model = z3_check(z3, consts, c, getv, timeout=timeout, defs=sym.defs, assume=sym.assume, ufs=sym.ufs)
        if sym.bounded:
            h["bounded"] = Sym.UNROLL
        return res, model, eo, en

    try:
        local, lmodel, _, _ = check(fresh=True)
        if local == "valid":
            h["role"] = "identity"
            return h
        full, fmodel, eo, en = check()
    except Unsupported as ex:
        h["role"] = "unsupported"; h["why"] = str(ex)
        return h
    if "vacuous" in (local, full):
        h["role"] = "unknown"; h["why"] = f"a loop runs more than {Sym.UNROLL} times"
        return h

    if full == "valid":
        h["role"] = "context"
        h["local_counterexample"] = {k.replace("v0_", ""): v for k, v in lmodel.items()}
        # smallest set of earlier statements the proof needs: drop one at a time while the claim still holds
        same_prefix = len(pre_o) == len(pre_n) and all(
            re.sub(r"\s+", "", "".join(ol[s["l0"] - 1:s["l1"]])) == re.sub(r"\s+", "", "".join(nl[t["l0"] - 1:t["l1"]]))
            for s, t in zip(pre_o, pre_n))
        need = list(range(len(pre_o)))
        if same_prefix:
            for k in reversed(range(len(pre_o))):
                trial = [i for i in need if i != k]
                ho = {id(pre_o[i]) for i in range(len(pre_o)) if i not in trial}
                hn = {id(pre_n[i]) for i in range(len(pre_n)) if i not in trial}
                try:
                    r, _, _, _ = check(havoc_o=ho, havoc_n=hn, timeout=3)
                except Unsupported:
                    r = "unknown"
                if r == "valid":
                    need = trial
        h["support"] = [{"line": pre_o[i]["l0"], "text": " ".join(x.strip() for x in ol[pre_o[i]["l0"] - 1:pre_o[i]["l1"]]),
                         "refined_iter": next((picked[l] for l in range(pre_o[i]["l0"], pre_o[i]["l1"] + 1) if l in picked), None),
                         "new_line": pre_n[i]["l0"] if same_prefix else None}
                        for i in need] if same_prefix else []
        if not same_prefix:
            h["note"] = "holds given the earlier changes"
        return h

    if full == "invalid":
        h["role"] = "breaks"
        params = [n for n, _ in mo["params"]]
        h["counterexample"] = {k: v for k, v in fmodel.items() if k in params}
        try:
            rdiv, _, _, _ = check(smt_div=True)
            if rdiv == "valid":
                h["note"] = "holds with SMT div (rounds down, ARDiff's encoding); Java's / truncates toward zero"
                h["smt_div_only"] = True
        except Unsupported:
            pass
        return h
    h["role"] = "unknown"
    return h


if __name__ == "__main__":
    print(json.dumps(analyze(sys.argv[1]), ensure_ascii=False, indent=1))
