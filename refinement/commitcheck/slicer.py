"""Dynamic backward slice over an executed line sequence (regex-level, no Java parser).

Starting from the return statement, walk the trace backwards and keep a step when it defines a variable
the kept steps still need (data dependence) or when it is the condition/loop header that a kept step sits
under (control dependence). Good enough for the numeric methods ARDiff handles; field/array aliasing is
approximated by name.
"""
import re

KEYWORDS = {"if", "else", "for", "while", "do", "return", "int", "long", "short", "byte", "char", "double", "float",
            "boolean", "new", "true", "false", "null", "final", "static", "public", "private", "protected", "this",
            "switch", "case", "break", "continue", "default", "void", "var", "instanceof", "try", "catch", "throw"}
CONTROL = re.compile(r"^\s*(?:\}\s*)?(if|for|while|else|do|switch|case|default)\b")
IDENT = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)(?![\w$])(?!\s*\()")


def strip(line):
    line = re.sub(r"//.*", "", line)
    line = re.sub(r"/\*.*?\*/", "", line)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', line)


def defs_uses(line):
    code = strip(line)
    defs = set()
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*(?:\[[^\]]*\])?\s*(?:[+\-*/%&|^]|<<|>>|>>>)?=(?!=)", code):
        if m.start() > 0 and code[m.start() - 1] in "=!<>":
            continue
        defs.add(m.group(1))
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*(?:\+\+|--)|(?:\+\+|--)\s*([A-Za-z_$][\w$]*)", code):
        defs.add(m.group(1) or m.group(2))
    # variables only: skip keywords and class names like Math (capitalised but not ALL_CAPS constants)
    uses = {n for n in IDENT.findall(code) if n not in KEYWORDS and (not n[0].isupper() or n.isupper())}
    # a plain "x = ..." does not read x; compound ops and ++ do
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*=(?!=)", code):
        if m.start() == 0 or code[m.start() - 1] not in "=!<>+-*/%&|^":
            if not re.search(r"(?<![\w$])" + re.escape(m.group(1)) + r"(?![\w$])", code[m.end():]):
                uses.discard(m.group(1))
    # declared type names are not variables
    uses -= set(re.findall(r"\b(?:int|long|short|byte|char|double|float|boolean)\s+", code))
    return defs, uses


def controllers(lines):
    """0-based line -> set of 0-based lines of the if/for/while/else headers it is nested under (by indentation)."""
    ind = [len(l) - len(l.lstrip()) if l.strip() else None for l in lines]
    out = {}
    for i, l in enumerate(lines):
        if ind[i] is None:
            continue
        ctl, need = set(), ind[i]
        for j in range(i - 1, -1, -1):
            if ind[j] is None or ind[j] >= need:
                continue
            need = ind[j]
            m = CONTROL.match(lines[j])
            if m:
                ctl.add(j)
                if m.group(1) == "else":            # else depends on the matching if
                    for k in range(j - 1, -1, -1):
                        if ind[k] is not None and ind[k] == ind[j] and re.match(r"\s*(?:\}\s*)?if\b", lines[k]):
                            ctl.add(k); break
            if need == 0:
                break
        # braceless "if (c)" / "for (..)" / "else" on the previous line owns this line whatever its indentation
        for j in range(i - 1, -1, -1):
            if ind[j] is None:
                continue
            prev = strip(lines[j]).rstrip()
            if CONTROL.match(lines[j]) and not prev.endswith(("{", ";", "}")):
                ctl.add(j)
                ctl |= out.get(j, set())
            break
        out[i] = ctl
    return out


def dynamic_slice(lines, trace):
    """lines: source lines; trace: executed 0-based line numbers in order. -> sorted step indices in the slice."""
    if not trace:
        return []
    ctl = controllers(lines)
    du = {}
    keep, need, pend = {len(trace) - 1}, set(), set()
    last = trace[-1]
    du[last] = du.get(last) or defs_uses(lines[last])
    need |= du[last][1]
    pend |= ctl.get(last, set())
    for k in range(len(trace) - 2, -1, -1):
        ln = trace[k]
        if ln not in du:
            du[ln] = defs_uses(lines[ln]) if ln < len(lines) else (set(), set())
        d, u = du[ln]
        take = bool(d & need) or ln in pend
        if take:
            keep.add(k)
            need = (need - d) | u
            pend = (pend - {ln}) | ctl.get(ln, set())
    return sorted(keep)
