"""Optimised compiler helpers must match the original implementations exactly."""
import random
import re

from teloce.compiler.compiler import _ATTR_MARKER, _TEXT_MARKER, _MarkerIndex
from teloce.compiler.optimizer import Optimizer


def reference_dependencies(expression):
    cls = Optimizer
    """Return conservative root dependencies for a template expression.

    This is intentionally conservative: a false positive causes one extra
    binding to update, while a false negative could leave stale DOM. The
    JavaScript parser validates the authored script; this pass only builds
    a safe dependency index for template expressions.
    """
    raw_source = str(expression or "")
    source = raw_source
    # Identifiers inside string literals are values, not state reads. Keep
    # the character positions stable so diagnostics still use the same
    # source offsets when this analysis is extended.
    source = re.sub(
        r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"",
        lambda match: " " * len(match.group(0)),
        source,
    )
    names: list[str] = []
    # The normal identifier expression intentionally ignores member names
    # after a dot. Handle the component state form separately so
    # `this.firstName` contributes the root `firstName` dependency.
    for pattern, search_source in (
        (r"\bthis\.([A-Za-z_$][\w$]*)", source),
        (r"\bthis\?\.([A-Za-z_$][\w$]*)", source),
        (r"\bthis\s*\[\s*['\"]([A-Za-z_$][\w$]*)['\"]\s*\]", raw_source),
    ):
        for match in re.finditer(pattern, search_source):
            name = match.group(1)
            if name not in names:
                names.append(name)
    for match in cls._IDENTIFIER_RE.finditer(source):
        name = match.group(1)
        if name in cls._NON_STATE_NAMES or name in names:
            continue
        before = source[:match.start()].rstrip()
        if before.endswith("?"):
            continue
        if before.endswith("."):
            # `this.user.name` is a state read rooted at `user`; ordinary
            # member names such as `name` are not separate dependencies.
            if before[:-1].rstrip().endswith("this"):
                names.append(name)
            continue
        # Object-literal keys and arrow parameters are not state reads.
        after = source[match.end():].lstrip()
        if after.startswith(":") and not before.endswith("?"):
            continue
        if before.endswith("=>"):
            continue
        names.append(name)
    return names


_PIECES = [
    "a", "item", "this", "this.", "this?.", "this.user.name", "this ['k']", "this[\"q\"]", ".", "?.", "?", ":", "=>", "(", ")",
    "x", "y2", "$z", "_w", "true", "null", "Math", "event", "$event", "{", "}", "[", "]", ",", "+", " ", "  ", "\n", "\t",
    "'str a'", '"str b"', "'it\\'s'", "'unterminated", '"x', "a ? b : c", "k: v", "(p) => p", "p => p.q", "a.b.c", "fn(x)", "a | f",
    "count", "items.length", "!flag", "a&&b", "x?.y", "x ?. y", "é", "日本", "1.5", "0x1F",
]


def test_dependencies_match_reference():
    rng = random.Random(11)
    for _ in range(40000):
        expression = "".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 14)))
        assert Optimizer._dependencies(expression) == reference_dependencies(expression), expression


def test_dependencies_returns_independent_lists():
    first = Optimizer._dependencies("a + b")
    first.append("*")
    assert Optimizer._dependencies("a + b") == ["a", "b"]


def _reference_find(code, prefix, identifier):
    return code.find(prefix + identifier)


def test_marker_index_matches_find():
    rng = random.Random(21)
    ids = ["t0", "t1", "t10", "t11", "b0", "b1", "b12", "b123", "a-b", "x.y", "x:y", "", "None", "é", "t 1", "t\"1"]
    for prefix in (_TEXT_MARKER, _ATTR_MARKER):
        for _ in range(4000):
            parts = []
            for _ in range(rng.randint(0, 12)):
                parts.append(rng.choice([prefix + rng.choice(ids), prefix, "x", "\n", " ", prefix[:5], prefix[-4:], rng.choice(ids)]))
            code = "".join(parts)
            index = _MarkerIndex(code, prefix)
            for identifier in ids:
                assert index.find(identifier) == _reference_find(code, prefix, identifier), (code, identifier)
