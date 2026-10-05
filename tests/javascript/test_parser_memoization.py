"""Memoized tokenizer/parser must behave exactly like the uncached versions."""

import pytest

from teloce.javascript.parser import parse_javascript, tokenize_javascript


def test_tokenize_returns_equal_but_independent_lists():
    a = tokenize_javascript("const x = 1;")
    b = tokenize_javascript("const x = 1;")
    assert a == b and a is not b
    a.clear()                      # mutating one result must not poison the cache
    assert tokenize_javascript("const x = 1;") == b


def test_parse_is_stable_across_repeated_calls():
    src = "export default { data() { return { a: 1 }; } };"
    assert parse_javascript(src) == parse_javascript(src)


def test_language_and_backend_are_part_of_the_cache_key():
    src = "const x: number = 1;"
    ts = parse_javascript(src, language="ts")
    js_legacy = parse_javascript(src, backend="legacy")
    assert ts is not js_legacy


def test_syntax_errors_are_not_cached_as_success():
    for _ in range(3):
        with pytest.raises(Exception):
            parse_javascript("const = ;", backend="tree-sitter")


def test_invalid_backend_still_raises():
    with pytest.raises(ValueError):
        parse_javascript("1", backend="nope")
