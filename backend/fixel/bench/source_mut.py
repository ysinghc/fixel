"""Source-level defect injection for the fix benchmark (guide section 9.4: verified-fix rate, revert-equivalence).

The detection benchmark injects in the page, which leaves nothing to repair. A fix case needs the defect in the source, so
the repair is a real edit: Tailwind classes are added to the className of the JSX element a `data-loc` names
(`file:line:col`, the position of its opening `<`). The target keeps its line numbers (the classes go on the same line), so
findings still localize to the same element.

Classes carry Tailwind's important marker so the injected defect wins over whatever the element already says: it is the
benchmark breaking the app on purpose, the same licence the page-level injector takes. The patch linter's ban on
`!important` applies to Fixel's own patches, and a fix that removes the injected class is what we want to see.
"""
import re

# operator name -> Tailwind utilities that cause it (operators of mutations.OPS that a class list can express)
SOURCE_OPS: dict[str, str] = {
    "fixed_width": "w-[480px] shrink-0",
    "no_wrap_row": "flex-nowrap",
    "img_unbounded": "max-w-none w-[900px]",
    "negative_margin": "-mt-6",
    "nudge": "relative left-10",
    "tiny_target": "w-4 h-4 p-0 min-w-0",
    "clamp_height": "h-5 overflow-hidden",
}


def important(classes: str, tailwind_major: int = 4) -> str:
    """Tailwind 4 puts the marker after the utility (`w-4!`), Tailwind 3 before it (`!w-4`)."""
    return " ".join(f"{c}!" if tailwind_major >= 4 else f"!{c}" for c in classes.split())


def tailwind_major(package_json: dict) -> int | None:
    deps = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})}
    v = deps.get("tailwindcss")
    m = re.search(r"(\d+)", v or "")
    return int(m[1]) if m else None


def _offset(text: str, line: int, col: int) -> int:
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        return -1
    return sum(len(l) + 1 for l in lines[:line - 1]) + col - 1


def opening_tag_end(text: str, start: int) -> int:
    """Index just past the `>` that closes the JSX opening tag at `start` (`{...}` and quoted strings are skipped), or -1."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "\"'`" and (depth > 0 or text[i - 1] in "= "):
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            return i + 1
        i += 1
    return -1


def add_classes(text: str, loc: str, classes: str) -> tuple[str | None, str]:
    """Add `classes` to the className of the element at `loc` (`file:line:col`). Returns (new text or None, reason).

    Only a static `className="..."` string is edited, or a tag with no className at all; a dynamic className is
    reported as unsupported rather than guessed at.
    """
    m = re.match(r"^.+:(\d+):(\d+)$", loc)
    if not m:
        return None, "bad data-loc"
    start = _offset(text, int(m[1]), int(m[2]))
    if start < 0 or start >= len(text) or text[start] != "<":
        return None, "data-loc does not point at a tag"
    end = opening_tag_end(text, start)
    if end < 0:
        return None, "could not find the end of the opening tag"
    tag = text[start:end]
    static = re.search(r'\bclassName="([^"]*)"', tag)
    if static and tag.count("className") == 1:
        a, b = start + static.start(1), start + static.end(1)
        have = text[a:b]
        return text[:a] + (have + " " if have.strip() else "") + classes + text[b:], "ok"
    if "className" in tag:
        return None, "className is dynamic"
    name = re.match(r"<[A-Za-z][\w.-]*", tag)
    if not name:
        return None, "not an intrinsic tag"
    at = start + name.end()
    return text[:at] + f' className="{classes}"' + text[at:], "ok"
