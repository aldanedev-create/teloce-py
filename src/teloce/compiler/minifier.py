"""Small, dependency-free minifiers for compiler-owned output.

Teloce can optionally use esbuild for whole-application bundling.  A compiler
should still be able to produce a valid production artifact when npm tooling
is not installed, so this module provides a conservative fallback.  It only
removes comments and insignificant whitespace; it does not rename user
symbols or rewrite expressions.
"""

from __future__ import annotations

import re


_IDENTIFIER = re.compile(r"[A-Za-z0-9_$]")


def _can_start_regex(previous: str | None) -> bool:
    """Return whether a slash is likely to start a regular expression."""
    return previous is None or previous in "([{=,:;!&|?+-*%^~<>"


def minify_js(source: str) -> str:
    """Conservatively minify JavaScript without changing string contents.

    The scanner understands quoted strings, template literals, comments and
    regular expressions.  Template literals are deliberately kept intact;
    whitespace inside ``${...}`` is valid but parsing it here would make this
    fallback less safe than the original source.
    """
    text = str(source)
    output: list[str] = []
    index = 0
    previous_significant: str | None = None
    pending_space = False

    def append(value: str, significant: bool = True) -> None:
        nonlocal previous_significant, pending_space
        if pending_space and output and value and _needs_space(output[-1][-1], value[0]):
            output.append(" ")
        pending_space = False
        if value:
            output.append(value)
            if significant:
                previous_significant = value[-1]

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if char.isspace():
            pending_space = True
            index += 1
            continue

        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            pending_space = True
            continue

        if char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            pending_space = True
            continue

        # A slash can be either division or the beginning of a regular
        # expression. Preserve source whitespace before it when present; this
        # prevents ``a / /regex/`` and ``return /regex/`` from becoming an
        # ambiguous token sequence in the conservative fallback.
        if char == "/" and pending_space and output:
            output.append(" ")
            pending_space = False

        if char in "'\"`":
            quote = char
            end = index + 1
            while end < len(text):
                if text[end] == "\\":
                    end += 2
                    continue
                if text[end] == quote:
                    end += 1
                    break
                end += 1
            append(text[index:end])
            index = end
            continue

        if char == "/" and _can_start_regex(previous_significant):
            end = index + 1
            in_class = False
            while end < len(text):
                current = text[end]
                if current == "\\":
                    end += 2
                    continue
                if current == "[":
                    in_class = True
                elif current == "]":
                    in_class = False
                elif current == "/" and not in_class:
                    end += 1
                    while end < len(text) and text[end].isalpha():
                        end += 1
                    break
                end += 1
            append(text[index:end])
            index = end
            continue

        append(char)
        index += 1

    return "".join(output).strip()


def _needs_space(previous: str, current: str) -> bool:
    """Keep the separator required between tokens."""
    if _IDENTIFIER.fullmatch(previous) and _IDENTIFIER.fullmatch(current):
        return True
    # ``a + ++b`` and ``a - --b`` must not become ``a+++b``/``a---b``.
    if previous == current and previous in "+-":
        return True
    # Keep two adjacent slash tokens separated. This is relevant when the
    # scanner cannot prove whether the second slash starts a regexp literal.
    if previous == current == "/":
        return True
    return False


def minify_css(source: str) -> str:
    """Conservatively minify CSS while preserving quoted values."""
    text = str(source)
    output: list[str] = []
    index = 0
    quote = ""
    pending_space = False

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if quote:
            output.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                output.append(text[index])
            elif char == quote:
                quote = ""
            index += 1
            continue

        if char in "'\"":
            if pending_space and output and output[-1][-1].isalnum():
                output.append(" ")
            pending_space = False
            quote = char
            output.append(char)
            index += 1
            continue

        if char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            pending_space = True
            continue

        if char.isspace():
            pending_space = True
            index += 1
            continue

        if pending_space:
            previous = output[-1][-1] if output else ""
            # A separator is needed between selectors/values, but not around
            # CSS punctuation. Keep spaces in calc()/custom values intact by
            # only removing them next to structural punctuation.
            if output and previous not in "{}:;,>~" and char not in "{}:;,>~":
                output.append(" ")
        pending_space = False
        output.append(char)
        index += 1

    return "".join(output).strip()
