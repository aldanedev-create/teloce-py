"""Scope attribute must land on the rightmost compound selector (Vel semantics)."""

import pytest

from teloce.css.scoped import CSSScoper

SID = "data-v-test"


def scope(selector: str) -> str:
    out = CSSScoper().scope(f"{selector} {{ color: red; }}", SID)
    return out.split(" {")[0].strip()


@pytest.mark.parametrize("selector, expected", [
    (".a:hover", f".a[{SID}]:hover"),
    (".a .b:hover", f".a .b[{SID}]:hover"),
    (".a:hover .b", f".a:hover .b[{SID}]"),
    (".a:focus-within > .b", f".a:focus-within > .b[{SID}]"),
    (".a:not(.x) .b", f".a:not(.x) .b[{SID}]"),
    (".a:first-child .b", f".a:first-child .b[{SID}]"),
    (".a.on .b", f".a.on .b[{SID}]"),
    (".a::before", f".a[{SID}]::before"),
    (".a:hover::after", f".a[{SID}]:hover::after"),
    ("div > p:nth-child(2n+1)", f"div > p[{SID}]:nth-child(2n+1)"),
    ("a[href^='x:y'] .b", f"a[href^='x:y'] .b[{SID}]"),
    (".a ~ .b:not(.x)::before", f".a ~ .b[{SID}]:not(.x)::before"),
    (":is(.a, .b)", f"[{SID}]:is(.a, .b)"),
    (":is(.a) .b", f":is(.a) .b[{SID}]"),
])
def test_attribute_goes_on_last_compound(selector, expected):
    assert scope(selector) == expected


def test_selector_list_scopes_each_part_independently():
    assert scope(".a .b, .c:hover .d") == f".a .b[{SID}], .c:hover .d[{SID}]"
