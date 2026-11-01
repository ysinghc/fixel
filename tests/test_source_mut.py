import pytest

from fixel.bench.source_mut import SOURCE_OPS, add_classes, important, opening_tag_end, tailwind_major

SRC = '''export default function A() {
  return (
    <div className="flex gap-2" onClick={() => go(">")}>
      <span>hi</span>
      <img src="a.png" alt="a > b" />
      <p className={cn("a", x && "b")}>dyn</p>
      <ul>
        <li>x</li>
      </ul>
    </div>
  )
}
'''


def loc(line, text="<"):
    ln = SRC.split("\n")[line - 1]
    return f"src/A.jsx:{line}:{ln.index(text) + 1}"


def test_adds_to_a_static_className_on_the_same_line():
    new, why = add_classes(SRC, loc(3), "w-4!")
    assert why == "ok" and 'className="flex gap-2 w-4!"' in new
    assert new.count("\n") == SRC.count("\n"), "line numbers must not move"


def test_a_tag_without_className_gets_one_and_a_self_closing_tag_with_a_gt_in_a_string_is_found():
    new, _ = add_classes(SRC, loc(4), "hidden!")
    assert "<span className=\"hidden!\">hi" in new
    new, _ = add_classes(SRC, loc(5), "max-w-none!")
    assert '<img className="max-w-none!" src="a.png" alt="a > b" />' in new


def test_dynamic_className_and_bad_locations_are_refused_not_guessed():
    assert add_classes(SRC, loc(6), "x")[0] is None and "dynamic" in add_classes(SRC, loc(6), "x")[1]
    assert add_classes(SRC, "src/A.jsx:3:1", "x")[0] is None            # points at whitespace, not a tag
    assert add_classes(SRC, "src/A.jsx:99:1", "x")[0] is None
    assert add_classes(SRC, "nonsense", "x")[0] is None


def test_opening_tag_end_skips_arrow_functions_and_quoted_gt():
    start = SRC.index('<div')
    assert SRC[start:opening_tag_end(SRC, start)].endswith('go(">")}>')


def test_important_marker_follows_the_tailwind_major():
    assert important("w-4 -mt-6", 4) == "w-4! -mt-6!"
    assert important("w-4 -mt-6", 3) == "!w-4 !-mt-6"
    assert tailwind_major({"devDependencies": {"tailwindcss": "^4.1.0"}}) == 4
    assert tailwind_major({"dependencies": {"tailwindcss": "~3.4.7"}}) == 3 and tailwind_major({}) is None


@pytest.mark.parametrize("op", sorted(SOURCE_OPS))
def test_every_source_operator_is_a_known_detection_operator(op):
    from fixel.bench.mutations import BY_NAME
    assert op in BY_NAME and not BY_NAME[op].control
