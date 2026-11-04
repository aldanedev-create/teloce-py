"""The regex lexer must be indistinguishable from the legacy lexer."""
import random
import re
from pathlib import Path

import pytest

from teloce.javascript.parser import (
    JavaScriptLexer,
    JavaScriptSyntaxError,
    LegacyJavaScriptLexer,
    find_balanced_end,
)

ROOT = Path(__file__).resolve().parents[2]


def _lex(cls, source):
    try:
        return ("ok", cls(source).tokenize())
    except JavaScriptSyntaxError as exc:
        return ("err", str(exc), exc.token)


def _assert_same(source):
    assert _lex(JavaScriptLexer, source) == _lex(LegacyJavaScriptLexer, source), repr(source)


def _corpus():
    files = [p for p in ROOT.rglob("*") if p.suffix in {".vel", ".js", ".mjs", ".ts"}
             and "node_modules" not in p.parts and ".git" not in p.parts
             and p.stat().st_size < 400_000]
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        yield text
        for m in re.finditer(r"<script[^>]*>([\s\S]*?)</script>", text):
            yield m.group(1)


def test_repo_corpus_matches():
    count = 0
    for text in _corpus():
        _assert_same(text)
        count += 1
    assert count > 10


_PIECES = [
    "a", "foo", "_x", "$y", "return", "typeof", "in", "of", "x1", "é", "日本", "𝒳",
    "0", "12", "3.14", ".5", "1e+5", "0x1F", "0b101", "1_000", "10n", "1..toString", "²",
    "+", "-", "*", "/", "%", "=", "==", "===", "!==", "!=", "<", ">", "<=", ">=", ">>", ">>>", ">>>=",
    "&&", "||", "??", "?.", "?", ":", ";", ",", ".", "...", "=>", "++", "--", "**", "**=", "/=", "+=",
    "(", ")", "[", "]", "{", "}",
    "'s'", '"d"', "`t`", "'a\\'b'", '"a\\"b"', "`a${b}c`", "'unterminated", '"x\\', "`open",
    "// line comment", "/* block */", "/* open", "/re/g", "/[/]/", "/a\\/b/i", "/(x/", "/", "//",
    "\n", "\r\n", "\t", " ", "  ", "\u00a0", "\u2028", "#!shebang", "#", "@", "\\", "~", "^", "&", "|",
]


def test_fuzz_matches():
    rng = random.Random(1234)
    for _ in range(40000):
        source = "".join(rng.choice(_PIECES) + rng.choice(["", " ", "\n"]) for _ in range(rng.randint(1, 12)))
        _assert_same(source)


def test_fuzz_random_characters():
    rng = random.Random(99)
    pool = list("abcXYZ019_$ \n\r\t'\"`/\\*+-=<>!?&|.,;:(){}[]#@~^%é日") + ["\u00a0", "²"]
    for _ in range(20000):
        source = "".join(rng.choice(pool) for _ in range(rng.randint(1, 40)))
        _assert_same(source)


def _legacy_balanced(source, opening, open_char, close_char):
    depth = 0
    for token in LegacyJavaScriptLexer(source[opening:]).tokenize():
        if token.value == open_char:
            depth += 1
        elif token.value == close_char:
            depth -= 1
            if depth == 0:
                return opening + token.end
    return None


def test_balanced_pair_matches_legacy_when_legacy_succeeds():
    rng = random.Random(7)
    for _ in range(15000):
        source = "".join(rng.choice(_PIECES) + rng.choice(["", " ", "\n"]) for _ in range(rng.randint(1, 14)))
        for open_char, close_char in (("{", "}"), ("(", ")"), ("[", "]")):
            for opening in [i for i, c in enumerate(source) if c == open_char][:3]:
                try:
                    expected = _legacy_balanced(source, opening, open_char, close_char)
                except JavaScriptSyntaxError:
                    continue  # legacy rejects the whole remainder; early stop may be more lenient
                assert find_balanced_end(source, opening, open_char, close_char) == expected, (source, opening)
