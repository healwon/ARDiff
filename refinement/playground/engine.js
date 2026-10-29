// Browser-side engine for the playground: parse the first method of oldV/newV, run it with Java int semantics,
// diff the two versions, and judge each change by running hybrids (old + just that change) on many inputs.
// Everything here is plain JS so the page works without a server; it tests, it does not prove.
(function (root) {
"use strict";

var TYPES = {int: "I", long: "I", short: "I", byte: "I", char: "I", double: "D", float: "D", boolean: "Z"};
var MAX_STEPS = 20000;

function Unsupported(msg) { this.message = msg; }

// ---------------------------------------------------------------- text helpers
function stripComments(src) {
  var out = "", i = 0, n = src.length;
  while (i < n) {
    if (src.startsWith("//", i)) { var j = src.indexOf("\n", i); j = j < 0 ? n : j; out += " ".repeat(j - i); i = j; }
    else if (src.startsWith("/*", i)) { var k = src.indexOf("*/", i + 2); k = k < 0 ? n : k + 2; out += src.slice(i, k).replace(/[^\n]/g, " "); i = k; }
    else if (src[i] === '"' || src[i] === "'") { var q = src[i], m = i + 1; while (m < n && src[m] !== q) m += src[m] === "\\" ? 2 : 1; out += src.slice(i, m + 1); i = m + 1; }
    else { out += src[i]; i++; }
  }
  return out;
}

function matchBrace(s, i) {
  for (var d = 0; i < s.length; i++) {
    if (s[i] === "{") d++;
    else if (s[i] === "}") { d--; if (d === 0) return i; }
  }
  throw new Unsupported("unbalanced braces");
}

// ---------------------------------------------------------------- tokens
var TOK = /\s*(?:(\d+\.\d*(?:[eE][-+]?\d+)?[dDfF]?|\.\d+(?:[eE][-+]?\d+)?[dDfF]?|\d+[eE][-+]?\d+[dDfF]?|\d+[lLdDfF]?)|([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)|(>>>=|<<=|>>=|>>>|\+\+|--|&&|\|\||==|!=|<=|>=|\+=|-=|\*=|\/=|%=|<<|>>|[-+*\/%<>=!?:;,(){}\[\]&|^~]))/y;

function tokenize(text, line0) {
  var out = [], pos = 0, line = line0;
  while (pos < text.length) {
    if (!text.slice(pos).trim()) break;
    TOK.lastIndex = pos;
    var m = TOK.exec(text);
    if (!m) throw new Unsupported("unexpected '" + text.slice(pos, pos + 12).trim() + "'");
    var kind = m[1] !== undefined ? "num" : m[2] !== undefined ? "id" : "op";
    var tok = m[1] || m[2] || m[3];
    var start = m.index + m[0].indexOf(tok);
    line += (text.slice(pos, start).match(/\n/g) || []).length;
    out.push({k: kind, t: tok, line: line});
    pos = TOK.lastIndex;
  }
  return out;
}

// ---------------------------------------------------------------- parser
function Parser(toks) { this.t = toks; this.i = 0; }
Parser.prototype = {
  peek: function (k) { return this.t[this.i + (k || 0)] || {k: null, t: null, line: null}; },
  at: function (t) { return this.peek().t === t; },
  take: function (t) {
    var x = this.peek();
    if (x.t === null || (t !== undefined && x.t !== t)) throw new Unsupported("expected '" + t + "' but found '" + x.t + "' (line " + x.line + ")");
    this.i++; return x;
  },
  takeAny: function (ts) { var x = this.peek(); if (ts.indexOf(x.t) < 0) throw new Unsupported("unexpected '" + x.t + "'"); this.i++; return x; },
  block: function () { var items = []; while (this.peek().t !== null && !this.at("}")) items.push(this.stmt()); return items; },
  stmt: function () {
    var x = this.peek(), t = x.t, line = x.line, s;
    if (t === "{") { this.take("{"); var body = this.block(); var end = this.take("}").line; return {k: "block", body: body, l0: line, l1: end}; }
    if (t === "if") {
      this.take("if"); this.take("("); var c = this.expr(); this.take(")");
      var th = this.stmt(), el = null;
      if (this.at("else")) { this.take("else"); el = this.stmt(); }
      return {k: "if", cond: c, then: th, els: el, l0: line, l1: (el || th).l1};
    }
    if (t === "for") {
      this.take("for"); this.take("(");
      var init = this.at(";") ? (this.take(";"), null) : this.simpleList([";"]);
      var cond = this.at(";") ? ["bool", true] : this.expr(); this.take(";");
      var upd = this.at(")") ? (this.take(")"), null) : this.simpleList([")"]);
      var b = this.stmt();
      return {k: "loop", init: init, cond: cond, upd: upd, body: b, l0: line, l1: b.l1};
    }
    if (t === "while") { this.take("while"); this.take("("); var wc = this.expr(); this.take(")"); var wb = this.stmt(); return {k: "loop", init: null, cond: wc, upd: null, body: wb, l0: line, l1: wb.l1}; }
    if (t === "do") { this.take("do"); var db = this.stmt(); this.take("while"); this.take("("); var dc = this.expr(); this.take(")"); var de = this.take(";").line; return {k: "loop", init: null, cond: dc, upd: null, body: db, isDo: true, l0: line, l1: de}; }
    if (t === "return") { this.take("return"); var e = this.at(";") ? null : this.expr(); var re = this.take(";").line; return {k: "return", e: e, l0: line, l1: re}; }
    if (t === "break" || t === "continue") { this.take(); var be = this.take(";").line; return {k: t, l0: line, l1: be}; }
    if (t === ";") { this.take(";"); return {k: "block", body: [], l0: line, l1: line}; }
    if (t === "switch" || t === "try" || t === "throw") throw new Unsupported("'" + t + "' is not supported");
    s = this.simple([";"]); s.l0 = line; return s;
  },
  simpleList: function (terms) {
    var line = this.peek().line, items = [this.simple([",", ";", ")"])];
    while (this.t[this.i - 1].t === ",") items.push(this.simple([",", ";", ")"]));
    if (terms.indexOf(this.t[this.i - 1].t) < 0) throw new Unsupported("bad for header");
    return items.length === 1 ? items[0] : {k: "block", body: items, l0: line, l1: items[items.length - 1].l1};
  },
  simple: function (terms) {
    var x = this.peek(), line = x.line;
    if (x.t === "final") { this.take(); x = this.peek(); }
    if (x.k === "id" && TYPES[x.t] && this.peek(1).k === "id") {
      var ty = TYPES[this.take().t], vars = [];
      for (;;) {
        var name = this.take().t, init = null;
        if (this.at("=")) { this.take("="); init = this.expr(); }
        vars.push([name, init]);
        if (this.at(",") && terms.indexOf(",") < 0) { this.take(","); continue; }
        break;
      }
      var end = this.takeAny(terms).line;
      return {k: "decl", type: ty, vars: vars, l0: line, l1: end};
    }
    if (x.t === "++" || x.t === "--") {
      var op0 = this.take().t, nm = this.take().t, e0 = this.takeAny(terms).line;
      return {k: "assign", name: nm, e: ["bin", op0[0], ["var", nm], ["num", "1"]], l0: line, l1: e0};
    }
    if (x.k === "id") {
      var n2 = this.take().t, op = this.take().t, e;
      if (op === "++" || op === "--") e = ["bin", op[0], ["var", n2], ["num", "1"]];
      else if (["=", "+=", "-=", "*=", "/=", "%="].indexOf(op) >= 0) { e = this.expr(); if (op !== "=") e = ["bin", op[0], ["var", n2], e]; }
      else throw new Unsupported("unsupported statement near '" + n2 + " " + op + "'");
      var e1 = this.takeAny(terms).line;
      return {k: "assign", name: n2, e: e, l0: line, l1: e1};
    }
    throw new Unsupported("unsupported statement starting with '" + x.t + "' (line " + line + ")");
  },
  expr: function () {
    var c = this.binary(0);
    if (this.at("?")) { this.take("?"); var a = this.expr(); this.take(":"); var b = this.expr(); return ["ite", c, a, b]; }
    return c;
  },
  LV: [["||"], ["&&"], ["|"], ["^"], ["&"], ["==", "!="], ["<", ">", "<=", ">="], ["<<", ">>", ">>>"], ["+", "-"], ["*", "/", "%"]],
  binary: function (lv) {
    if (lv === this.LV.length) return this.unary();
    var left = this.binary(lv + 1);
    while (this.LV[lv].indexOf(this.peek().t) >= 0 && this.peek().k === "op") { var op = this.take().t; left = ["bin", op, left, this.binary(lv + 1)]; }
    return left;
  },
  unary: function () {
    var t = this.peek().t;
    if (t === "-" || t === "+" || t === "!" || t === "~") { this.take(); var e = this.unary(); return t === "-" ? ["neg", e] : t === "!" ? ["not", e] : t === "~" ? ["bnot", e] : e; }
    if (t === "(" && TYPES[this.peek(1).t] && this.peek(2).t === ")") { this.take("("); var ty = TYPES[this.take().t]; this.take(")"); return ["cast", ty, this.unary()]; }
    var p = this.primary();
    if (this.at("++") || this.at("--")) throw new Unsupported("x++ inside an expression is not supported");
    return p;
  },
  primary: function () {
    var x = this.peek();
    if (x.t === "(") { this.take("("); var e = this.expr(); this.take(")"); return e; }
    if (x.k === "num") { this.take(); return ["num", x.t]; }
    if (x.t === "true" || x.t === "false") { this.take(); return ["bool", x.t === "true"]; }
    if (x.k === "id" && this.peek(1).t === "=") { this.take(); this.take("="); return ["assignx", x.t, this.expr()]; }
    if (x.k === "id") {
      this.take();
      if (this.at("(")) {
        this.take("("); var args = [];
        while (!this.at(")")) { args.push(this.expr()); if (this.at(",")) this.take(","); }
        this.take(")"); return ["call", x.t, args];
      }
      return ["var", x.t];
    }
    throw new Unsupported("unexpected '" + x.t + "' (line " + x.line + ")");
  }
};

// first method of the class: header, parameters, statements with 1-based line numbers of the whole file
function parseMethod(src) {
  var clean = stripComments(src);
  var re = /(?:public|private|protected|static|final|\s)*\b(int|long|short|byte|char|double|float|boolean|void)\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?:throws[^{]*)?\{/g;
  var m = re.exec(clean);
  if (!m) throw new Unsupported("no method found (expected e.g. public static double snippet(int x) { ... })");
  var open = m.index + m[0].length - 1, close = matchBrace(clean, open);
  var params = [];
  m[3].split(",").map(function (p) { return p.trim(); }).filter(Boolean).forEach(function (p) {
    var mm = /^(?:final\s+)?([A-Za-z_$][\w$]*)\s+([A-Za-z_$][\w$]*)$/.exec(p);
    if (!mm || !TYPES[mm[1]]) throw new Unsupported("parameter '" + p + "' is not a primitive");
    params.push({name: mm[2], type: TYPES[mm[1]], jtype: mm[1]});
  });
  var line0 = clean.slice(0, open + 1).split("\n").length;
  var p = new Parser(tokenize(clean.slice(open + 1, close), line0));
  return {name: m[2], ret: m[1], params: params, stmts: p.block()};
}

// ---------------------------------------------------------------- interpreter (Java semantics for int/double)
function JavaError(name) { this.name = name; }
function Ret(v) { this.v = v; }
function Brk() {}
function Cont() {}

function toInt(v) { return Math.trunc(v) | 0; }

function run(method, inputs, opts) {
  opts = opts || {};
  var env = {}, types = {}, trace = [], steps = 0;
  method.params.forEach(function (p) { env[p.name] = p.type === "I" ? (inputs[p.name] | 0) : p.type === "Z" ? !!inputs[p.name] : +inputs[p.name]; types[p.name] = p.type; });
  function tick(line) { if (++steps > MAX_STEPS) throw new JavaError("timeout"); if (opts.trace && line) trace.push(line); }
  function typeOf(e) {
    switch (e[0]) {
      case "num": return /[.eEdDfF]/.test(e[1]) && !/^0x/i.test(e[1]) ? "D" : "I";
      case "bool": case "not": return "Z";
      case "var": return types[e[1]] || "I";
      case "assignx": return types[e[1]] || "I";
      case "neg": case "bnot": return typeOf(e[1]);
      case "cast": return e[1];
      case "ite": var a = typeOf(e[2]), b = typeOf(e[3]); return a === "D" || b === "D" ? "D" : a;
      case "call": return /^Math\.(min|max|abs)$/.test(e[1]) && e[2].every(function (x) { return typeOf(x) === "I"; }) ? "I" : "D";
      case "bin":
        if (["==", "!=", "<", ">", "<=", ">=", "&&", "||"].indexOf(e[1]) >= 0) return "Z";
        if (["<<", ">>", ">>>"].indexOf(e[1]) >= 0) return typeOf(e[2]);
        var l = typeOf(e[2]), r = typeOf(e[3]); return l === "D" || r === "D" ? "D" : l === "Z" ? "Z" : "I";
    }
    return "I";
  }
  function ev(e) {
    switch (e[0]) {
      case "num": var s = e[1].replace(/[lLdDfF]$/, ""); return /[.eE]/.test(s) || /[dDfF]$/.test(e[1]) ? parseFloat(s) : parseInt(s, 10) | 0;
      case "bool": return e[1];
      case "var": if (!(e[1] in env)) throw new Unsupported("unknown variable '" + e[1] + "'"); return env[e[1]];
      case "assignx": var v = ev(e[2]); assign(e[1], v, typeOf(e[2])); return env[e[1]];
      case "neg": var x = ev(e[1]); return typeOf(e[1]) === "I" ? (-x) | 0 : -x;
      case "not": return !ev(e[1]);
      case "bnot": return ~ev(e[1]);
      case "cast": var c = ev(e[2]); return e[1] === "I" ? (typeOf(e[2]) === "D" ? toInt(c) : c | 0) : e[1] === "D" ? +c : c;
      case "ite": return ev(e[1]) ? ev(e[2]) : ev(e[3]);
      case "call":
        var args = e[2].map(ev), f = e[1].replace(/^java\.lang\./, "");
        if (f === "Math.min") return Math.min(args[0], args[1]);
        if (f === "Math.max") return Math.max(args[0], args[1]);
        if (f === "Math.abs") return typeOf(e[2][0]) === "I" ? Math.abs(args[0]) | 0 : Math.abs(args[0]);
        var g = f.replace(/^Math\./, "");
        if (f.indexOf("Math.") === 0 && typeof Math[g] === "function") return Math[g].apply(null, args);
        throw new Unsupported("call to " + e[1] + " is not supported");
      case "bin":
        var op = e[1];
        if (op === "&&") return !!(ev(e[2]) && ev(e[3]));
        if (op === "||") return !!(ev(e[2]) || ev(e[3]));
        var a = ev(e[2]), b = ev(e[3]), isInt = typeOf(e) === "I";
        switch (op) {
          case "+": return isInt ? (a + b) | 0 : a + b;
          case "-": return isInt ? (a - b) | 0 : a - b;
          case "*": return isInt ? Math.imul(a, b) : a * b;
          case "/": if (isInt) { if (b === 0) throw new JavaError("ArithmeticException"); return toInt(a / b); } return a / b;
          case "%": if (isInt && b === 0) throw new JavaError("ArithmeticException"); return isInt ? (a % b) | 0 : a % b;
          case "<": return a < b; case ">": return a > b; case "<=": return a <= b; case ">=": return a >= b;
          case "==": return a === b; case "!=": return a !== b;
          case "&": return typeof a === "boolean" ? a && b : a & b;
          case "|": return typeof a === "boolean" ? a || b : a | b;
          case "^": return typeof a === "boolean" ? a !== b : a ^ b;
          case "<<": return a << b; case ">>": return a >> b; case ">>>": return a >>> b;
        }
    }
    throw new Unsupported("cannot evaluate " + e[0]);
  }
  function assign(name, v, vt) {
    if (!(name in types)) throw new Unsupported("assignment to undeclared '" + name + "'");
    var t = types[name];
    env[name] = t === "I" ? (vt === "D" ? toInt(v) : v | 0) : t === "D" ? +v : !!v;
  }
  function exec(s) {
    switch (s.k) {
      case "block": s.body.forEach(exec); return;
      case "decl": tick(s.l0); s.vars.forEach(function (d) { types[d[0]] = s.type; env[d[0]] = s.type === "Z" ? false : 0; if (d[1]) assign(d[0], ev(d[1]), typeOf(d[1])); }); return;
      case "assign": tick(s.l0); assign(s.name, ev(s.e), typeOf(s.e)); return;
      case "if": tick(s.l0); if (ev(s.cond)) exec(s.then); else if (s.els) exec(s.els); return;
      case "loop":
        if (s.init) { tick(s.l0); exec(s.init); }
        var first = true;
        for (;;) {
          if (!(s.isDo && first)) { tick(s.l0); if (!ev(s.cond)) break; }
          first = false;
          try { exec(s.body); } catch (x) { if (x instanceof Brk) break; if (!(x instanceof Cont)) throw x; }
          if (s.upd) { tick(s.l0); exec(s.upd); }
        }
        return;
      case "return": tick(s.l0); throw new Ret(s.e ? ev(s.e) : undefined);
      case "break": tick(s.l0); throw new Brk();
      case "continue": tick(s.l0); throw new Cont();
    }
  }
  var out;
  try { method.stmts.forEach(exec); out = {value: "(no return)"}; }
  catch (x) {
    if (x instanceof Ret) out = {value: fmt(x.v, method.ret)};
    else if (x instanceof JavaError) out = {value: x.name, error: true};
    else throw x;
  }
  out.trace = trace;
  return out;
}

function fmt(v, ret) {
  if (ret === "double" || ret === "float") {
    if (typeof v === "boolean") return String(v);
    if (Number.isNaN(v)) return "NaN";
    if (!isFinite(v)) return v > 0 ? "Infinity" : "-Infinity";
    if (Number.isInteger(v) && Math.abs(v) < 1e7) return v.toFixed(1);
    var s = String(v);
    return /e/.test(s) ? s.replace(/e\+?/, "E") : s;
  }
  return String(v);
}

// ---------------------------------------------------------------- inputs
function inputSet(params, limit) {
  limit = limit || 2500;
  var ints = [-100, -51, -50, -11, -10, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 9, 10, 11, 12, 49, 50, 51, 99, 100];
  var dbls = [-100, -10.5, -2.5, -1, -0.5, 0, 0.5, 1, 2.5, 10.5, 100];
  var doms = params.map(function (p) { return p.type === "Z" ? [false, true] : p.type === "D" ? dbls : ints; });
  var total = doms.reduce(function (a, d) { return a * d.length; }, 1), out = [];
  if (total <= limit) {
    (function rec(i, cur) {
      if (i === params.length) { out.push(Object.assign({}, cur)); return; }
      doms[i].forEach(function (v) { cur[params[i].name] = v; rec(i + 1, cur); });
    })(0, {});
    return out;
  }
  var seed = 12345;
  function rnd(n) { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; }
  var zero = {}; params.forEach(function (p) { zero[p.name] = p.type === "Z" ? false : 0; });
  out.push(zero);
  params.forEach(function (p, i) { doms[i].forEach(function (v) { var o = Object.assign({}, zero); o[p.name] = v; out.push(o); }); });
  while (out.length < limit) { var o = {}; params.forEach(function (p, i) { o[p.name] = doms[i][rnd(doms[i].length)]; }); out.push(o); }
  return out;
}

// ---------------------------------------------------------------- diff
function lcsOps(a, b) {
  var n = a.length, m = b.length, dp = [];
  for (var i = 0; i <= n; i++) { dp.push(new Int32Array(m + 1)); }
  for (i = n - 1; i >= 0; i--) for (var j = m - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  var ops = []; i = 0; j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) { ops.push(["=", i, j]); i++; j++; }
    else if (j < m && (i === n || dp[i][j + 1] >= dp[i + 1][j])) { ops.push(["+", null, j]); j++; }
    else { ops.push(["-", i, null]); i++; }
  }
  return ops;
}

var TOKRE = /[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|\S/g;
function tokSpans(line) { var out = [], m; TOKRE.lastIndex = 0; while ((m = TOKRE.exec(line))) out.push([m.index, m.index + m[0].length, m[0]]); return out; }

// rows [[oldLineIdx|null, newLineIdx|null]], changed token spans per side
function diffRows(oldText, newText) {
  var norm = function (l) { return stripComments(l).replace(/\b(?:oldV|newV)\b/g, "V").replace(/\s+/g, " ").trim() + "\u0000" + l.trim(); };
  var a = oldText.split("\n"), b = newText.split("\n");
  var na = a.map(function (l) { return l.replace(/\b(?:oldV|newV)\b/g, "V").replace(/\s+/g, " ").trim(); });
  var nb = b.map(function (l) { return l.replace(/\b(?:oldV|newV)\b/g, "V").replace(/\s+/g, " ").trim(); });
  var ops = lcsOps(na, nb), rows = [], lch = {}, rch = {}, k = 0;
  while (k < ops.length) {
    if (ops[k][0] === "=") { rows.push([ops[k][1], ops[k][2]]); k++; continue; }
    var dels = [], adds = [];
    while (k < ops.length && ops[k][0] !== "=") { if (ops[k][0] === "-") dels.push(ops[k][1]); else adds.push(ops[k][2]); k++; }
    for (var q = 0; q < Math.max(dels.length, adds.length); q++) {
      var l = q < dels.length ? dels[q] : null, r = q < adds.length ? adds[q] : null;
      rows.push([l, r]);
      if (l !== null && r !== null) {
        var ta = tokSpans(a[l]), tb = tokSpans(b[r]);
        lcsOps(ta.map(function (x) { return x[2]; }), tb.map(function (x) { return x[2]; })).forEach(function (o) {
          if (o[0] === "-") (lch[l] = lch[l] || []).push(ta[o[1]].slice(0, 2));
          if (o[0] === "+") (rch[r] = rch[r] || []).push(tb[o[2]].slice(0, 2));
        });
      } else if (l !== null) lch[l] = tokSpans(a[l]).map(function (x) { return x.slice(0, 2); });
      else rch[r] = tokSpans(b[r]).map(function (x) { return x.slice(0, 2); });
    }
  }
  return {rows: rows, lch: lch, rch: rch, ops: ops};
}

// ---------------------------------------------------------------- changes and their roles
function hunks(oldText, newText) {
  var a = oldText.split("\n"), b = newText.split("\n");
  var key = function (l) { return stripComments(l).replace(/\b(?:oldV|newV)\b/g, "V").replace(/\s+/g, " ").trim(); };
  var ops = lcsOps(a.map(key), b.map(key)), out = [], k = 0;
  while (k < ops.length) {
    if (ops[k][0] === "=") { k++; continue; }
    var h = {old: [], neu: []};
    while (k < ops.length && ops[k][0] !== "=") { if (ops[k][0] === "-") h.old.push(ops[k][1] + 1); else h.neu.push(ops[k][2] + 1); k++; }
    var before = k - h.old.length - h.neu.length - 1;
    h.oldAt = before >= 0 ? ops[before][1] + 1 : 0; h.newAt = before >= 0 ? ops[before][2] + 1 : 0;
    out.push(h);
  }
  return out;
}

function touches(stmts, lines) { var r = []; stmts.forEach(function (s, i) { if (lines.some(function (l) { return l >= s.l0 && l <= s.l1; })) r.push(i); }); return r; }

function analyze(oldSrc, newSrc) {
  var res = {error: null};
  try { res.mo = parseMethod(oldSrc); res.mn = parseMethod(newSrc); }
  catch (e) { if (e instanceof Unsupported) { res.error = e.message; return res; } throw e; }
  var mo = res.mo, mn = res.mn, so = mo.stmts, sn = mn.stmts;
  if (mo.params.map(function (p) { return p.type; }).join() !== mn.params.map(function (p) { return p.type; }).join())
    { res.error = "old and new need the same parameter types"; return res; }
  // group changed lines by the top-level statements they touch
  var groups = [];
  hunks(oldSrc, newSrc).forEach(function (h) {
    var io = touches(so, h.old), inn = touches(sn, h.neu);
    var comment = h.old.concat([]).length + h.neu.length > 0 && !io.length && !inn.length;
    if (comment) return;
    if (!io.length) io = []; if (!inn.length) inn = [];
    var posO = io.length ? io[0] : so.filter(function (s) { return s.l1 < h.oldAt + 1; }).length;
    var posN = inn.length ? inn[0] : sn.filter(function (s) { return s.l1 < h.newAt + 1; }).length;
    var last = groups[groups.length - 1];
    if (last && (io.some(function (i) { return last.io.indexOf(i) >= 0; }) || inn.some(function (i) { return last.in_.indexOf(i) >= 0; }))) {
      io.forEach(function (i) { if (last.io.indexOf(i) < 0) last.io.push(i); }); inn.forEach(function (i) { if (last.in_.indexOf(i) < 0) last.in_.push(i); });
      last.oldLines = last.oldLines.concat(h.old); last.newLines = last.newLines.concat(h.neu);
    } else groups.push({io: io, in_: inn, posO: posO, posN: posN, oldLines: h.old, newLines: h.neu});
  });
  groups.forEach(function (g) {
    g.io.sort(function (x, y) { return x - y; }); g.in_.sort(function (x, y) { return x - y; });
    var span = function (st, idx) { var ls = []; idx.forEach(function (i) { for (var l = st[i].l0; l <= st[i].l1; l++) ls.push(l); }); return ls; };
    g.oldLines = span(so, g.io).length ? span(so, g.io) : g.oldLines;
    g.newLines = span(sn, g.in_).length ? span(sn, g.in_) : g.newLines;
  });
  // hybrid programs: old with only change g applied / new with change g reverted
  function splice(base, from, keepIdx, putIdx, pos) {
    var out = [], put = putIdx.map(function (i) { return from[i]; }), done = false;
    base.forEach(function (s, i) {
      if (keepIdx.indexOf(i) >= 0) { if (!done) { out = out.concat(put); done = true; } return; }
      if (!done && !keepIdx.length && i === pos) { out = out.concat(put); done = true; }
      out.push(s);
    });
    if (!done) out = out.concat(put);
    return out;
  }
  var inputs = inputSet(mo.params);
  function outcome(stmts) {
    var m = {params: mo.params, ret: mo.ret, stmts: stmts};
    return inputs.map(function (inp) {
      try { return run(m, inp).value; } catch (e) { if (e instanceof Unsupported) return "?unsupported: " + e.message; throw e; }
    });
  }
  var base = outcome(so), full = outcome(sn);
  var diffIdx = []; base.forEach(function (v, i) { if (v !== full[i]) diffIdx.push(i); });
  res.inputs = inputs; res.base = base; res.full = full; res.diffIdx = diffIdx;
  res.unsupported = base.concat(full).filter(function (v) { return typeof v === "string" && v.indexOf("?unsupported") === 0; })[0] || null;
  res.groups = groups.map(function (g) {
    var alone = outcome(splice(so, sn, g.io, g.in_, g.posO));
    var without = outcome(splice(sn, so, g.in_, g.io, g.posN));
    var bad = alone.concat(without).some(function (v) { return typeof v === "string" && v.indexOf("?unsupported") === 0; });
    var aloneDiff = [], matters = [];
    alone.forEach(function (v, i) { if (v !== base[i]) aloneDiff.push(i); });
    without.forEach(function (v, i) { if (v !== full[i]) matters.push(i); });
    var role;
    if (bad) role = "isolate";
    else if (!aloneDiff.length && !matters.length) role = "none";
    else if (aloneDiff.length && !diffIdx.length) role = "undone";
    else if (aloneDiff.length) role = "changes";
    else role = "together";
    var ex = aloneDiff.filter(function (i) { return diffIdx.indexOf(i) >= 0; })[0];
    if (ex === undefined) ex = aloneDiff[0];
    return {oldLines: g.oldLines, newLines: g.newLines, role: role, nAlone: aloneDiff.length, nMatters: matters.length, example: ex};
  });
  // "undone by" / "together with": which other changes interact
  res.groups.forEach(function (g, k) {
    if (g.role === "undone" || g.role === "together") g.with = res.groups.map(function (h, j) { return j; }).filter(function (j) { return j !== k && res.groups[j].role !== "none"; });
  });
  return res;
}

root.Engine = {parseMethod: parseMethod, run: run, analyze: analyze, diffRows: diffRows, inputSet: inputSet, Unsupported: Unsupported};
})(typeof window !== "undefined" ? window : globalThis);
