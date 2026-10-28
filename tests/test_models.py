from fixel.models import StateSpec


def test_state_key_is_stable():
    s = StateSpec(route="/checkout", width=375)
    assert s.key == "/checkout|375|light|none|0"
