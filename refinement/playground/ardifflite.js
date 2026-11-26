// ARDiff-lite: ARDiff's abstraction-refinement loop re-implemented for the browser (needs engine.js and a z3 "eval").
//
//   1. common code is abstracted as in ARDiff: consecutive unchanged statements form a block, and every variable a
//      block writes becomes UF_<var>_B<block>(the block's inputs it depends on); both versions use the same UFs
//   2. each version is executed symbolically path by path, as Symbolic PathFinder does: at most 5 branches on the
//      inputs per path (ARDiff's default bound, SPF's search.depth_limit), ints as mathematical integers, Java / and %,
//      inputs -100..100 unless the task says otherwise. Its summary is the disjunction over its paths of (path condition and Ret = the returned value), and z3 is asked, as in
//      ARDiff, for summaryOld and not (summaryOld = summaryNew)
//   3. unsat -> EQUIVALENT. sat -> with nothing abstracted, NOT EQUIVALENT; otherwise z3 is asked whether
//      summaryOld and summaryOld = summaryNew can hold (for some input and some meaning of the abstracted blocks):
//      if not, NOT EQUIVALENT; if so, one abstracted statement is made concrete again (refinement), chosen with
//      ARDiff's heuristics H1-H3, and we go back to 1. The model's inputs are reported as the counterexample; they
//      are not run on the real code to decide.
//
// Calls to other methods of the class are inlined (their common statements are abstracted the same way);
// local arrays have a fixed, constant size and an index out of bounds is an exception, as in Java.
//
// This is a re-implementation, not ARDiff: the Java front end, the solver tactics and the tie-breaking of H3
// differ, and expressions such as Math.min or ?: stay terms instead of forking paths, so the steps and even the
// verdict can still differ from ARDiff's.
(function (root) {
"use strict";
var Engine = root.Engine;
var UNROLL = 5, BOUND = 5, ITER_CAP = 10000, MAX_PATHS = 4000, MAX_SUMMARY = 400000, H1_TIMEOUT = 2000, MIN = -100, MAX = 100, MAX_TERM = 200, TIME_LIMIT = 90000;

function rangeText(mo, ranges) {
  var own = mo.params.filter(function (q) { return ranges[q.name]; });
  if (!own.length) return MIN + ".." + MAX;
  return mo.params.filter(function (q) { return q.type !== "Z"; }).map(function (q) { var r = ranges[q.name] || [MIN, MAX]; return q.name + " " + r[0] + ".." + r[1]; }).join(", ");
}
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
function exprWrites(node, out) {
  if (Array.isArray(node)) {
    if ((node[0] === "assignx" || node[0] === "preinc" || node[0] === "postinc") && !(node[1] in out)) out[node[1]] = null;
    node.forEach(function (x) { if (x && typeof x === "object") exprWrites(x, out); });
  }
  return out;
}
function varsDefined(s, out) {
  out = out || {};
  if (!s) return out;
  ["e", "cond", "idx"].forEach(function (k) { if (s[k]) exprWrites(s[k], out); });
  if (s.k === "decl") s.vars.forEach(function (v) { if (v[1]) exprWrites(v[1], out); });
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
// variables an array size is computed from (new int[NTAB]): they must stay concrete so the size is a constant
function sizeVars(node, out) {
  out = out || {};
  if (Array.isArray(node)) { if (node[0] === "newarr") varsRead(node[2], out); node.forEach(function (x) { if (x && typeof x === "object") sizeVars(x, out); }); }
  else if (node && typeof node === "object") for (var k in node) if (node[k] && typeof node[k] === "object") sizeVars(node[k], out);
  return out;
}
// ---------------------------------------------------------------- common blocks (ARDiff's CommonBlockExtractor)
// Consecutive common statements at the same level form a block; a control statement goes into a block whole when
// nothing inside it is changed (or refined) and it has no return; otherwise it stays concrete and the statements
// inside it form blocks of their own. Each variable a block writes becomes UF_<var>_B<block>(the block's inputs that
// variable depends on). Statements are identified by their old line on both sides, and two statements are in the
// same block only when they are next to each other in both versions.
function adjacentPairs(stmts, side, maps, out) {
  out = out || {};
  var ids = stmts.map(function (s) { return commonId(s, side, maps); });
  for (var i = 0; i + 1 < ids.length; i++) if (ids[i] !== null && ids[i + 1] !== null) out[ids[i] + ">" + ids[i + 1]] = 1;
  stmts.forEach(function (s) {
    if (s.k === "block") adjacentPairs(s.body, side, maps, out);
    else if (s.k === "if") { adjacentPairs([s.then], side, maps, out); if (s.els) adjacentPairs([s.els], side, maps, out); }
    else if (s.k === "loop") adjacentPairs([s.body], side, maps, out);
  });
  return out;
}
// lines (old numbering) a statement spans that are refined
function touchesConcrete(s, side, maps, concrete) {
  for (var l = s.l0; l <= s.l1; l++) { var id = side === "old" ? l : maps.n2o[l]; if (id !== undefined && concrete[id]) return true; }
  return false;
}
// per variable a block writes: the block's inputs it depends on (data and control), like ARDiff's def-use chains
function blockDeps(stmts) {
  var D = {};
  var src = function (vars, ctx) { var out = Object.assign({}, ctx); Object.keys(vars).forEach(function (v) { if (D[v]) Object.assign(out, D[v]); else out[v] = 1; }); return out; };
  function walk(list, ctx) {
    list.forEach(function (s) {
      if (!s) return;
      if (s.k === "block") return walk(s.body, ctx);
      if (s.k === "if") {
        var c = src(varsRead(s.cond), ctx), before = Object.assign({}, D), defs = varsDefined(s);
        walk([s.then], c); var afterThen = D; D = Object.assign({}, before); walk([s.els], c);
        var afterElse = D; D = Object.assign({}, before);
        Object.keys(defs).forEach(function (v) { D[v] = Object.assign({}, c, afterThen[v] || {}, afterElse[v] || {}, before[v] || (defs[v] ? {} : {[v]: 1})); });
        return;
      }
      if (s.k === "loop") {
        if (s.init) walk([s.init], ctx);
        var defs2 = varsDefined(s), prev = null;
        for (var k = 0; k < 8 && JSON.stringify(D) !== prev; k++) {
          prev = JSON.stringify(D);
          var c2 = src(varsRead(s.cond), ctx), was = Object.assign({}, D);
          walk([s.body], c2); if (s.upd) walk([s.upd], c2);
          Object.keys(defs2).forEach(function (v) { D[v] = Object.assign({}, D[v] || {}, was[v] || {}, c2, src(varsRead(s.cond), {})); if (!was[v] && !defs2[v]) D[v][v] = 1; });
        }
        return;
      }
      var reads = varsRead(s), defs3 = varsDefined(s), r = src(reads, ctx);
      Object.keys(defs3).forEach(function (v) { D[v] = Object.assign({}, r); });
    });
  }
  walk(stmts, {});
  return D;
}
// the statements of a block that write each variable, with how many loops (inside the block) they sit in, for H3
function blockLines(stmts, side, maps) {
  var out = {};
  (function walk(list, loops) {
    list.forEach(function (s) {
      if (!s) return;
      if (s.k === "block") return walk(s.body, loops);
      if (s.k === "if") { walk([s.then], loops); walk([s.els], loops); return; }
      if (s.k === "loop") { if (s.init) walk([s.init], loops + 1); walk([s.body], loops + 1); if (s.upd) walk([s.upd], loops + 1); return; }
      var id = side === "old" ? s.l0 : maps.n2o[s.l0];
      Object.keys(varsDefined(s)).forEach(function (v) { (out[v] = out[v] || []).push({line: id, loops: loops, stmt: s}); });
    });
  })(stmts, 0);
  return out;
}
function abstract(stmts, side, maps, concrete, seen, methods, keep, pairs, blocks) {
  keep = keep || {};
  var out = [], run = [];
  var ok = function (s) {
    var defs = varsDefined(s);
    return commonId(s, side, maps) !== null && !touchesConcrete(s, side, maps, concrete) && !hasReturn(s) && !opaque(s, methods) &&
      !Object.keys(defs).some(function (v) { return keep[v]; });
  };
  var flush = function () {
    if (!run.length) return;
    var defs = {}; run.forEach(function (s) { varsDefined(s, defs); });
    if (!Object.keys(defs).length) { out.push.apply(out, run); run = []; return; }
    var id = commonId(run[0], side, maps);
    // every line of the block counts as abstracted (for the view); the block is known by its first statement
    run.forEach(function (s) { for (var l = s.l0; l <= s.l1; l++) { var o = side === "old" ? l : maps.n2o[l]; if (o !== undefined) seen[o] = seen[o] || {line: o, side: side}; } });
    if (blocks && side === "old") blocks[id] = blockLines(run, side, maps);
    out.push({k: "uf", id: id, defs: defs, deps: blockDeps(run), l0: run[0].l0, l1: run[run.length - 1].l1});
    run = [];
  };
  stmts.forEach(function (s) {
    if (ok(s)) {
      // stay in the current block only if the previous statement is right before this one in the other version too
      if (run.length && !pairs[commonId(run[run.length - 1], side, maps) + ">" + commonId(s, side, maps)]) flush();
      run.push(s); return;
    }
    flush();
    if (s.k === "block") out.push(Object.assign({}, s, {body: abstract(s.body, side, maps, concrete, seen, methods, keep, pairs, blocks)}));
    else if (s.k === "if") out.push(Object.assign({}, s, {then: abstract([s.then], side, maps, concrete, seen, methods, keep, pairs, blocks)[0], els: s.els ? abstract([s.els], side, maps, concrete, seen, methods, keep, pairs, blocks)[0] : null}));
    else if (s.k === "loop") out.push(Object.assign({}, s, {body: abstract([s.body], side, maps, concrete, seen, methods, keep, pairs, blocks)[0]}));
    else out.push(s);
  });
  flush();
  return out;
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
    var n = Engine.numLit(t);
    return n.isInt ? ["Int", n.v < 0 ? "(- " + (-n.v) + ")" : String(n.v)] : this.real(n.v);
  },
  real: function (v) {
    if (!isFinite(v)) throw new Unsupported("infinite or NaN constant");
    // exact decimal from the shortest round-trip form: digits * 10^exp, as an SMT-LIB rational
    var m = /^(\d+)(?:\.(\d+))?(?:e([-+]\d+))?$/.exec(String(Math.abs(v)));
    var digits = (m[1] + (m[2] || "")).replace(/^0+(?=\d)/, ""), exp = (+(m[3] || 0)) - (m[2] || "").length, r;
    if (exp >= 0) r = digits + "0".repeat(exp) + ".0";
    else r = "(/ " + digits + ".0 1" + "0".repeat(-exp) + ".0)";
    return ["Real", v < 0 ? "(- " + r + ")" : r];
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
      case "var":
        if (e[1] in env) return env[e[1]];
        var mc = Engine.MATHC[e[1].replace(/^java\.lang\./, "")];
        if (mc !== undefined) return e[1].indexOf("Integer.") >= 0 ? this.num(String(mc)) : this.real(mc);
        throw new Unsupported("unknown variable " + e[1]);
      case "preinc": case "postinc":
        var was = this.ev(["var", e[1]], env, sorts), one = was[0] === "Real" ? "1.0" : "1";
        this.assign(env, sorts, e[1], [was[0], "(" + e[2] + " " + was[1] + " " + one + ")"]);
        return e[0] === "preinc" ? env[e[1]] : was;
      case "str": throw new Unsupported("strings are not supported");
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
        if (/^(?:java\.lang\.)?System\.(out|err)\.print/.test(e[1])) return ["Int", "0"];      // output is not part of the result
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
      var done = self.stopped(env), before = Object.assign({}, env);
      self.step(s, env, sorts);
      if (done !== "false") Object.keys(env).forEach(function (v) { if (v in before && env[v] !== before[v]) env[v] = self.iteVal(done, before[v], env[v]); });
    });
  },
  // ---- path by path, as Symbolic PathFinder explores the method. A state is {env, sorts, pc: [conditions], stop,
  // depth} where stop is null, "ret", "brk" or "cont". A condition that depends on the inputs (or on an abstracted
  // block) forks the state and counts one step of depth; && and || are separate branches, as in the bytecode. A
  // condition on constants is just evaluated, so a loop with a fixed count runs as such. Like SPF's
  // search.depth_limit (ARDiff's bound, 5 by default), a path that would take more symbolic branches is dropped,
  // so the summary only describes the paths within the bound.
  paths: function (stmts, env, sorts) {
    this.npaths = 0; this.gmemo = {}; this.defIx = {};
    var self = this; this.defs.forEach(function (d, k) { self.defIx[d[0]] = k; });
    return this.execList(stmts, [{env: env, sorts: sorts, pc: [], stop: null, depth: 0}]);
  },
  fork: function (st, cond) {
    if (++this.npaths > MAX_PATHS) throw new Unsupported("more than " + MAX_PATHS + " paths");
    return {env: Object.assign({}, st.env), sorts: Object.assign({}, st.sorts), pc: st.pc.concat([cond]), stop: st.stop, depth: st.depth + 1};
  },
  // the value of a term without symbols (numbers, and definitions of such), or undefined
  ground: function (term) {
    var self = this;
    var num = function (x) { return /^-?\d+(\.\d+)?$/.test(x) ? +x : undefined; };
    function g(t) {
      if (!Array.isArray(t)) {
        if (t === "true") return true; if (t === "false") return false;
        if (num(t) !== undefined) return num(t);
        if (/^d\d+$/.test(t)) {
          if (!(t in self.gmemo)) { var k = self.defIx[t]; if (k === undefined) { k = self.defs.findIndex(function (d) { return d[0] === t; }); if (k < 0) throw 0; self.defIx[t] = k; } self.gmemo[t] = g(sexprs(self.defs[k][2])[0]); }
          return self.gmemo[t];
        }
        throw 0;
      }
      var op = t[0];
      if (op === "ite") return g(t[1]) ? g(t[2]) : g(t[3]);
      var a = t.slice(1).map(g), x = a[0], y = a[1];
      switch (op) {
        case "-": return a.length === 1 ? -x : x - y;
        case "+": return a.reduce(function (p, q) { return p + q; });
        case "*": return a.reduce(function (p, q) { return p * q; });
        case "/": if (y === 0) throw 0; return x / y;
        case "jdiv": if (y === 0) throw 0; return Math.trunc(x / y);
        case "jmod": if (y === 0) throw 0; return x - y * Math.trunc(x / y);
        case "to_real": return x;
        case "jtrunc": return Math.trunc(x);
        case "<": return x < y; case "<=": return x <= y; case ">": return x > y; case ">=": return x >= y;
        case "=": return x === y;
        case "not": return !x;
        case "and": return a.every(Boolean); case "or": return a.some(Boolean); case "xor": return x !== y;
      }
      throw 0;
    }
    try { var v = g(sexprs(term)[0]); return typeof v === "number" && !isFinite(v) ? undefined : v; } catch (e) { return undefined; }
  },
  // the states after a branch on e: [state, whether e held]
  forkCond: function (e, st) {
    var self = this, out = [];
    if (e[0] === "bin" && (e[1] === "&&" || e[1] === "||")) {
      this.forkCond(e[2], st).forEach(function (r) {
        if (e[1] === "&&" ? !r[1] : r[1]) out.push(r); else out.push.apply(out, self.forkCond(e[3], r[0]));
      });
      return out;
    }
    if (e[0] === "not") return this.forkCond(e[1], st).map(function (r) { return [r[0], !r[1]]; });
    var c = this.ev(e, st.env, st.sorts)[1], g = this.ground(c);
    if (g === true || g === false) return [[st, g]];
    if (st.depth >= (this.bound || BOUND)) { this.cut = true; return []; }
    return [[this.fork(st, c), true], [this.fork(st, "(not " + c + ")"), false]];
  },
  execList: function (stmts, states) {
    var self = this;
    stmts.forEach(function (s) {
      var next = [];
      states.forEach(function (st) { if (st.stop) next.push(st); else next.push.apply(next, self.execStmt(s, st)); });
      states = next;
    });
    return states;
  },
  execStmt: function (s, st) {
    var self = this;
    if (!s) return [st];
    switch (s.k) {
      case "block": return this.execList(s.body, [st]);
      case "if":
        var res = [];
        this.forkCond(s.cond, st).forEach(function (r) {
          res.push.apply(res, r[1] ? self.execList([s.then], [r[0]]) : s.els ? self.execList([s.els], [r[0]]) : [r[0]]);
        });
        return res;
      case "loop":
        var out = [], live, n = 0;
        if (s.init) this.step(s.init, st.env, st.sorts);
        live = s.isDo ? this.loopBody(s, [st], out) : [st];
        while (live.length) {
          if (++n > ITER_CAP) throw new Unsupported("a loop runs more than " + ITER_CAP + " times");
          var go = [];
          live.forEach(function (x) { self.forkCond(s.cond, x).forEach(function (r) { (r[1] ? go : out).push(r[0]); }); });
          live = this.loopBody(s, go, out);
        }
        return out;
      case "return":
        var want = st.env.__rsort || "Real", r = s.e ? this.conv(this.ev(s.e, st.env, st.sorts), want) : [want, st.env.__ret[1]];
        st.env.__ret = [want, this.share(want, r[1])]; st.stop = "ret";
        return [st];
      case "break": st.stop = "brk"; return [st];
      case "continue": st.stop = "cont"; return [st];
      default:
        this.step(s, st.env, st.sorts);
        return [st];
    }
  },
  // one iteration for each live state: body (continue ends it early), then the update; break and return leave the loop
  loopBody: function (s, states, out) {
    var self = this, live = [];
    this.execList([s.body], states).forEach(function (x) {
      if (x.stop === "brk") { x.stop = null; out.push(x); return; }
      if (x.stop === "ret") { out.push(x); return; }
      x.stop = null;
      if (s.upd) self.step(s.upd, x.env, x.sorts);
      live.push(x);
    });
    return live;
  },
  // the path has returned, or left the current loop iteration by break / continue
  stopped: function (env) {
    var xs = [env.__done[1], env.__brk[1], env.__cont[1]].filter(function (x) { return x !== "false"; });
    return !xs.length ? "false" : xs.length === 1 ? xs[0] : "(or " + xs.join(" ") + ")";
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
    var cenv = {__done: ["Bool", "false"], __brk: ["Bool", "false"], __cont: ["Bool", "false"], __exc: ["Bool", "false"], __rsort: m.ret === "void" ? "Int" : SORT[TYPE[m.ret]]}, csorts = {}, self = this;
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
      case "expr": this.ev(s.e, env, sorts); return;
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
        var outer = [env.__brk, env.__cont], F = ["Bool", "false"];
        env.__brk = F; env.__cont = F;
        if (s.init) this.step(s.init, env, sorts);
        // one iteration: the body, then (unless it broke out) the update; continue only skips the rest of the body
        var iter = function (e, so) { self.run([s.body], e, so); e.__cont = F; if (s.upd) self.run([s.upd], e, so); };
        if (s.isDo) iter(env, sorts);
        for (var i = 0; i < UNROLL; i++) {
          c = this.ev(s.cond, env, sorts);
          var stop = this.stopped(env), g = stop === "false" ? c[1] : "(and " + c[1] + " (not " + stop + "))";
          var body = Object.assign({}, env), bs = Object.assign({}, sorts);
          iter(body, bs);
          this.merge(env, g, body, Object.assign({}, env));
        }
        c = this.ev(s.cond, env, sorts);
        this.assume.push("(or (not " + c[1] + ") " + this.stopped(env) + ")");
        env.__brk = outer[0]; env.__cont = outer[1];
        return;
      case "break": env.__brk = ["Bool", "true"]; return;
      case "continue": env.__cont = ["Bool", "true"]; return;
      case "return":
        var want = env.__rsort || "Real", r = s.e ? this.conv(this.ev(s.e, env, sorts), want) : [want, env.__ret[1]];
        env.__ret = [want, this.share(want, r[1])];
        env.__done = ["Bool", "true"];
        return;
      case "uf":
        // the abstracted block: every variable it writes becomes UF(the block's inputs it depends on, as they are now)
        var vals = {};
        Object.keys(s.defs).forEach(function (v) {
          var args = Object.keys(s.deps[v] || {}).filter(function (x) { return x in env && x.indexOf("__") !== 0 && env[x][0] !== "Arr"; }).sort();
          var sort = s.defs[v] ? SORT[s.defs[v]] : sorts[v];
          if (!sort) throw new Unsupported("unknown type of " + v);
          sorts[v] = sort;
          var nm = "UF_" + v + "_B" + s.id + "_" + args.length;
          self.ufs[nm] = [args.map(function (x) { return env[x][0]; }), sort];
          vals[v] = [sort, args.length ? "(" + nm + " " + args.map(function (x) { return env[x][1]; }).join(" ") + ")" : nm];
        });
        Object.keys(vals).forEach(function (v) { env[v] = vals[v]; });
        return;
    }
  }
};

var PRELUDE = "(define-fun jdiv ((a Int) (b Int)) Int (ite (>= a 0) (ite (> b 0) (div a b) (- (div a (- b)))) (ite (> b 0) (- (div (- a) b)) (div (- a) (- b)))))\n" +
  "(define-fun jmod ((a Int) (b Int)) Int (- a (* b (jdiv a b))))\n" +
  "(define-fun jtrunc ((x Real)) Int (ite (>= x 0.0) (to_int x) (- (to_int (- x)))))\n";

// ao / an: abstracted bodies of every method of each version ("name/arity" -> statements)
// Each version's summary is, as in ARDiff, the disjunction over its paths of (path condition and the returned value):
// Ret = the value, plus Exc = whether the path throws. ARDiff's query is summaryOld and not (summaryOld = summaryNew).
function buildQuery(mo, mn, ao, an, ranges, bound) {
  var sym = new Sym(), sums = [], apps = [], merged = [];
  sym.bound = bound;
  [[mo, ao], [mn, an]].forEach(function (p) {
    var env = {__done: ["Bool", "false"], __brk: ["Bool", "false"], __cont: ["Bool", "false"], __ret: ["Real", "ret_none"], __exc: ["Bool", "false"]}, sorts = {};
    p[0].params.forEach(function (q) { env[q.name] = [SORT[q.type], q.name]; sorts[q.name] = SORT[q.type]; });
    sym.methods = p[1]; sym.all = p[0].methods;
    var defs0 = sym.defs.length, states;
    var one = function (pc, xr, rv) { return "(and " + pc.join(" ") + " (= Exc " + xr + ")" + (xr === "true" ? "" : xr === "false" ? " (= Ret " + rv + ")" : " (or " + xr + " (= Ret " + rv + "))") + ")"; };
    try {
      states = sym.paths(p[1][p[0].key], Object.assign({}, env), Object.assign({}, sorts));
      var size = 0; states.forEach(function (x) { size += x.pc.join(" ").length + x.env.__ret[1].length; });
      if (size > MAX_SUMMARY) throw new Unsupported("path summary larger than " + MAX_SUMMARY + " characters");
    }
    catch (e) {
      if (!(e instanceof Unsupported) || !/paths|path summary/.test(e.message)) throw e;
      // too many paths: this version is summarized as one term with the branches merged (if-then-else) instead
      merged.push(sums.length ? "new" : "old"); sym.defs.length = defs0;
      sym.run(p[1][p[0].key], env, sorts);
      states = [{pc: ["true"], env: env}];
    }
    var ps = states.map(function (x) { return one(x.pc.length ? x.pc : ["true"], x.env.__exc[1], x.env.__ret[1]); });
    sums.push(ps.length ? (ps.length === 1 ? ps[0] : "(or " + ps.join(" ") + ")") : "false");
    apps.push(sym.defs.slice(defs0).map(function (d) { return d[2]; }).concat(ps));
  });
  var decl = mo.params.map(function (q) { return "(declare-fun " + q.name + " () " + SORT[q.type] + ")\n"; }).join("") +
    "(declare-fun ret_none () Real)\n(declare-fun Ret () Real)\n(declare-fun Exc () Bool)\n";
  var rng = mo.params.filter(function (q) { return q.type !== "Z"; }).map(function (q) {
    var r = ranges[q.name] || [MIN, MAX], num = function (v) { var t = q.type === "I" ? String(Math.abs(v)) : Math.abs(v).toFixed(1); return v < 0 ? "(- " + t + ")" : t; };
    return "(and (<= " + num(r[0]) + " " + q.name + ") (<= " + q.name + " " + num(r[1]) + "))";
  });
  decl += rng.map(function (x) { return "(assert " + x + ")\n"; }).join("");
  Object.keys(sym.ufs).sort().forEach(function (n) { decl += "(declare-fun " + n + " (" + sym.ufs[n][0].join(" ") + ") " + sym.ufs[n][1] + ")\n"; });
  sym.defs.forEach(function (d) { decl += "(declare-fun " + d[0] + " () " + d[1] + ")\n(assert (= " + d[0] + " " + d[2] + "))\n"; });
  sym.assume.forEach(function (x) { decl += "(assert " + x + ")\n"; });      // loops in inlined callees
  var same = "(= " + sums[0] + " " + sums[1] + ")";
  // the UFs the formula actually mentions (an abstracted block whose result is never used is not worth refining)
  var body = sym.defs.map(function (d) { return d[2]; }).concat(sums).join(" ");
  var used = Object.keys(sym.ufs).filter(function (n) { return new RegExp("[ (]" + n + "[ )]").test(" " + body + " "); });
  return {smt: PRELUDE + decl + "(assert " + sums[0] + ")\n(assert (not " + same + "))\n(check-sat)\n" + (mo.params.length ? "(get-value (" + mo.params.map(function (q) { return q.name; }).join(" ") + "))\n" : ""),
          // ARDiff's satisfiability check (DSE.checkForSatisfiability): summaryOld and summaryOld = summaryNew
          agree: PRELUDE + decl + "(assert " + sums[0] + ")\n(assert " + same + ")\n(check-sat)\n",
          noPaths: sums[0] === "false" || sums[1] === "false", ufs: used, bounded: sym.bounded, cut: sym.cut, merged: merged,
          // with a merged summary (or a loop in an inlined callee) the loop bound is an assumption on the inputs:
          // if no input meets it, an unsat query says nothing
          vacuity: sym.assume.length ? PRELUDE + decl + "(check-sat)\n" : null,
          occ: occurrences(sym, apps), h1: function (f) { return h1Query(mo, sym, rng, same, f); }};
}

// ---------------------------------------------------------------- ARDiff's refinement heuristics (GradDiff.getNextToRefine)
function pr(t) { return Array.isArray(t) ? "(" + t.map(pr).join(" ") + ")" : t; }
function ufApps(term, ufs, out) {
  (function walk(t) {
    if (Array.isArray(t)) { if (ufs[t[0]]) { out.push([t[0], pr(t)]); } t.forEach(walk); }
    else if (ufs[t]) out.push([t, t]);
  })(sexprs(term)[0]);
  return out;
}
// how often each application of an abstracted function occurs in the old and in the new summary (H2 compares these)
function occurrences(sym, apps) {
  var count = function (terms) { var c = {}; terms.forEach(function (x) { ufApps(x, sym.ufs, []).forEach(function (a) { c[a[1]] = (c[a[1]] || 0) + 1; }); }); return c; };
  return {old: count(apps[0]), new: count(apps[1])};
}
// H1: every application of an abstracted function becomes a constant; is there a value for the applications of f
// that makes the two versions agree whatever the inputs and the other constants are?
function h1Query(mo, sym, rng, claim, f) {
  var consts = {}, n = 0;
  var subst = function (term) {
    var walk = function (t) {
      if (Array.isArray(t)) { if (sym.ufs[t[0]]) return key(t[0], pr(t)); return t.map(walk); }
      return sym.ufs[t] ? key(t, t) : t;
    };
    var key = function (fn, app) { if (!consts[app]) consts[app] = {name: "h1_" + (n++), fn: fn, sort: sym.ufs[fn][1]}; return consts[app].name; };
    return pr(walk(sexprs(term)[0]));
  };
  var defs = sym.defs.map(function (d) { return "(= " + d[0] + " " + subst(d[2]) + ")"; });
  var assume = sym.assume.map(subst), body = subst(claim);
  var all = Object.keys(consts).map(function (k) { return consts[k]; });
  if (!all.some(function (c) { return c.fn === f; })) return null;
  var bound = mo.params.map(function (q) { return "(" + q.name + " " + SORT[q.type] + ")"; }).concat(["(Ret Real)", "(Exc Bool)"])
    .concat(sym.defs.map(function (d) { return "(" + d[0] + " " + d[1] + ")"; }))
    .concat(all.filter(function (c) { return c.fn !== f; }).map(function (c) { return "(" + c.name + " " + c.sort + ")"; }));
  var pre = rng.concat(defs, assume);
  // a short time limit: ARDiff only takes a function from H1 when z3 says sat, and these queries rarely finish
  return "(set-option :timeout " + H1_TIMEOUT + ")\n" + PRELUDE + "(declare-fun ret_none () Real)\n" +
    all.filter(function (c) { return c.fn === f; }).map(function (c) { return "(declare-fun " + c.name + " () " + c.sort + ")\n"; }).join("") +
    "(assert (forall (" + bound.join(" ") + ") " + (pre.length ? "(=> (and " + pre.join(" ") + ") " + body + ")" : body) + "))\n(check-sat)\n";
}
// H3: the simplest statement first: the loops it sits in inside its block, plus * and / and method calls in it
function h3Score(e, src) {
  var s = e.stmt, n = e.loops;
  if (s.k !== "assign" && s.k !== "decl" && s.k !== "expr") return n;
  var text = Engine.stripComments(src.split("\n").slice(s.l0 - 1, s.l1).join("\n"));
  return n + (text.match(/[*\/]/g) || []).length + (text.match(/\b[A-Za-z_]\w*\s*\(/g) || []).length;
}
async function pickToRefine(q, rec, blocks, oldSrc, z3eval) {
  var parse = function (fn) { var m = /^UF_(.+)_B(\d+)_\d+$/.exec(fn); return m ? {v: m[1], block: +m[2]} : null; };
  var open = q.ufs.filter(function (fn) { var f = parse(fn); return f && blocks[f.block] && blocks[f.block][f.v]; });
  var h1 = [], h2 = [], fnOf = function (app) { return app.replace(/^\(/, "").split(" ")[0]; }, fnsOld = {};
  Object.keys(q.occ.old).forEach(function (app) { fnsOld[fnOf(app)] = 1; });
  // H1 (the functions of the old summary)
  for (var i = 0; i < open.length; i++) {
    if (!fnsOld[open[i]]) continue;
    var smt = q.h1(open[i]); if (!smt) continue;
    var a = (await z3eval(smt)).trim().split("\n")[0];
    if (a === "sat") h1.push(open[i]);
  }
  // H2: an application only in one summary, or occurring a different number of times
  var differ = {};
  Object.keys(q.occ.old).concat(Object.keys(q.occ.new)).forEach(function (app) { if ((q.occ.old[app] || 0) !== (q.occ.new[app] || 0)) differ[fnOf(app)] = 1; });
  open.forEach(function (fn) { if (differ[fn]) h2.push(fn); });
  var cand = h1.concat(h2.filter(function (fn) { return h1.indexOf(fn) < 0; }));
  if (!cand.length) cand = open;
  // H3 over the statements of the candidates' blocks that write their variable (ties: the earlier line)
  var ids = [], scores = {};
  cand.forEach(function (fn) { var f = parse(fn); blocks[f.block][f.v].forEach(function (e) { if (ids.indexOf(e.line) < 0) { ids.push(e.line); scores[e.line] = h3Score(e, oldSrc); } }); });
  ids.sort(function (x, y) { return scores[x] - scores[y] || x - y; });
  rec.heuristics = {h1: h1, h2: h2, h3: scores};
  return ids.length ? ids[0] : null;
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
// opts.ranges: {param: [lo, hi]} for the inputs to consider (default -100..100 for every number, as in ARDiff)
async function analyze(oldSrc, newSrc, z3eval, onStep, opts) {
  var ranges = (opts && opts.ranges) || {}, bound = (opts && opts.bound) || BOUND;      // opts.bound: like ARDiff's --b
  var mo = Engine.parseMethod(oldSrc), mn = Engine.parseMethod(newSrc);
  var maps = lineMaps(oldSrc, newSrc), oldLines = oldSrc.split("\n");
  var changed = []; for (var l = 1; l <= oldLines.length; l++) if (!maps.o2n[l] && !maps.blankOld[l - 1]) changed.push(l);
  var concrete = {}, iters = [], verdict = null, reason = null, cex = null;
  var pairsOld = {}, pairsNew = {};
  Object.keys(mo.methods).forEach(function (k) { adjacentPairs(mo.methods[k].stmts, "old", maps, pairsOld); });
  Object.keys(mn.methods).forEach(function (k) { adjacentPairs(mn.methods[k].stmts, "new", maps, pairsNew); });
  var started = Date.now();
  for (var it = 0; it < 60; it++) {
    if (Date.now() - started > TIME_LIMIT) { verdict = "UNKNOWN"; reason = "time limit (" + TIME_LIMIT / 1000 + " s)"; break; }
    var seen = {}, blocks = {};
    var absAll = function (m, side) {
      var out = {};
      Object.keys(m.methods).forEach(function (k) { out[k] = abstract(m.methods[k].stmts, side, maps, concrete, seen, m.methods, sizeVars(m.methods[k].stmts), side === "old" ? pairsNew : pairsOld, k === m.key ? blocks : null); });
      return out;
    };
    var q = buildQuery(mo, mn, absAll(mo, "old"), absAll(mn, "new"), ranges, bound), out;
    try { out = (await z3eval(q.smt)).trim(); } catch (e) { verdict = "UNKNOWN"; reason = "z3 failed: " + (e.message || e); break; }
    var status = out.split("\n")[0].trim();
    var rec = {iter: it, merged: q.merged, abstracted: Object.keys(seen).map(Number).sort(function (a, b) { return a - b; }), status: status, bounded: q.bounded,
               smt: q.smt, out: out};
    iters.push(rec);
    if (status === "unsat") {
      if (q.vacuity) { rec.vacuity = q.vacuity; rec.vacuityOut = (await z3eval(q.vacuity)).trim(); }
      if (q.noPaths) { verdict = "UNKNOWN"; reason = "every path takes more than " + bound + " branches on the inputs (ARDiff's bound)"; }
      else if (q.vacuity && rec.vacuityOut.split("\n")[0] !== "sat") { verdict = "UNKNOWN"; reason = "every input runs a loop more than " + UNROLL + " times"; }
      else { verdict = "EQUIVALENT"; reason = "for inputs in " + rangeText(mo, ranges) + (q.cut ? ", on the paths with up to " + bound + " branches on the inputs" : "") + (q.merged && q.merged.length && q.bounded ? ", loops up to " + UNROLL + " iterations" : ""); }
      break;
    }
    var inputs = null;
    if (status === "sat") {
      inputs = {};
      var vals = out.indexOf("\n") >= 0 ? sexprs(out.slice(out.indexOf("\n") + 1))[0] : null;
      if (!Array.isArray(vals)) vals = [];
      vals.forEach(function (p) { if (Array.isArray(p)) inputs[p[0]] = value(p[1]); });
      mo.params.forEach(function (p) { if (!(p.name in inputs)) inputs[p.name] = 0; });
      rec.model = inputs;
      var ro = Engine.run(mo, inputs).value, rn = Engine.run(mn, inputs).value;
      rec.run = [ro, rn];
      // as in ARDiff (GradDiff / DSE.checkForSatisfiability): with nothing abstracted, a difference is final; otherwise
      // the verdict is NOT EQUIVALENT only when no meaning of the abstracted statements lets the two versions agree.
      // The model is not run on the real code to decide; it is only reported as the counterexample.
      if (!q.ufs.length) { verdict = "NOT EQUIVALENT"; cex = {inputs: inputs, old: ro, new: rn}; rec.real = true; break; }
      rec.agreeOut = (await z3eval(q.agree)).trim();
      if (rec.agreeOut.split("\n")[0] === "unsat") { verdict = "NOT EQUIVALENT"; cex = {inputs: inputs, old: ro, new: rn}; rec.real = true; break; }
      rec.real = false;
    }
    // refine: make one abstracted statement concrete again, chosen with ARDiff's heuristics H1, H2 and H3
    var pick = await pickToRefine(q, rec, blocks, oldSrc, z3eval);
    if (pick === null) {
      if (status === "sat") { verdict = "NOT EQUIVALENT"; cex = {inputs: inputs, old: rec.run[0], new: rec.run[1]}; rec.real = true; }
      else { verdict = "UNKNOWN"; reason = "z3: " + status; }
      break;
    }
    rec.pick = pick;
    concrete[pick] = true;
    if (onStep) onStep(rec);
  }
  if (!verdict) { verdict = "UNKNOWN"; reason = "too many refinement steps"; }
  return {verdict: verdict, reason: reason, counterexample: cex, iterations: iters, changed: changed, o2n: maps.o2n};
}

root.ArdiffLite = {analyze: analyze, UNROLL: UNROLL};
})(typeof window !== "undefined" ? window : globalThis);
