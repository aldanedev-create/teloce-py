"""
Source map generator.

Generates source maps to map generated JavaScript back to the original source.
"""

from difflib import SequenceMatcher
from typing import List, Optional, Dict, Any
import json


def script_line_hints(generated_code: str, source_content: Optional[str]) -> Dict[int, tuple]:
    """Map each generated line to the source line it was copied from.

    A component's script is emitted with extra indentation, helper imports are
    injected above it and type-only imports are dropped, so generated line ``n``
    is almost never source line ``n``. Aligning the two texts (ignoring
    indentation) recovers the true origin of every line that is copied verbatim:

    * lines the compiler injected (``insert``) belong to the source line they
      were injected next to, which is what a developer expects from a helper
      import or a generated wrapper;
    * lines the compiler rewrote (``replace``, e.g. an annotated declaration
      that lost its type) keep the position of the block they replace;
    * source lines the compiler removed (``delete``, e.g. type-only imports)
      simply have no generated line.

    The result is a ``{generated_line: (source_line, column)}`` map with
    0-based indices, ready for :meth:`SourceMapGenerator.generate`.
    """
    if not source_content or not generated_code:
        return {}
    source_lines = [line.strip() for line in source_content.split("\n")]
    generated_lines = [line.strip() for line in generated_code.split("\n")]
    matcher = SequenceMatcher(None, source_lines, generated_lines, autojunk=False)
    hints: Dict[int, tuple] = {}
    candidates: List[int] = []
    last_source = 0
    for tag, first_source, last_source_end, first_generated, last_generated in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(last_source_end - first_source):
                hints[first_generated + offset] = (first_source + offset, 0)
            last_source = last_source_end - 1
        elif tag == "insert":
            for index in range(first_generated, last_generated):
                hints[index] = (last_source, 0)
                candidates.append(index)
        elif tag == "replace":
            for offset in range(last_generated - first_generated):
                source_index = min(first_source + offset, max(first_source, last_source_end - 1))
                hints[first_generated + offset] = (source_index, 0)
                candidates.append(first_generated + offset)
            last_source = max(first_source, last_source_end - 1)
    # The alignment above covers lines that are identical or that the compiler
    # left intact; the script body, however, may be emitted more than once
    # (module level and again inside the generated ``methods`` block) and
    # ``<script setup lang="ts">`` lines lose their generic arguments when
    # emitted to JavaScript. Two more passes rescue those lines: first by
    # matching their full stripped text against a unique source line, then by
    # matching the *type-stripped* form so ``signal<number>(0)`` in the source
    # still resolves to ``signal (0)`` in the generated code.
    unique, ambiguous = _build_unique_map(source_lines)
    stripped_source = [_strip_inline_generics(line) for line in source_lines]
    unique_stripped, ambiguous_stripped = _build_unique_map(stripped_source)
    for index in candidates:
        text = generated_lines[index]
        if not text:
            continue
        if text not in ambiguous and text in unique:
            hints[index] = (unique[text], 0)
            continue
        stripped = _strip_inline_generics(text)
        if (
            stripped
            and stripped not in ambiguous_stripped
            and stripped in unique_stripped
        ):
            hints[index] = (unique_stripped[stripped], 0)
    return hints


def _build_unique_map(lines: List[str]) -> tuple[Dict[str, int], set]:
    unique: Dict[str, int] = {}
    ambiguous: set = set()
    for index, text in enumerate(lines):
        if not text:
            continue
        if text in unique or text in ambiguous:
            ambiguous.add(text)
            unique.pop(text, None)
        else:
            unique[text] = index
    return unique, ambiguous


def _strip_inline_generics(line: str) -> str:
    """Return ``line`` with every balanced ``<...>`` annotation collapsed to blanks.

    ``<script setup lang="ts">`` declarations like ``signal<number>(1)`` and
    ``computed<Map<string, Task[]>>(items)`` are emitted to JavaScript without
    the angle-bracket annotation, but the compiler keeps the same column
    count, so the generated line has the same number of characters as the
    source. Replacing the annotation with a run of blanks of the same length
    lets the SequenceMatcher and the unique-line passes recover the origin.
    The opening ``<`` must sit directly after an identifier character so the
    function does not mistake HTML / JSX tags (``<template>``, ``<h1>``) for
    type arguments. Unbalanced ``<`` or ``>`` are preserved verbatim.
    """
    result: List[str] = []
    i = 0
    length = len(line)
    identifier_after = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$")
    while i < length:
        ch = line[i]
        if ch != "<" or i == 0 or line[i - 1] not in identifier_after:
            result.append(ch)
            i += 1
            continue
        depth = 1
        j = i + 1
        closed = False
        while j < length:
            current = line[j]
            if current == "<":
                depth += 1
            elif current == ">":
                depth -= 1
                if depth == 0:
                    closed = True
                    j += 1
                    break
            j += 1
        if closed:
            result.append(" " * (j - i))
            i = j
        else:
            result.append(line[i])
            i += 1
    return "".join(result)


class SourceMapGenerator:
    """
    Generates source maps for compiled JavaScript.
    """
    
    def __init__(self):
        self.mappings: List[str] = []
        self.sources: List[str] = []
        self.sources_content: List[str] = []
        self.names: List[str] = []
    
    def generate(
        self,
        generated_code: str,
        source_filename: str,
        source_content: Optional[str] = None,
        line_hints: Optional[Dict[int, tuple[int, int]]] = None,
    ) -> Dict[str, Any]:
        """Generate a valid line-level source map.

        The compiler does not currently retain token-to-token mappings, but a
        line-level map is still useful and is materially better than empty
        mappings: every generated line points to the corresponding source
        line (clamped at the final source line).
        """
        lines = generated_code.split('\n')
        source_lines = max(1, (source_content or '').count('\n') + 1)
        mappings = []
        previous_source_line = 0
        previous_source_column = 0
        line_hints = line_hints or {}
        for generated_line in range(len(lines)):
            original_line, original_column = line_hints.get(
                generated_line,
                (min(generated_line, source_lines - 1), 0),
            )
            original_line = max(0, min(int(original_line), source_lines - 1))
            original_column = max(0, int(original_column or 0))
            original_delta = original_line - previous_source_line
            column_delta = original_column - previous_source_column
            previous_source_line = original_line
            previous_source_column = original_column
            mappings.append(self._vlq_segment(original_delta, column_delta))
        return {
            "version": 3,
            "file": source_filename.replace('.vel', '.js'),
            "sources": [source_filename],
            "sourcesContent": [source_content],
            "names": [],
            "mappings": ';'.join(mappings)
        }

    @staticmethod
    def _vlq_segment(original_line_delta: int, original_column_delta: int = 0) -> str:
        """Encode a segment at generated column zero.

        The previous implementation emitted only a line-level approximation.
        Keeping the segment writer explicit makes it possible for compiler
        passes to provide an exact original column for known dynamic bindings
        while retaining a valid mapping for generated helper lines.
        """
        values = [0, 0, original_line_delta, original_column_delta]
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        encoded = []
        for value in values:
            signed = ((-value) << 1 | 1) if value < 0 else (value << 1)
            while True:
                digit = signed & 31
                signed >>= 5
                if signed:
                    digit |= 32
                encoded.append(alphabet[digit])
                if not signed:
                    break
        return ''.join(encoded)
    
    def to_json(self) -> str:
        """Convert the source map to JSON."""
        return json.dumps(self.to_dict(), indent=2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the source map to a dictionary."""
        return {
            "version": 3,
            "file": "output.js",
            "sources": self.sources,
            "sourcesContent": self.sources_content,
            "names": self.names,
            "mappings": ';'.join(self.mappings)
        }
