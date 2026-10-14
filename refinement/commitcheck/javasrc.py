"""Lightweight Java source scanner: finds classes, fields and methods without a full parser.

Good enough for ARDiff-style code (numeric methods in plain classes). It understands comments,
string/char literals and brace nesting; it does not resolve types or generics beyond text.
"""
import re
from dataclasses import dataclass, field

METHOD_HEADER = re.compile(
    r"^(?P<annos>(?:@\w+(?:\([^)]*\))?\s+)*)"
    r"(?P<mods>(?:(?:public|protected|private|static|final|abstract|synchronized|native|strictfp)\s+)*)"
    r"(?:<[^>]*>\s+)?"
    r"(?P<ret>[\w$.<>\[\], ?]+?)\s+(?P<name>[A-Za-z_$][\w$]*)\s*"
    r"\((?P<params>[^)]*)\)\s*(?:throws\s+[\w$.,\s]+)?$",
    re.S,
)
CLASS_HEADER = re.compile(r"\b(class|interface|enum)\s+(?P<name>[A-Za-z_$][\w$]*)")
KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new", "else", "do", "try", "synchronized"}


@dataclass
class Method:
    cls: str
    name: str
    ret: str
    params: list            # [(type, name)]
    modifiers: list
    text: str               # full declaration incl. annotations/javadoc-free header and body
    body: str               # text between the outer braces
    start_line: int         # 1-based, header line
    end_line: int

    @property
    def is_static(self):
        return "static" in self.modifiers

    @property
    def signature(self):
        return f"{self.name}({','.join(norm_type(t) for t, _ in self.params)})"

    @property
    def key(self):
        return f"{self.cls}.{self.signature}"

    def normalized(self):
        return normalize_code(self.text)


@dataclass
class ClassInfo:
    name: str
    methods: list = field(default_factory=list)
    fields: list = field(default_factory=list)   # raw field declaration texts
    start_line: int = 0


def norm_type(t):
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"\bfinal\b", "", t)
    return t.replace("...", "[]")


def strip_comments(src):
    """Replace comments with spaces (keeping newlines) so offsets and line numbers stay valid."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in src[i:j])); i = j
        elif c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); i = j + 1
        else:
            out.append(c); i += 1
    return "".join(out)


def normalize_code(s):
    s = strip_comments(s)
    return re.sub(r"\s+", " ", s).strip()


def _match_brace(src, i):
    """src[i] == '{' (comments already blanked). Return index of the matching '}'."""
    depth, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            i = j + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces")


def _parse_params(p):
    p = p.strip()
    if not p:
        return []
    parts, depth, cur = [], 0, ""
    for ch in p:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    out = []
    for part in parts:
        part = re.sub(r"@\w+\s*", "", part).strip()
        part = re.sub(r"^final\s+", "", part)
        m = re.match(r"(.+?)\s*(\.\.\.)?\s+([A-Za-z_$][\w$]*)\s*(\[\s*\])*$", part, re.S)
        if not m:
            out.append((part, "")); continue
        t = m.group(1) + ("[]" if m.group(2) else "") + ("[]" if m.group(4) else "")
        out.append((t.strip(), m.group(3)))
    return out


def _from_code(src, clean, a, b):
    """src[a:b] starting at the first non-blank char of the comment-free text (drops leading comments)."""
    seg = clean[a:b]
    a += len(seg) - len(seg.lstrip())
    return src[a:b].strip()


def _line_of(src, idx):
    return src.count("\n", 0, idx) + 1


def parse(src):
    """Return list of ClassInfo for top-level (and nested) classes in src."""
    clean = strip_comments(src)
    classes = []
    _scan_body(src, clean, 0, len(clean), None, classes)
    return classes


def _scan_body(src, clean, start, end, cls, classes):
    """Scan [start, end) at member level of class `cls` (None = compilation unit)."""
    i, seg_start = start, start
    while i < end:
        c = clean[i]
        if c in "\"'":
            j = i + 1
            while j < end and clean[j] != c:
                j += 2 if clean[j] == "\\" else 1
            i = j + 1
            continue
        if c == ";":
            decl = clean[seg_start:i].strip()
            if cls is not None and decl and "(" not in decl.split("=")[0] and not decl.startswith(("import", "package")):
                cls.fields.append(_from_code(src, clean, seg_start, i + 1))
            i += 1; seg_start = i
            continue
        if c == "{":
            close = _match_brace(clean, i)
            header = clean[seg_start:i].strip()
            hm = CLASS_HEADER.search(header)
            if hm and not header.endswith(")"):
                ci = ClassInfo(hm.group("name"), start_line=_line_of(clean, seg_start))
                classes.append(ci)
                _scan_body(src, clean, i + 1, close, ci, classes)
            elif cls is not None:
                mm = METHOD_HEADER.match(re.sub(r"\s+", " ", header))
                if mm and mm.group("name") not in KEYWORDS and mm.group("ret").split()[-1] not in KEYWORDS:
                    hstart = seg_start + (len(clean[seg_start:i]) - len(clean[seg_start:i].lstrip()))
                    cls.methods.append(Method(
                        cls=cls.name, name=mm.group("name"), ret=mm.group("ret").strip(),
                        params=_parse_params(mm.group("params")),
                        modifiers=mm.group("mods").split(),
                        text=src[hstart:close + 1], body=src[i + 1:close],
                        start_line=_line_of(clean, hstart), end_line=_line_of(clean, close)))
                elif "=" in header:   # field initialised with a block, e.g. array initialiser
                    j = clean.find(";", close)
                    if j > 0:
                        cls.fields.append(_from_code(src, clean, seg_start, j + 1)); close = j
            i = close + 1; seg_start = i
            continue
        if c == "}" :
            i += 1; seg_start = i
            continue
        i += 1


def called_names(method):
    """Simple names invoked as methods inside the body (no receiver resolution)."""
    names = set()
    for m in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", strip_comments(method.body)):
        if m.group(1) not in KEYWORDS:
            names.add(m.group(1))
    return names


def referenced_fields(method, cls):
    """Field declarations of `cls` whose names appear in the method body."""
    body = strip_comments(method.body)
    out = []
    for f in cls.fields:
        head = f.split("=")[0]
        names = re.findall(r"([A-Za-z_$][\w$]*)\s*(?:\[\s*\])*\s*(?:,|$)", head.strip().rstrip(";"))
        if any(re.search(r"(?<![\w$.])" + re.escape(n) + r"\b", body) for n in names if n):
            out.append(f)
    return out
