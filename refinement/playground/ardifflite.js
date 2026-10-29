// ARDiff-lite: ARDiff's abstraction-refinement loop re-implemented for the browser (needs engine.js and a z3 "eval").
//
//   1. statements that are the same in old and new (by line diff) are abstracted: each becomes
//      `x = UF_x_L<line>(variables it reads)`; the matching statement in the other version uses the same UF
//   2. both versions are executed symbolically (loops unrolled, ints as mathematical integers, Java / and %)
//      and z3 is asked whether their results can differ (inputs bounded like ARDiff: -100..100)
//   3. unsat -> EQUIVALENT. sat -> the model's inputs are run on the real code: if the results differ,
//      NOT EQUIVALENT (a real counterexample); otherwise the difference came from the abstraction, so one
//      abstracted statement is made concrete again (refinement) and we go back to 2
//
// Calls to other methods of the class are inlined (their common statements are abstracted the same way);
// local arrays have a fixed, constant size and an index out of bounds is an exception, as in Java.
//
// This is a re-implementation, not ARDiff: the summaries are functional (no per-path fresh variables) and
// spurious counterexamples are discarded by running them, so it can differ from ARDiff's verdict.
(function (root) {
"use strict";
var Engine = root.Engine;
var UNROLL = 10, MIN = -100, MAX = 100, MAX_TERM = 200;

function Unsupported(m) { this.message = m; }

// ---------------------------------------------------------------- which statements are common
function lineMaps(oldSrc, newSrc) {
  var key = function (l) { return Engine.stripComments(l).replace(/\b(?:oldV|newV)\b/g, "V").replace(/\s+/g, " ").trim(); };
  var a = oldSrc.split("\n"), b = newSrc.split("\n");
  var ops = Engine.lcsOps(a.map(key), b.map(key)), o2n = {}, n2o = {};
  ops.forEach(function (op) { if (op[0] === "=") { o2n[op[1] + 1] = op[2] + 1; n2o[op[2] + 1] = op[1] + 1; } });
  return {o2n: o2n, n2o: n2o, blankOld: a.map(function (l) { return !key(l); }), blankNew: b.map(function (l) { return !key(l); })};
}

// a statement is common when every non-blank line it spans is unchanged; its id is the old line it starts on
function commonId(s, side, maps) {
  var map = side === "old" ? maps.o2n : maps.n2o, blank = side === "old" ? maps.blankOld : maps.blankNew;
  for (var l = s.l0; l <= s.l1; l++) if (!blank[l - 1] && !map[l]) return null;
  return side === "old" ? s.l0 : maps.n2o[s.l0];
}

function varsRead(node, out) {
  out = out || {};
  if (Array.isArray(node)) {
    if (node[0] === "var") out[node[1]] = 1;
    else if (node[0] === "assignx") { out[node[1]] = 1; varsRead(node[2], out); }
    else node.forEach(function (x) { if (x && typeof x === "object") varsRead(x, out); });
  } else if (node && typeof node === "object") {
    for (var k in node) if (k !== "l0" && k !== "l1" && k !== "k" && k !== "type" && node[k] && typeof node[k] === "object") varsRead(node[k], out);
  }
  return out;
}
function varsDefined(s, out) {
  out = out || {};
  if (!s) return out;
  if (s.k === "decl") s.vars.forEach(function (v) { out[v[0]] = s.type; });
  else if (s.k === "assign" || s.k === "astore") out[s.name] = out[s.name] || null;
  else if (s.k === "block") s.body.forEach(function (x) { varsDefined(x, out); });
  else if (s.k === "if") { varsDefined(s.then, out); varsDefined(s.els, out); }
  else if (s.k === "loop") { varsDefined(s.init, out); varsDefined(s.body, out); varsDefined(s.upd, out); }
  return out;
}
function hasReturn(s) {
  if (!s) return false;
  if (s.k === "return" || s.k === "break" || s.k === "continue") return true;
  if (s.k === "block") return s.body.some(hasReturn);
  if (s.k === "if") return hasReturn(s.then) || hasReturn(s.els);
  if (s.k === "loop") return hasReturn(s.body);
  return false;
}

// a statement that calls a method of the class or touches an array stays concrete: a UF over the variables it
// reads would assume the callee, or the array's contents, are the same in both versions
function opaque(node, methods) {
  if (Array.isArray(node)) {
    if (node[0] === "aget" || node[0] === "newarr" || node[0] === "arrlit") return true;
    if (node[0] === "call" && methods[node[1] + "/" + node[2].length]) return true;
    return node.some(function (x) { return x && typeof x === "object" && opaque(x, methods); });
  }
  if (node && typeof node === "object") {
    if (node.k === "astore" || (node.k === "decl" && node.type[0] === "A")) return true;
    for (var k in node) if (k !== "l0" && k !== "l1" && node[k] && typeof node[k] === "object" && opaque(node[k], methods)) return true;
  }
  return false;
}

// replace common statements (not yet refined) by UF nodes
function abstract(stmts, side, maps, concrete, seen, methods) {
  return stmts.map(function (s) {
    var id = commonId(s, side, maps);
    if (id !== null && !concrete[id] && !hasReturn(s) && Object.keys(varsDefined(s)).length && !opaque(s, methods)) {
      seen[id] = seen[id] || {line: id, text: null, side: side};
      return {k: "uf", id: id, defs: varsDefined(s), reads: varsRead(s), l0: s.l0, l1: s.l1};
    }
    if (s.k === "block") return Object.assign({}, s, {body: abstract(s.body, side, maps, concrete, seen, methods)});
    if (s.k === "if") return Object.assign({}, s, {then: abstract([s.then], side, maps, concrete, seen, methods)[0], els: s.els ? abstract([s.els], side, maps, concrete, seen, methods)[0] : null});
    if (s.k === "loop") return Object.assign({}, s, {body: abstract([s.body], side, maps, concrete, seen, methods)[0]});
    return s;
  });
}

// ---------------------------------------------------------------- symbolic execution to SMT-LIB
var SORT = {I: "Int", D: "Real", Z: "Bool"};
var TYPE = {int: "I", long: "I", short: "I", byte: "I", char: "I", double: "D", float: "D", boolean: "Z", void: "I"};
// values are [sort, term]; an array is ["Arr", {sort, items: [term...]}] (fixed size)
function Sym() { this.defs = []; this.assume = []; this.ufs = {}; this.bounded = false; this.total = 0; this.methods = {}; this.depth = 0; }
Sym.prototype = {
  fresh: function (sort, term) {
    var n = "d" + this.defs.length;
    this.defs.push([n, sort, term]); this.total += term.length;
    if (this.total > 3e6) throw new Unsupported("formula too large");
    return n;
  },
  share: function (sort, term) { return term.length <= MAX_TERM ? term : this.fresh(sort, term); },
  num: function (t) {
    var s = t.replace(/[lLdDfF]$/, "");
    if (/[.eE]/.test(s) || /[dDfF]$/.test(t)) { var v = parseFloat(s); var r = Math.abs(v).toFixed(12).replace(/0+$/, "").replace(/\.$/, ".0"); return ["Real", v < 0 ? "(- " + r + ")" : r]; }
    return ["Int", String(parseInt(s, 10))];
  },
  unify: function (a, b) {
    if (a[0] === b[0]) return [a[0], a[1], b[1]];
    if ((a[0] === "Int" && b[0] === "Real") || (a[0] === "Real" && b[0] === "Int"))
      return ["Real", a[0] === "Int" ? "(to_real " + a[1] + ")" : a[1], b[0] === "Int" ? "(to_real " + b[1] + ")" : b[1]];
    throw new Unsupported("mixed " + a[0] + "/" + b[0]);
  },
  ev: function (e, env, sorts) {
    var self = this, a, b, u;
    switch (e[0]) {
      case "num": return this.num(e[1]);
      case "bool": return ["Bool", e[1] ? "true" : "false"];
      case "var": if (!(e[1] in env)) throw new Unsupported("unknown variable " + e[1]); return env[e[1]];
      case "assignx": this.assign(env, sorts, e[1], this.ev(e[2], env, sorts)); return env[e[1]];
      case "neg": a = this.ev(e[1], env, sorts); return [a[0], "(- " + a[1] + ")"];
      case "aget":
        var at = this.index(env, sorts, env[e[1]], e[2]), it = env[e[1]][1];
        if (at.lit !== null) return [it.sort, it.items[at.lit]];
        var t = it.items[at.n - 1] || (it.sort === "Real" ? "0.0" : it.sort === "Bool" ? "false" : "0");
        for (var q = at.n - 2; q >= 0; q--) t = "(ite (= " + at.ix + " " + q + ") " + it.items[q] + " " + t + ")";
        return [it.sort, this.share(it.sort, t)];
      case "newarr":
        var sz = this.ev(e[2], env, sorts);
        if (!/^\d+$/.test(sz[1])) throw new Unsupported("array size must be a constant");
        if (+sz[1] > 1000) throw new Unsupported("array too large");
        return ["Arr", {sort: SORT[e[1]], items: new Array(+sz[1]).fill(e[1] === "D" ? "0.0" : e[1] === "Z" ? "false" : "0")}];
      case "arrlit":
        return ["Arr", {sort: SORT[e[1]], items: e[2].map(function (x) { return self.conv(self.ev(x, env, sorts), SORT[e[1]])[1]; })}];
      case "not": a = this.ev(e[1], env, sorts); return ["Bool", "(not " + a[1] + ")"];
      case "cast":
        a = this.ev(e[2], env, sorts);
        if (e[1] === "I" && a[0] === "Real") return ["Int", "(jtrunc " + a[1] + ")"];
        if (e[1] === "D" && a[0] === "Int") return ["Real", "(to_real " + a[1] + ")"];
        return a;
      case "ite":
        var c = this.ev(e[1], env, sorts); u = this.unify(this.ev(e[2], env, sorts), this.ev(e[3], env, sorts));
        return [u[0], "(ite " + c[1] + " " + u[1] + " " + u[2] + ")"];
      case "call":
        var args = e[2].map(function (x) { return self.ev(x, env, sorts); }), f = e[1].replace(/^java\.lang\./, "");
        var callee = this.methods[f + "/" + args.length] && this.all[f + "/" + args.length];
        if (callee) return this.call(callee, args, env);
        if ((f === "Math.min" || f === "Math.max") && args.length === 2) { u = this.unify(args[0], args[1]); return [u[0], "(ite (" + (f === "Math.min" ? "<=" : ">=") + " " + u[1] + " " + u[2] + ") " + u[1] + " " + u[2] + ")"]; }
        if (f === "Math.abs" && args.length === 1) return [args[0][0], "(ite (>= " + args[0][1] + " " + (args[0][0] === "Int" ? "0" : "0.0") + ") " + args[0][1] + " (- " + args[0][1] + "))"];
        var nm = "fn_" + f.replace(/\W/g, "_") + "_" + args.map(function (x) { return x[0]; }).join("_");
        this.ufs[nm] = [args.map(function (x) { return x[0]; }), "Real"];
        return ["Real", args.length ? "(" + nm + " " + args.map(function (x) { return x[1]; }).join(" ") + ")" : nm];
      case "bin":
        var op = e[1];
        a = this.ev(e[2], env, sorts); b = this.ev(e[3], env, sorts);
        if (op === "&&" || op === "||") return ["Bool", "(" + (op === "&&" ? "and" : "or") + " " + a[1] + " " + b[1] + ")"];
        if ((op === "&" || op === "|" || op === "^") && a[0] === "Bool") return ["Bool", op === "&" ? "(and " + a[1] + " " + b[1] + ")" : op === "|" ? "(or " + a[1] + " " + b[1] + ")" : "(xor " + a[1] + " " + b[1] + ")"];
        if (["&", "|", "^", "<<", ">>", ">>>"].indexOf(op) >= 0) throw new Unsupported("bit operations are not supported");
        u = this.unify(a, b);
        if (op === "==") return ["Bool", "(= " + u[1] + " " + u[2] + ")"];
        if (op === "!=") return ["Bool", "(not (= " + u[1] + " " + u[2] + "))"];
        if (["<", ">", "<=", ">="].indexOf(op) >= 0) return ["Bool", "(" + op + " " + u[1] + " " + u[2] + ")"];
        if (op === "+" || op === "-" || op === "*") return [u[0], "(" + op + " " + u[1] + " " + u[2] + ")"];
        if (op === "/") return u[0] === "Int" ? ["Int", "(jdiv " + u[1] + " " + u[2] + ")"] : ["Real", "(/ " + u[1] + " " + u[2] + ")"];
        if (op === "%") { if (u[0] !== "Int") throw new Unsupported("% on doubles"); return ["Int", "(jmod " + u[1] + " " + u[2] + ")"]; }
    }
    throw new Unsupported("cannot translate " + e[0]);
  },
  assign: function (env, sorts, name, val) {
    if (!(name in sorts)) throw new Unsupported("assignment to undeclared " + name);
    var want = sorts[name], t = val[1];
    if (want === "Arr") { if (val[0] !== "Arr") throw new Unsupported("not an array: " + name); env[name] = val; return; }
    if (val[0] !== want) t = want === "Real" && val[0] === "Int" ? "(to_real " + t + ")" : want === "Int" && val[0] === "Real" ? "(jtrunc " + t + ")" : t;
    env[name] = [want, this.share(want, t)];
  },
  ite: function (sort, c, a, b) { return a === b ? a : this.share(sort, "(ite " + c + " " + a + " " + b + ")"); },
  // c ? a : b for whole values, arrays element by element
  iteVal: function (c, a, b) {
    if (a === b) return a;
    if (a[0] !== "Arr") return [a[0], this.ite(a[0], c, a[1], b[1])];
    var x = a[1], y = b[1], self = this;
    if (!x || !y || x.items.length !== y.items.length) throw new Unsupported("an array that is allocated on only some paths");
    return ["Arr", {sort: x.sort, items: x.items.map(function (t, i) { return self.ite(x.sort, c, t, y.items[i]); })}];
  },
  merge: function (env, c, e1, e2) {
    c = this.share("Bool", c);
    var self = this;
    Object.keys(e1).forEach(function (v) { if (v in e2) env[v] = self.iteVal(c, e1[v], e2[v]); });
  },
  run: function (stmts, env, sorts) {
    var self = this;
    stmts.forEach(function (s) {
      var done = env.__done[1], before = Object.assign({}, env);
      self.step(s, env, sorts);
      if (done !== "false") Object.keys(env).forEach(function (v) { if (v in before && env[v] !== before[v]) env[v] = self.iteVal(done, before[v], env[v]); });
    });
  },
  conv: function (val, want) {
    if (val[0] === want || want === "Arr") return val;
    if (want === "Real" && val[0] === "Int") return ["Real", "(to_real " + val[1] + ")"];
    if (want === "Int" && val[0] === "Real") return ["Int", "(jtrunc " + val[1] + ")"];
    if (want === "Real" && val[0] === "Bool") return ["Real", "(ite " + val[1] + " 1.0 0.0)"];
    return val;
  },
  // index of an array: the element term (an ite over positions) and, when it can be out of bounds, the exception flag
  index: function (env, sorts, arr, idxExpr) {
    if (!arr || arr[0] !== "Arr") throw new Unsupported("not an array");
    if (!arr[1]) throw new Unsupported("array used before it is allocated");
    var n = arr[1].items.length, ix = this.ev(idxExpr, env, sorts);
    if (ix[0] !== "Int") throw new Unsupported("array index is not an int");
    if (/^\d+$/.test(ix[1])) { var k = +ix[1]; if (k >= n) this.raise(env, "true"); return {lit: k < n ? k : null, ix: ix[1], n: n}; }
    var i = this.share("Int", ix[1]);
    this.raise(env, "(or (< " + i + " 0) (>= " + i + " " + n + "))");
    return {lit: null, ix: i, n: n};
  },
  raise: function (env, cond) { env.__exc = ["Bool", env.__exc[1] === "false" ? this.share("Bool", cond) : this.share("Bool", "(or " + env.__exc[1] + " " + cond + ")")]; },
  // a call to a method of the class, inlined: its own locals, return value and exception flag
  call: function (m, args, env) {
    if (this.depth >= 8) throw new Unsupported("recursion is not supported");
    var cenv = {__done: ["Bool", "false"], __exc: ["Bool", "false"], __rsort: m.ret === "void" ? "Int" : SORT[TYPE[m.ret]]}, csorts = {}, self = this;
    cenv.__ret = [cenv.__rsort, cenv.__rsort === "Real" ? "0.0" : cenv.__rsort === "Bool" ? "false" : "0"];
    m.params.forEach(function (p, i) { csorts[p.name] = SORT[p.type]; cenv[p.name] = self.conv(args[i], SORT[p.type]); cenv[p.name] = [SORT[p.type], self.share(SORT[p.type], cenv[p.name][1])]; });
    this.depth++;
    try { this.run(this.methods[m.key], cenv, csorts); } finally { this.depth--; }
    if (cenv.__exc[1] !== "false") this.raise(env, cenv.__exc[1]);
    return cenv.__ret;
  },
  step: function (s, env, sorts) {
    var self = this, c, e1, e2;
    switch (s.k) {
      case "block": this.run(s.body, env, sorts); return;
      case "decl":
        s.vars.forEach(function (d) {
          if (s.type[0] === "A") { sorts[d[0]] = "Arr"; env[d[0]] = d[1] ? self.ev(d[1], env, sorts) : ["Arr", null]; return; }
          sorts[d[0]] = SORT[s.type];
          if (d[1]) self.assign(env, sorts, d[0], self.ev(d[1], env, sorts));
          else env[d[0]] = [SORT[s.type], s.type === "D" ? "0.0" : s.type === "Z" ? "false" : "0"];
        });
        return;
      case "assign": this.assign(env, sorts, s.name, this.ev(s.e, env, sorts)); return;
      case "astore":
        var arr = env[s.name], at = this.index(env, sorts, arr, s.idx), v = this.conv(this.ev(s.e, env, sorts), arr[1].sort)[1];
        v = this.share(arr[1].sort, v);
        env[s.name] = ["Arr", {sort: arr[1].sort, items: arr[1].items.map(function (t, i) {
          return at.lit !== null ? (i === at.lit ? v : t) : at.ix === undefined ? t : self.ite(arr[1].sort, "(= " + at.ix + " " + i + ")", v, t);
        })}];
        return;
      case "if":
        c = this.ev(s.cond, env, sorts);
        e1 = Object.assign({}, env); e2 = Object.assign({}, env);
        var s1 = Object.assign({}, sorts), s2 = Object.assign({}, sorts);
        this.run([s.then], e1, s1); if (s.els) this.run([s.els], e2, s2);
        this.merge(env, c[1], e1, e2);
        return;
      case "loop":
        this.bounded = true;
        if (s.init) this.step(s.init, env, sorts);
        if (s.isDo) this.run([s.body], env, sorts);
        for (var i = 0; i < UNROLL; i++) {
          c = this.ev(s.cond, env, sorts);
          var g = env.__done[1] === "false" ? c[1] : "(and " + c[1] + " (not " + env.__done[1] + "))";
          var body = Object.assign({}, env), bs = Object.assign({}, sorts);
          this.run([s.body].concat(s.upd ? [s.upd] : []), body, bs);
          this.merge(env, g, body, Object.assign({}, env));
        }
        c = this.ev(s.cond, env, sorts);
        this.assume.push("(or (not " + c[1] + ") " + env.__done[1] + ")");
        return;
      case "return":
        var want = env.__rsort || "Real", r = s.e ? this.conv(this.ev(s.e, env, sorts), want) : [want, env.__ret[1]];
        env.__ret = [want, this.share(want, r[1])];
        env.__done = ["Bool", "true"];
        return;
      case "uf":
        // the abstracted statement: every variable it may write becomes UF(variables it reads, as they are now)
        var args = Object.keys(s.reads).filter(function (v) { return v in env && v.indexOf("__") !== 0 && env[v][0] !== "Arr"; }).sort();
        Object.keys(s.defs).forEach(function (v) {
          var sort = s.defs[v] ? SORT[s.defs[v]] : sorts[v];
          if (!sort) throw new Unsupported("unknown type of " + v);
          sorts[v] = sort;
          var nm = "UF_" + v + "_L" + s.id + "_" + args.length;
          self.ufs[nm] = [args.map(function (x) { return env[x][0]; }), sort];
          env[v] = [sort, args.length ? "(" + nm + " " + args.map(function (x) { return env[x][1]; }).join(" ") + ")" : nm];
        });
        return;
      case "break": case "continue": throw new Unsupported(s.k + " is not supported");
    }
  }
};

var PRELUDE = "(define-fun jdiv ((a Int) (b Int)) Int (ite (>= a 0) (ite (> b 0) (div a b) (- (div a (- b)))) (ite (> b 0) (- (div (- a) b)) (div (- a) (- b)))))\n" +
  "(define-fun jmod ((a Int) (b Int)) Int (- a (* b (jdiv a b))))\n" +
  "(define-fun jtrunc ((x Real)) Int (ite (>= x 0.0) (to_int x) (- (to_int (- x)))))\n";

// ao / an: abstracted bodies of every method of each version ("name/arity" -> statements)
function buildQuery(mo, mn, ao, an) {
  var sym = new Sym(), envs = [];
  [[mo, ao], [mn, an]].forEach(function (p) {
    var env = {__done: ["Bool", "false"], __ret: ["Real", "ret_none"], __exc: ["Bool", "false"]}, sorts = {};
    p[0].params.forEach(function (q) { env[q.name] = [SORT[q.type], q.name]; sorts[q.name] = SORT[q.type]; });
    sym.methods = p[1]; sym.all = p[0].methods;
    sym.run(p[1][p[0].key], env, sorts);
    envs.push(env);
  });
  var decl = mo.params.map(function (q) { return "(declare-fun " + q.name + " () " + SORT[q.type] + ")\n"; }).join("") + "(declare-fun ret_none () Real)\n";
  decl += mo.params.filter(function (q) { return q.type !== "Z"; }).map(function (q) {
    var lo = q.type === "I" ? String(-MIN).replace(/^/, "(- ") + ")" : "(- " + (-MIN).toFixed(1) + ")", hi = q.type === "I" ? String(MAX) : MAX.toFixed(1);
    return "(assert (and (<= " + lo + " " + q.name + ") (<= " + q.name + " " + hi + ")))\n";
  }).join("");
  Object.keys(sym.ufs).sort().forEach(function (n) { decl += "(declare-fun " + n + " (" + sym.ufs[n][0].join(" ") + ") " + sym.ufs[n][1] + ")\n"; });
  sym.defs.forEach(function (d) { decl += "(declare-fun " + d[0] + " () " + d[1] + ")\n(assert (= " + d[0] + " " + d[2] + "))\n"; });
  sym.assume.forEach(function (x) { decl += "(assert " + x + ")\n"; });
  // same result: both throw, or neither does and the returned values are equal
  var xo = envs[0].__exc[1], xn = envs[1].__exc[1], same = "(= " + envs[0].__ret[1] + " " + envs[1].__ret[1] + ")";
  var claim = xo === "false" && xn === "false" ? same : "(and (= " + xo + " " + xn + ") (or " + xo + " " + same + "))";
  // the UFs the formula actually mentions (an abstracted statement whose result is never used is not worth refining)
  var body = sym.defs.map(function (d) { return d[2]; }).concat(sym.assume, [claim]).join(" ");
  var used = Object.keys(sym.ufs).filter(function (n) { return new RegExp("[ (]" + n + "[ )]").test(" " + body + " "); });
  return {smt: PRELUDE + decl + "(assert (not " + claim + "))\n(check-sat)\n" + (mo.params.length ? "(get-value (" + mo.params.map(function (q) { return q.name; }).join(" ") + "))\n" : ""),
          vacuity: sym.assume.length ? PRELUDE + decl + "(check-sat)\n" : null, ufs: used, bounded: sym.bounded};
}

// ---------------------------------------------------------------- z3 output
function sexprs(s) {
  var toks = s.match(/\(|\)|[^\s()]+/g) || [], i = 0;
  function one() { var t = toks[i++]; if (t !== "(") return t; var l = []; while (toks[i] !== ")" && i < toks.length) l.push(one()); i++; return l; }
  var out = []; while (i < toks.length) out.push(one()); return out;
}
function value(x) {
  if (typeof x === "string") return x === "true" ? true : x === "false" ? false : Number(x);
  if (x[0] === "-" && x.length === 2) return -value(x[1]);
  if (x[0] === "/" && x.length === 3) return value(x[1]) / value(x[2]);
  return NaN;
}

// ---------------------------------------------------------------- the loop
async function analyze(oldSrc, newSrc, z3eval, onStep) {
  var mo = Engine.parseMethod(oldSrc), mn = Engine.parseMethod(newSrc);
  var maps = lineMaps(oldSrc, newSrc), oldLines = oldSrc.split("\n");
  var changed = []; for (var l = 1; l <= oldLines.length; l++) if (!maps.o2n[l] && !maps.blankOld[l - 1]) changed.push(l);
  var concrete = {}, iters = [], verdict = null, reason = null, cex = null;
  for (var it = 0; it < 60; it++) {
    var seen = {};
    var absAll = function (m, side) { var out = {}; Object.keys(m.methods).forEach(function (k) { out[k] = abstract(m.methods[k].stmts, side, maps, concrete, seen, m.methods); }); return out; };
    var q = buildQuery(mo, mn, absAll(mo, "old"), absAll(mn, "new"));
    var out = (await z3eval(q.smt)).trim(), status = out.split("\n")[0].trim();
    var rec = {iter: it, abstracted: Object.keys(seen).map(Number).sort(function (a, b) { return a - b; }), status: status, bounded: q.bounded,
               smt: q.smt, out: out};
    iters.push(rec);
    if (status === "unsat") {
      if (q.vacuity) { rec.vacuity = q.vacuity; rec.vacuityOut = (await z3eval(q.vacuity)).trim(); }
      if (q.vacuity && rec.vacuityOut.split("\n")[0] !== "sat") { verdict = "UNKNOWN"; reason = "every input runs a loop more than " + UNROLL + " times"; }
      else { verdict = "EQUIVALENT"; reason = "for inputs in " + MIN + ".." + MAX + (q.bounded ? ", loops up to " + UNROLL + " iterations" : ""); }
      break;
    }
    var inputs = null;
    if (status === "sat") {
      inputs = {};
      var vals = sexprs(out.slice(out.indexOf("\n") + 1))[0] || [];
      vals.forEach(function (p) { if (Array.isArray(p)) inputs[p[0]] = value(p[1]); });
      mo.params.forEach(function (p) { if (!(p.name in inputs)) inputs[p.name] = 0; });
      rec.model = inputs;
      var ro = Engine.run(mo, inputs).value, rn = Engine.run(mn, inputs).value;
      rec.run = [ro, rn];
      if (ro !== rn) { verdict = "NOT EQUIVALENT"; cex = {inputs: inputs, old: ro, new: rn}; rec.real = true; break; }
      rec.real = false;
    }
    // refine: make one abstracted statement concrete again; prefer the ones the formula uses, closest to a change
    var used = {}; q.ufs.forEach(function (n) { var m = /_L(\d+)_\d+$/.exec(n); if (m) used[m[1]] = 1; });
    var cand = rec.abstracted.filter(function (id) { return used[id]; });
    if (!cand.length) cand = rec.abstracted;
    if (!cand.length) { verdict = "UNKNOWN"; reason = status === "sat" ? "difference only from integer overflow or the loop bound" : "z3: " + status; break; }
    var dist = function (id) { return Math.min.apply(null, changed.map(function (c) { return Math.abs(c - id); }).concat([1e9])); };
    cand.sort(function (a, b) { return dist(a) - dist(b) || a - b; });
    rec.pick = cand[0];
    concrete[cand[0]] = true;
    if (onStep) onStep(rec);
  }
  if (!verdict) { verdict = "UNKNOWN"; reason = "too many refinement steps"; }
  return {verdict: verdict, reason: reason, counterexample: cex, iterations: iters, changed: changed, o2n: maps.o2n};
}

root.ArdiffLite = {analyze: analyze, UNROLL: UNROLL};
})(typeof window !== "undefined" ? window : globalThis);
