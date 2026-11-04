"""The batched template lexer must tokenize exactly like the original."""
import importlib.util
import random
import re
from pathlib import Path

from teloce.compiler.lexer import Lexer

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("reference_lexer", _HERE / "reference_lexer.py")
_ref = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ref)
ROOT = _HERE.parents[1]


def _dump(lexer_cls, source):
    lexer = lexer_cls(source)
    tokens = lexer.tokenize()
    return (
        [(t.type.name, t.value, t.line, t.column) for t in tokens],
        list(lexer.errors),
        (lexer.position, lexer.line, lexer.column),
    )


def _same(source):
    assert _dump(Lexer, source) == _dump(_ref.Lexer, source), repr(source)


def test_repo_templates_match():
    count = 0
    for path in ROOT.rglob("*.vel"):
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<template[^>]*>([\s\S]*)</template>", text)
        for source in ([m.group(1)] if m else []) + [text]:
            _same(source)
            count += 1
    assert count > 10


_PIECES = [
    "<div>", "</div>", "<p class=\"a b\">", "<p class='x'>", "<input v-model=\"x\">", "<br/>", "<br>", "<img src=a.png>",
    "<for each=\"i in items\">", "</for>", "<if cond=\"x\">", "</if>", "<else>", "</else>", "<!-- c -->", "<!-- open",
    "<!DOCTYPE html>", "<!doctype", "{{ a }}", "{{a|f}}", "{{ unterminated", "}}", "{", "}", "{{", "<", "<<", "</", "<a",
    "@click=\"go\"", "@keyup.enter=x", ":class=\"{a:b}\"", ":model=\"m\"", ":style=s", ":value=v", ":href=h", ":src=s",
    "v-on:click=\"f\"", "v-bind:title=\"t\"", "v-model.trim=\"z\"", "v-highlight.flash", "v-if=\"q\"", "use:focus", "use:drag.x:y",
    "transition:fade", "in:fly", "out:slide", "animate:flip", "data-id=7", "disabled", "x=\"y", "x='y", "a=b c=d",
    "text ", "hello world", "é日本😀", "\n", "\r\n", "\t", "  ", ">", "/>", "=", "\"", "'", "-", "_", ".", ":", "$",
]


def test_fuzz_templates_match():
    rng = random.Random(2026)
    for _ in range(25000):
        source = "".join(rng.choice(_PIECES) + rng.choice(["", " ", "\n", ""]) for _ in range(rng.randint(1, 14)))
        _same(source)


def test_fuzz_random_characters_match():
    rng = random.Random(5)
    pool = list("ab<>/{}=\"'!-: @$.\n\r\tv0é日") 
    for _ in range(20000):
        _same("".join(rng.choice(pool) for _ in range(rng.randint(1, 40))))
