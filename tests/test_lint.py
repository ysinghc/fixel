"""The guardrail is the product's credibility (guide 14.1): legitimate fixes pass, every symptom-hiding trick is blocked."""
import pytest

from fixel.fix.lint import is_class_list, lint, parse_diff

FILE = "src/Card.jsx"


def diff(removed=(), added=(), path=FILE, before=("  <div>",), after=("  </div>",)):
    """A well-formed one-hunk unified diff replacing `removed` lines with `added` ones."""
    old = [*before, *removed, *after]
    new = [*before, *added, *after]
    body = [f" {l}" for l in before] + [f"-{l}" for l in removed] + [f"+{l}" for l in added] + [f" {l}" for l in after]
    return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -10,{len(old)} +10,{len(new)} @@\n" + "\n".join(body) + "\n")


def cls(old, new, path=FILE):
    return diff([f'  <div className="{old}">'], [f'  <div className="{new}">'], path)


# ----------------------------------------------------------------------------- must pass
PASSES = {
    "min-w-0 on a flex child": cls("flex items-center", "flex items-center min-w-0"),
    "flex-wrap": cls("flex gap-2", "flex flex-wrap gap-2"),
    "w-full max-w-md instead of a fixed width": cls("w-[480px]", "w-full max-w-md"),
    "break-words": cls("text-sm", "text-sm break-words"),
    "a breakpoint": cls("flex", "flex flex-col sm:flex-row"),
    "gap instead of a negative margin": cls("-mt-6", "mt-0 gap-2"),
    "min-width 0 in css": diff(["  .card { min-width: 480px; }"], ["  .card { min-width: 0; }"], "src/card.css"),
    "overflow-wrap anywhere": diff(["  .t { color: #333; }"], ["  .t { color: #333; overflow-wrap: anywhere; }"], "src/card.css"),
    "max-width 100%": diff(["  .p { width: 480px; }"], ["  .p { width: 480px; max-width: 100%; }"], "src/card.css"),
    "darker text for contrast": cls("text-gray-400", "text-gray-700"),
    "larger hit area": cls("p-0", "p-3 min-h-6 min-w-6"),
    "keeping the same text": diff(['  <p className="a">Free shipping</p>'], ['  <p className="a b-2">Free shipping</p>']),
    "css custom property line starting with --": diff(["  --gap: 4px;"], ["  --gap: 8px;"], "src/card.css"),
    "flex-wrap in a clsx call": diff(['  className={clsx("flex", open && "gap-2")}'], ['  className={clsx("flex flex-wrap", open && "gap-2")}']),
}


@pytest.mark.parametrize("name", PASSES)
def test_legitimate_fix_passes(name):
    assert lint(PASSES[name], {FILE, "src/card.css"}) == []


# ----------------------------------------------------------------------------- must be blocked
BLOCKED = {
    "overflow-hidden class": (cls("flex", "flex overflow-hidden"), "clip"),
    "overflow-x-hidden": (cls("flex", "flex overflow-x-hidden"), "clip"),
    "md:hidden": (cls("flex", "flex md:hidden"), "hides"),
    "hidden": (cls("flex", "hidden"), "hides"),
    "hidden attribute": (diff(["  <div>"], ["  <div hidden>"]), "hides"),
    "display none": (diff(["  .a { color: red; }"], ["  .a { display: none; }"], "src/card.css"), "hides the element"),
    "visibility hidden": (diff(["  .a {}"], ["  .a { visibility: hidden; }"], "src/card.css"), "hides the element"),
    "opacity 0": (diff(["  .a {}"], ["  .a { opacity: 0; }"], "src/card.css"), "hides the element"),
    "opacity-0 class": (cls("flex", "flex opacity-0"), "hides"),
    "css overflow hidden": (diff(["  .a {}"], ["  .a { overflow: hidden; }"], "src/card.css"), "clipping"),
    "overflow-x clip": (diff(["  .a {}"], ["  .a { overflow-x: clip; }"], "src/card.css"), "clipping"),
    "important": (diff(["  .a { width: 9px; }"], ["  .a { width: 9px !important; }"], "src/card.css"), "!important"),
    "truncate": (cls("flex", "flex truncate"), "truncating"),
    "text-overflow ellipsis": (diff(["  .a {}"], ["  .a { text-overflow: ellipsis; }"], "src/card.css"), "truncating"),
    "line-clamp": (cls("text-sm", "text-sm line-clamp-2"), "truncating"),
    "zero width": (diff(["  .a {}"], ["  .a { width: 0; }"], "src/card.css"), "collapses"),
    "zero max-height": (diff(["  .a {}"], ["  .a { max-height: 0px; }"], "src/card.css"), "collapses"),
    "w-0 class": (cls("flex", "flex w-0"), "collapses"),
    "scale-0": (cls("flex", "flex scale-0"), "collapses"),
    "font-size 0": (diff(["  .a {}"], ["  .a { font-size: 0; }"], "src/card.css"), "zero font size"),
    "transparent text": (diff(["  .a {}"], ["  .a { color: transparent; }"], "src/card.css"), "invisible"),
    "off-screen": (diff(["  .a {}"], ["  .a { position: absolute; left: -9999px; }"], "src/card.css"), "off screen"),
    "pointer-events none": (diff(["  .a {}"], ["  .a { pointer-events: none; }"], "src/card.css"), "hit test"),
    "pointer-events-none class": (cls("fixed", "fixed pointer-events-none"), "hit test"),
    "clip-path": (diff(["  .a {}"], ["  .a { clip-path: inset(0); }"], "src/card.css"), "clips"),
    "copy edit": (diff(['  <p className="a">Free shipping on orders</p>'], ['  <p className="a">Free shipping</p>']), "visible text"),
    "copy edit in a string": (diff(['  const label = "Browse catalog";'], ['  const label = "Browse";']), "visible text"),
    "bare text line removed": (diff(["    Free shipping on orders over fifty dollars"], ["    Free shipping"]), "visible text"),
    "element removed": (diff(["  <img src={logo} />", "  <p>x</p>"], ["  <p>x</p>"]), "removes"),
    "new file": ("diff --git a/src/new.css b/src/new.css\nnew file mode 100644\n--- /dev/null\n+++ b/src/new.css\n@@ -0,0 +1 @@\n+.a { }\n", "creates a file"),
    "deleted file": ("diff --git a/src/Card.jsx b/src/Card.jsx\ndeleted file mode 100644\n--- a/src/Card.jsx\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n", "deletes a file"),
    "rename": ("diff --git a/src/Card.jsx b/src/Other.jsx\nsimilarity index 90%\nrename from src/Card.jsx\nrename to src/Other.jsx\n", "renames"),
    "file outside the localized set": (cls("a", "b", "package.json"), "outside the localized set"),
    "too large": (diff([f"  .r{i} {{ gap: 1px; }}" for i in range(15)], [f"  .r{i} {{ gap: 2px; }}" for i in range(15)], "src/card.css"), "too large"),
    "empty": ("", "empty diff"),
}


@pytest.mark.parametrize("name", BLOCKED)
def test_symptom_hiding_patch_is_blocked(name):
    patch, expect = BLOCKED[name]
    errs = lint(patch, {FILE, "src/card.css"})
    assert errs and any(expect in e for e in errs), errs


def test_removing_a_hiding_class_is_not_flagged():
    # only ADDED lines are checked for hiding: deleting `hidden` or `overflow-hidden` is a fix, not a symptom-hide
    assert lint(cls("flex overflow-hidden", "flex"), {FILE}) == []


def test_each_blocked_reason_is_reported_once():
    errs = lint(cls("flex", "flex hidden"), {FILE})
    assert len(errs) == len(set(errs))


# ----------------------------------------------------------------------------- parsing
def test_parse_diff_honours_hunk_counts_for_lines_starting_with_dashes():
    d = diff(["  --gap: 4px;"], ["  --gap: 8px;"], "a.css")
    f = parse_diff(d)[0]
    assert f.path == "a.css" and f.removed == ["  --gap: 4px;"] and f.added == ["  --gap: 8px;"]


def test_parse_diff_handles_several_files_and_hunks():
    d = diff(["  a"], ["  b"], "x.css") + diff(["  c"], ["  d"], "y.css")
    assert [f.path for f in parse_diff(d)] == ["x.css", "y.css"]


@pytest.mark.parametrize("s,expected", [
    ("flex items-center", True), ("w-[480px] max-w-md", True), ("md:flex-row gap-2", True), ("flex", True),
    ("Free shipping", False), ("Pay now", False), ("hello world", False), ("ok", False),
])
def test_is_class_list(s, expected):
    assert is_class_list(s) is expected
