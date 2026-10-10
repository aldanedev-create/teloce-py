"""Standalone SSR contracts and server/client expression parity."""

import json
import subprocess
from pathlib import Path

import pytest

from teloce.server import (
    Renderer,
    compile_program,
    SSRCompileError,
    SSRRenderError,
    public_data,
)
from teloce.server.expressions import compile_expression, evaluate, string


def renderer(tmp_path, source):
    program = compile_program(source, "App.html")
    (tmp_path / "App.ssr.json").write_text(json.dumps(program))
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "ssr": {
                    "version": 1,
                    "entries": {"App.html": {"artifact": "App.ssr.json"}},
                }
            }
        )
    )
    return Renderer(tmp_path)


@pytest.mark.parametrize(
    "expression,scope",
    [
        ("items.length > 0 && open", {"items": [1], "open": True}),
        ("!items", {"items": []}),
        ("a === b", {"a": True, "b": 1}),
        ("a == b", {"a": "1", "b": 1}),
        ('a?.b ?? "missing"', {"a": None}),
        ("name.toUpperCase()", {"name": "Hello"}),
        ("a + b", {"a": 3, "b": "4"}),
        ("open ? a : b", {"open": False, "a": 1, "b": 2}),
        ("a && missing.value", {"a": False}),
        ("a / b", {"a": 3, "b": 0}),
        ("items[i]", {"items": [3, 4], "i": 1}),
        ('obj["name"]', {"obj": {"name": "Hello"}}),
        ('items.join("-")', {"items": [1, 2]}),
        ("items.includes(2)", {"items": [1, 2]}),
    ],
)
def test_expression_matches_javascript(expression, scope):
    js = (
        "const scope="
        + json.dumps(scope)
        + ";console.log(String((function(){with(scope){return ("
        + expression
        + ")}})()));"
    )
    expected = subprocess.check_output(["node", "-e", js], text=True).strip()
    assert string(evaluate(compile_expression(expression), scope)) == expected


def test_render_conditions_loops_and_escaped_attributes(tmp_path):
    render = renderer(
        tmp_path,
        '<template><section><a :href="url" :title="name">{{ name }}</a><ul v-if="items.length"><li v-for="(item, i) in items" :key="item.id">{{ i }}:{{ item.name }}</li></ul><p v-else>Empty</p></section></template>',
    )
    result = render.render(
        "App.html", {"url": "/ok", "name": "<bad>", "items": [{"id": 1, "name": "A"}]}
    )
    assert '<li data-teloce-key="1">0:A</li>' in result.html
    assert "&lt;bad&gt;" in result.html and "<bad>" not in result.html
    assert "\\u003c" in result.props_json
    assert (
        "<p>Empty</p>"
        in render.render("App.html", {"url": "/", "name": "A", "items": []}).html
    )


def test_render_rejects_unsafe_url_and_missing_public_value(tmp_path):
    render = renderer(tmp_path, '<template><a :href="url">{{ name }}</a></template>')
    with pytest.raises(SSRRenderError, match="Unsafe SSR URL"):
        render.render("App.html", {"url": "java\nscript:alert(1)", "name": "X"})
    with pytest.raises(SSRRenderError, match="Missing SSR public value"):
        render.render("App.html", {"url": "/"})


@pytest.mark.parametrize(
    "source",
    [
        "<p>{{ run() }}</p>",
        '<p v-html="html"></p>',
        '<component :is="name"/>',
        "<p>{{ value = 1 }}</p>",
    ],
)
def test_unsupported_syntax_has_diagnostics(source):
    with pytest.raises(SSRCompileError) as failure:
        compile_program("<template>" + source + "</template>", "Unsafe.html")
    assert failure.value.diagnostic["component"] == "Unsafe.html"
    assert failure.value.diagnostic["line"] >= 1


def test_plain_data_and_limits(tmp_path):
    with pytest.raises(ValueError, match="plain JSON"):
        public_data({"user": Path("/secret")})
    render = renderer(tmp_path, "<template><p>{{ message }}</p></template>")
    render.max_output = 10
    with pytest.raises(ValueError):
        render.render("App.html", {"message": "x" * 100})


@pytest.mark.parametrize(
    "expression,scope",
    [
        ("typeof missing", {}),
        ("n + 1", {"n": 9007199254740991}),
        ("a / b", {"a": 1, "b": 10000000}),
        ("name.length", {"name": "😀"}),
        ("items.includes()", {"items": []}),
        ("value === null", {"value": None}),
        ('a?.b?.c ?? "fallback"', {"a": None}),
    ],
)
def test_additional_javascript_parity(expression, scope):
    test_expression_matches_javascript(expression, scope)


def test_cache_is_bounded_and_public_data_specific(tmp_path):
    render = renderer(tmp_path, "<template><p>{{ name }}</p></template>")
    render.cache_size = 1
    a = render.render("App.html", {"name": "A"})
    assert render.render("App.html", {"name": "A"}) is a
    assert render.render("App.html", {"name": "B"}).html == "<p>B</p>"
    assert len(render._cache) == 1
    assert render.render("App.html", {"name": "A"}) is not a


def test_prerender_cli_exports_safe_state(tmp_path):
    from teloce.build import Builder
    from teloce.cli.main import main

    (tmp_path / "ui").mkdir()
    (tmp_path / "ui/App.html").write_text("<template><h1>{{ title }}</h1></template>")
    build = Builder({"ssr": True, "html_mode": True, "source_roots": ["ui"]}).build(
        tmp_path
    )
    assert not build["failed"]
    state = tmp_path / "public.json"
    state.write_text(json.dumps({"title": "</script><script>alert(1)</script>"}))
    assert (
        main(
            [
                "prerender",
                "ui/App.html",
                "--build-dir",
                str(tmp_path / "dist"),
                "--data",
                str(state),
            ]
        )
        == 0
    )
    output = (tmp_path / "dist/index.html").read_text()
    assert "\\u003c/script" in output and "<h1>&lt;/script" in output
    assert (
        main(
            [
                "prerender",
                "ui/App.html",
                "--build-dir",
                str(tmp_path / "dist"),
                "--output",
                "../escape.html",
            ]
        )
        == 1
    )


def test_selected_ssr_entries_include_children_but_skip_browser_only_pages(tmp_path):
    from teloce.build import Builder

    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "Card.html").write_text("<template><p>{{ title }}</p></template>")
    (ui / "App.html").write_text(
        '<template><Card :title="title"/></template><script>import Card from "./Card.html"; export default {components:{Card}}</script>'
    )
    (ui / "BrowserOnly.html").write_text('<template><p v-html="body"></p></template>')
    result = Builder(
        {
            "ssr": True,
            "ssr_entries": ["ui/App.html"],
            "html_mode": True,
            "source_roots": ["ui"],
        }
    ).build(tmp_path)
    assert not result["failed"], result["errors"]
    render = Renderer(tmp_path / "dist")
    assert (
        "ui/Card.html" in render.entries and "ui/BrowserOnly.html" not in render.entries
    )
    assert "<p>Hello</p>" in render.render("ui/App.html", {"title": "Hello"}).html


def test_diagnostic_uses_original_sfc_position():
    source = "<template>\n\n    <p>{{ run() }}</p>\n</template>"
    with pytest.raises(SSRCompileError) as failure:
        compile_program(source, "ui/Example.html")
    assert failure.value.diagnostic["line"] == 3
    assert failure.value.diagnostic["column"] >= 5
