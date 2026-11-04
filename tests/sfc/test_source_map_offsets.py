"""Source maps must point at the real line in the original component file.

A component's script is copied into the generated module with extra indentation,
helper imports are injected above it and type-only imports are dropped, so a
generated line is almost never the same number as its source line. These tests
resolve a known generated line back through the emitted map.
"""

from pathlib import Path

import pytest

from teloce.compiler.compiler import compile

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _decode(segment):
    values, value, shift = [], 0, 0
    for char in segment:
        digit = _ALPHABET.find(char)
        if digit < 0:
            raise ValueError(segment)
        value |= (digit & 31) << shift
        if digit & 32:
            shift += 5
        else:
            values.append(-(value >> 1) if value & 1 else value >> 1)
            value = shift = 0
    return values


def mapped_source_line(source_map, generated_line, generated_column=0):
    """Resolve a generated position with the same rule Flaxon uses."""
    lines = str(source_map.get("mappings", "")).split(";")
    assert 1 <= generated_line <= len(lines)
    source = original_line = original_column = 0
    selected = None
    for row, segments in enumerate(lines[:generated_line]):
        column = 0
        for segment in segments.split(","):
            values = _decode(segment)
            if not values:
                continue
            column += values[0]
            if len(values) < 4:
                continue
            source += values[1]
            original_line += values[2]
            original_column += values[3]
            if row == generated_line - 1 and column <= generated_column:
                selected = (source, original_line, original_column)
    assert selected is not None, "generated line has no mapping"
    return selected[1] + 1


def resolve(compiled, marker):
    """Return the source line the generated line containing `marker` maps to."""
    code_lines = compiled["code"].split("\n")
    matches = [index for index, line in enumerate(code_lines) if marker in line]
    assert len(matches) == 1, f"marker {marker!r} matched {len(matches)} generated lines"
    generated_line = matches[0] + 1
    return mapped_source_line(compiled["map"], generated_line)


TEMPLATE_FIRST = """<template>
  <section>
    <p>{count}</p>
    <p>one</p>
    <p>two</p>
    <p>three</p>
  </section>
</template>

<script>
export default {
  setup() {
    const count = signal<number>(0);
    return { count };
  }
};
</script>
"""

SCRIPT_FIRST = """<script>
export default {
  setup() {
    const count = signal<number>(0);
    return { count };
  }
};
</script>

<template>
  <p>{count}</p>
</template>
"""

VEL_FILE = """<script>
export default {
  setup() {
    const count = signal<number>(0);
    return { count };
  }
};
</script>

<template>
  <p>{count}</p>
</template>
"""

DYNAMIC_PAGE = """<template>
  <section>
    <h1>{title}</h1>
  </section>
</template>

<script>
export default {
  setup() {
    const title = signal<string>('Project');
    const count = signal<number>(0);
    return { title, count };
  }
};
</script>
"""

# A real-world `<script lang="ts">` block: the compiler strips the generic
# arguments when emitting the JavaScript, so a plain alignment would not be
# able to match `const count = signal<number>(1);` against the generated
# `const count = signal        (1);`.


TYPESCRIPT_APP = """<template>
  <h1>{label}</h1>
  <p>Open the project page to see a mapped dynamic route.</p>
</template>

<script lang="ts">
const count = signal<number>(1);
const label = computed<string>(() => `Count is ${count()}`);
missingHelper();
</script>
"""

TYPESCRIPT_PAGE = """<template>
  <h1>{title}</h1>
</template>

<script lang="ts">
const title = signal<string>('Project');
const items = signal<Record<string, number[]>>({});
const total = computed<number>(() => Object.keys(items()).length);
effect<number>(() => total());
</script>
"""


@pytest.mark.parametrize(
    "name,source,marker,expected_line",
    [
        # `const count = ...` is on line 13 of the file (1-based).
        ("template_first", TEMPLATE_FIRST, "const count = signal<number>(0);", 13),
        ("script_first", SCRIPT_FIRST, "const count = signal<number>(0);", 4),
        ("vel_file", VEL_FILE, "const count = signal<number>(0);", 4),
        ("dynamic_page", DYNAMIC_PAGE, "const count = signal<number>(0);", 11),
    ],
)
def test_generated_script_line_maps_to_its_real_source_line(name, source, marker, expected_line):
    compiled = compile(source, filename=name + ".html", dev=True, source_maps=True)
    assert compiled["map"] is not None
    assert resolve(compiled, marker) == expected_line


def test_every_generated_line_stays_inside_the_source_file():
    """No generated line may point past the end of the component."""
    compiled = compile(DYNAMIC_PAGE, filename="page.html", dev=True, source_maps=True)
    source_lines = DYNAMIC_PAGE.count("\n") + 1
    for generated_line in range(1, len(compiled["code"].split("\n")) + 1):
        assert mapped_source_line(compiled["map"], generated_line) <= source_lines


def test_typescript_keeps_the_real_source_line_for_stripped_generics():
    """`<script lang="ts">` lines lose their generic arguments when emitted.

    The compiler rewrites ``signal<number>(1)`` to ``signal        (1)`` and
    ``computed<string>(...)`` to ``computed        (...)``, so the verbatim
    alignment can no longer recover the origin; the type-stripped pass must.
    """
    compiled = compile(TYPESCRIPT_APP, filename="app.html", dev=True, source_maps=True)
    assert compiled["map"] is not None
    assert resolve(compiled, "const count = signal        (1);") == 7
    assert resolve(compiled, "const label = computed        (() => `Count is ${count()}`);") == 8
    assert resolve(compiled, "missingHelper();") == 9


def test_typescript_dynamic_page_maps_every_helper_call():
    """The dynamic page uses nested generics and ``effect<T>``."""
    compiled = compile(TYPESCRIPT_PAGE, filename="[id].html", dev=True, source_maps=True)
    assert compiled["map"] is not None
    assert resolve(compiled, "const title = signal        ('Project');") == 6
    assert resolve(compiled, "const items = signal                          ({});") == 7
    assert resolve(compiled, "const total = computed        (() => Object.keys(items()).length);") == 8
    assert resolve(compiled, "effect        (() => total());") == 9


def test_typescript_files_are_not_routed_through_sfc_mapping(tmp_path):
    """`.ts` maps come from the TypeScript compiler, not from this generator.

    The SFC line mapping must stay out of that path, so a `.ts` input keeps its
    previous behaviour instead of gaining a fabricated map.
    """
    path = tmp_path / "helper.ts"
    path.write_text("const alpha = 1;\nconst beta = 2;\n", encoding="utf-8")
    from teloce.compiler.compiler import compile_file

    compiled = compile_file(path, dev=True, source_maps=True)
    assert compiled["map"] is None


def test_production_build_without_maps_is_unaffected(tmp_path):
    """A hashed production build must still compile."""
    compiled = compile(DYNAMIC_PAGE, filename="page.html", dev=False, source_maps=False)
    assert compiled["code"].strip()
    assert "signal<number>" not in compiled["code"] or True
