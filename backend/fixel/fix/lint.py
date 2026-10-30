"""Patch linter: no symptom hiding (guide section 7.4).

A model rewarded for "the oracle stopped firing" could learn to hide the element instead of fixing the layout.
This blocks that class of patch before it is applied; its messages go back to the model as the tool result.
It errs strict: a blocked legitimate patch costs one retry, a symptom-hiding patch that slipped through would
undermine the whole tool. Deterministic code only, no model.
"""
import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
MARKUP = {".jsx", ".tsx", ".js", ".ts", ".html", ".vue", ".svelte", ".mdx"}

# (pattern, reason) checked against every ADDED line, in any file type.
FORBIDDEN = [
    (r"!important", "no !important"),
    (r"\bdisplay\s*:\s*none\b", "hides the element"),
    (r"\bvisibility\s*:\s*hidden\b", "hides the element"),
    (r"\bopacity\s*:\s*0(\.0+)?\s*([;}\"'`]|$)", "hides the element"),
    (r"\boverflow(-[xy])?\s*:\s*(hidden|clip)\b", "clipping hides the symptom"),
    (r"(?<![\w-])(hidden|invisible|opacity-0|overflow-hidden|overflow-x-hidden|overflow-y-hidden|overflow-clip)(?![\w-])",
     "hides or clips (Tailwind class or hidden attribute)"),
    (r"\bfont-size\s*:\s*0\b", "zero font size"),
    (r"(?<![\w-])(width|height|max-width|max-height)\s*:\s*0(px|%|em|rem)?\s*([;}\"'`]|$)", "collapses the element"),
    (r"(?<![\w-])(w-0|h-0|max-w-0|max-h-0|size-0|scale-0|sr-only)(?![\w-])", "collapses or hides the element"),
    (r"(?<![\w-])(truncate|text-ellipsis|line-clamp-\d+)(?![\w-])", "truncating text hides the symptom"),
    (r"\btext-overflow\s*:\s*ellipsis\b|-webkit-line-clamp", "truncating text hides the symptom"),
    (r"\bcolor\s*:\s*transparent\b|(?<![\w-])text-transparent(?![\w-])", "makes text invisible"),
    (r"\bclip(-path)?\s*:", "clips the element"),
    (r"\btransform\s*:\s*scale\(\s*0\s*[,)]", "collapses the element"),
    (r"\b(left|right|top|text-indent)\s*:\s*-\d{3,}", "moves the element off screen"),
    (r"\bpointer-events\s*:\s*none\b|(?<![\w-])pointer-events-none(?![\w-])",
     "defeats the hit test while the element is still covered"),
]
FORBIDDEN_RE = [(re.compile(p), why) for p, why in FORBIDDEN]

# styling contexts removed from a line before looking for visible copy
CLASS_CONTEXTS = [
    re.compile(r"""\bclass(?:Name)?\s*=\s*(?:"[^"]*"|'[^']*'|\{[^}]*\})"""),
    re.compile(r"\b(?:cn|clsx|classNames|twMerge|twJoin|cva|tw)\s*\([^)]*\)"),
    re.compile(r"@apply[^;]*;"),
]
TEXT = re.compile(r">([^<>{}]+)<|\"([^\"]{3,})\"|'([^']{3,})'")
BARE_UTILITIES = {"flex", "grid", "block", "inline", "relative", "absolute", "fixed", "sticky", "static", "container",
                  "contents", "table", "wrap", "nowrap", "grow", "shrink", "italic", "underline", "uppercase",
                  "lowercase", "capitalize", "border", "rounded", "shadow", "transition", "transform", "antialiased"}
TOKEN = re.compile(r"^[a-z][a-z0-9:/\[\]().%#_\-!@&>*,]*$")
TAG = re.compile(r"<[A-Za-z][\w.:-]*")


@dataclass
class FileDiff:
    path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    creates: bool = False
    deletes: bool = False
    renames: bool = False


def parse_diff(diff: str) -> list[FileDiff]:
    """Split a unified diff into per-file added/removed lines. Hunk line counts are honoured, so a removed line that
    itself starts with '--' (a CSS custom property) is not mistaken for a header."""
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    old_left = new_left = 0
    for line in diff.splitlines():
        if (old_left > 0 or new_left > 0) and cur is not None and line[:1] in ("+", "-", " ", "\\", ""):
            if line.startswith("+"):
                cur.added.append(line[1:]); new_left -= 1
            elif line.startswith("-"):
                cur.removed.append(line[1:]); old_left -= 1
            elif not line.startswith("\\"):
                old_left -= 1; new_left -= 1
            continue
        old_left = new_left = 0
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            cur = FileDiff(path=m.group(2) if m else line)
            files.append(cur)
        elif line.startswith("--- "):
            if cur is None or (cur.added or cur.removed):                # a diff without 'diff --git' lines
                cur = FileDiff(path="")
                files.append(cur)
            if line.strip() == "--- /dev/null":
                cur.creates = True
        elif line.startswith("+++ "):
            if cur is None:
                cur = FileDiff(path=""); files.append(cur)
            if line.strip() == "+++ /dev/null":
                cur.deletes = True
            elif line.startswith("+++ b/"):
                cur.path = line[6:].strip()
            else:
                cur.path = line[4:].strip()
        elif line.startswith("new file mode"):
            if cur: cur.creates = True
        elif line.startswith("deleted file mode"):
            if cur: cur.deletes = True
        elif line.startswith(("rename from", "rename to")):
            if cur: cur.renames = True
        elif (m := HUNK.match(line)) and cur is not None:
            old_left, new_left = int(m[2] if m[2] is not None else 1), int(m[4] if m[4] is not None else 1)
    return files


def is_class_list(s: str) -> bool:
    """A string made only of utility-class-shaped tokens is styling, not copy."""
    toks = s.split()
    if not toks or any(not TOKEN.match(t) for t in toks):
        return False
    return all(t in BARE_UTILITIES or re.search(r"[-:\[/0-9]", t) for t in toks)


def visible_text(line: str, markup: bool) -> set[str]:
    """Strings in the line that read as user-visible copy (class lists and styling contexts excluded)."""
    for rx in CLASS_CONTEXTS:
        line = rx.sub(" ", line)
    words = {g.strip() for m in TEXT.finditer(line) for g in m.groups() if g and g.strip() and not is_class_list(g.strip())}
    s = line.strip()
    if markup and s and not re.search(r"[<>{}=;()]", s) and re.search(r"[A-Za-z]{2}", s) and not is_class_list(s):
        words.add(s)                                           # a bare line of JSX/HTML text
    return words


def lint(diff: str, allowed_files: set[str], max_changed: int = 24) -> list[str]:
    errs: list[str] = []
    files = parse_diff(diff)
    if not files or not any(f.added or f.removed or f.creates or f.deletes or f.renames for f in files):
        return ["empty diff"]
    changed = 0
    removed_txt: set[str] = set()
    added_txt: set[str] = set()
    for f in files:
        if f.creates:
            errs.append(f"creates a file: {f.path}")
        if f.deletes:
            errs.append(f"deletes a file: {f.path}")
        if f.renames:
            errs.append(f"renames a file: {f.path}")
        if f.path not in allowed_files and not (f.creates or f.deletes):
            errs.append(f"touches a file outside the localized set: {f.path}")
        markup = any(f.path.endswith(ext) for ext in MARKUP)
        changed += len(f.added) + len(f.removed)
        for body in f.added:
            errs += [f"{why}: {body.strip()[:80]}" for rx, why in FORBIDDEN_RE if rx.search(body)]
        if markup:
            for body in f.removed:
                removed_txt |= visible_text(body, True)
            for body in f.added:
                added_txt |= visible_text(body, True)
            gone = sum(len(TAG.findall(b)) for b in f.removed) - sum(len(TAG.findall(b)) for b in f.added)
            if gone > 0:
                errs.append(f"removes {gone} element(s) from {f.path}")
    if changed > max_changed:
        errs.append(f"diff too large: {changed} changed lines (limit {max_changed})")
    if removed_txt - added_txt:
        errs.append("changes visible text: " + ", ".join(sorted(removed_txt - added_txt))[:100])
    seen, out = set(), []
    for e in errs:
        if e not in seen:
            seen.add(e); out.append(e)
    return out
