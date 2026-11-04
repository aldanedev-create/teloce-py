"""Optimised helpers must behave exactly like their original implementations."""
import random

from teloce.compiler.source_map import _strip_inline_generics
from teloce.javascript import tree_sitter_backend as ts
from teloce.sfc.script import ScriptParser


# ---- reference (original) implementations ---------------------------------
def _ref_find_property(source, name):
    quote = None
    escaped = False
    line_comment = block_comment = False
    index = 0
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n": line_comment = False
        elif block_comment:
            if char == "*" and nxt == "/": block_comment = False; index += 1
        elif quote:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == quote: quote = None
        elif char in "'\"`": quote = char
        elif char == "/" and nxt == "/": line_comment = True; index += 1
        elif char == "/" and nxt == "*": block_comment = True; index += 1
        elif source.startswith(name, index):
            before = source[index - 1] if index else ""
            after_index = index + len(name)
            if (not (before.isalnum() or before in "_$") and
                    (after_index == len(source) or not (source[after_index].isalnum() or source[after_index] in "_$"))):
                cursor = after_index
                while cursor < len(source) and source[cursor].isspace(): cursor += 1
                if cursor < len(source) and source[cursor] == ":":
                    return cursor + 1
        index += 1
    return None


def _ref_strip(line):
    result, i, length = [], 0, len(line)
    ident = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$")
    while i < length:
        ch = line[i]
        if ch != "<" or i == 0 or line[i - 1] not in ident:
            result.append(ch); i += 1; continue
        depth, j, closed = 1, i + 1, False
        while j < length:
            cur = line[j]
            if cur == "<": depth += 1
            elif cur == ">":
                depth -= 1
                if depth == 0: closed = True; j += 1; break
            j += 1
        if closed:
            result.append(" " * (j - i)); i = j
        else:
            result.append(line[i]); i += 1
    return "".join(result)


def _ref_byte_to_char(source, byte_offset):
    encoded = source.encode("utf-8")
    return len(encoded[:byte_offset].decode("utf-8", errors="ignore"))


def _ref_point(source, point):
    row, byte_column = point
    lines = source.splitlines(keepends=True)
    line = lines[row] if 0 <= row < len(lines) else ""
    column = len(line.encode("utf-8")[:byte_column].decode("utf-8", errors="ignore"))
    return row + 1, column + 1


_PIECES = ["computed", "methods", "watch", ":", " : ", "{", "}", "x", "_computed", "computed2", "$computed",
           "'", '"', "`", "\\", "// c\n", "/* b */", "/*", "\n", " ", "a<b>", "foo<T>(x)", "<div>", "x < y", "map<K, V<W>>",
           "é", "日本", "😀", "\r\n", "\r", "\u2028", "\x0b", "\x0c", "\x85"]


def _fuzz_sources(seed, count):
    rng = random.Random(seed)
    for _ in range(count):
        yield "".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 25)))


def test_find_property_matches_reference():
    for source in _fuzz_sources(1, 30000):
        for name in ("computed", "methods", "watch"):
            assert ScriptParser._find_property(source, name) == _ref_find_property(source, name), (source, name)


def test_strip_inline_generics_matches_reference():
    for source in _fuzz_sources(2, 20000):
        assert _strip_inline_generics(source) == _ref_strip(source), source


def test_offset_conversion_matches_reference():
    rng = random.Random(3)
    for source in _fuzz_sources(4, 4000):
        encoded_len = len(source.encode("utf-8"))
        lines = source.count("\n") + 1
        for _ in range(6):
            off = rng.randint(0, encoded_len + 2)
            assert ts._byte_to_char(source, off) == _ref_byte_to_char(source, off), (source, off)
            point = (rng.randint(0, lines + 1), rng.randint(0, 12))
            assert ts._point_to_line_column(source, point) == _ref_point(source, point), (source, point)


def test_shallow_program_matches_full_program_top_level():
    import re
    from pathlib import Path

    from teloce.javascript.parser import JavaScriptSyntaxError, parse_javascript, parse_javascript_top_level

    root = Path(__file__).resolve().parents[2]
    checked = 0
    for path in root.rglob("*.vel"):
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"<script[^>]*>([\s\S]*?)</script>", text):
            code = m.group(1)
            try:
                full = parse_javascript(code)
            except (JavaScriptSyntaxError, ValueError) as exc:
                try:
                    parse_javascript_top_level(code)
                except (JavaScriptSyntaxError, ValueError) as exc2:
                    assert str(exc) == str(exc2)
                    continue
                raise AssertionError("shallow parse accepted invalid source")
            shallow = parse_javascript_top_level(code)
            assert len(full.body) == len(shallow.body)
            for a, b in zip(full.body, shallow.body):
                assert (a.kind, a.source, a.start, a.end, a.line, a.column, a.name) == \
                       (b.kind, b.source, b.start, b.end, b.line, b.column, b.name)
            checked += 1
    assert checked > 5
