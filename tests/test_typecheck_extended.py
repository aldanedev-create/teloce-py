"""JavaScript, imported contracts and runtime-supported dynamic/slot behavior."""

import pytest

from teloce.typecheck import check_project

pytest.importorskip("pytscheck")


def project(tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "Counter.html").write_text(
        '<script lang="ts">export default {props:{count:{type:Number,required:true}}};</script><template>{{ count }}</template>'
    )
    return ui


def test_javascript_jsdoc_script_template_and_positions(tmp_path):
    ui = project(tmp_path)
    source = """<script>
/** @type {{name: string}} */
const user = {name: 'Hello'};
export default { data() { return {user}; } };
</script><template>{{ user.name }}</template>"""
    (ui / "App.html").write_text(source)
    assert check_project([ui]).ok
    (ui / "App.html").write_text(source.replace("name: 'Hello'", "name: 1"))
    result = check_project([ui])
    assert not result.ok
    assert any(
        f.file == "App.html" and f.line == 3 and f.code == 2322 for f in result.findings
    )
    (ui / "App.html").write_text(source.replace("user.name", "user.missing"))
    assert not check_project([ui]).ok


@pytest.mark.parametrize(
    "import_text",
    [
        'import Counter from "./Counter.html";',
        'import { Counter } from "./barrel.ts";',
        'import { Counter as Renamed } from "./barrel.ts";',
        'import Counter from "@/Counter.html";',
    ],
)
def test_imported_child_contracts(tmp_path, import_text):
    ui = project(tmp_path)
    (ui / "barrel.ts").write_text(
        'export { default as Counter } from "./Counter.html.ts";'
    )
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"strict":true,"target":"ES2022","module":"esnext","moduleResolution":"bundler","paths":{"@/*":["./ui/*"]}}}'
    )
    name = "Renamed" if "Renamed" in import_text else "Counter"
    source = f'<script lang="ts">{import_text} export default {{components:{{{name}}}}};</script><template><{name} :count="1" /></template>'
    (ui / "App.html").write_text(source)
    assert check_project([ui], project_root=tmp_path).ok
    (ui / "App.html").write_text(source.replace(':count="1"', ":count=\"'bad'\""))
    assert not check_project([ui], project_root=tmp_path).ok


def test_dynamic_registered_name_checks_required_props(tmp_path):
    ui = project(tmp_path)
    source = """<script lang="ts">import Counter from './Counter.html'; export default {components:{Counter},data(){return {active:'Counter' as const};}};</script><template><component :is="active" :count="1" /></template>"""
    (ui / "App.html").write_text(source)
    assert check_project([ui]).ok
    (ui / "App.html").write_text(source.replace(':count="1"', ":count=\"'bad'\""))
    assert not check_project([ui]).ok
    (ui / "App.html").write_text(source.replace(':count="1"', ""))
    assert not check_project([ui]).ok
    (ui / "App.html").write_text(source.replace("active:'Counter'", "active:'Unknown'"))
    assert not check_project([ui]).ok


def test_slot_content_uses_parent_context_and_fallback_uses_child(tmp_path):
    ui = project(tmp_path)
    (ui / "Counter.html").write_text(
        '<script>export default {data(){return {fallback:"Default"};}};</script><template><slot name="header">{{ fallback }}</slot></template>'
    )
    source = """<script>import Counter from './Counter.html'; export default {components:{Counter},data(){return {title:'Hello'};}};</script><template><Counter><h1 slot="header">{{ title }}</h1></Counter></template>"""
    (ui / "App.html").write_text(source)
    assert check_project([ui]).ok
    (ui / "App.html").write_text(source.replace("{{ title }}", "{{ missing }}"))
    assert not check_project([ui]).ok


def test_repeated_property_error_maps_to_actual_occurrence(tmp_path):
    ui = project(tmp_path)
    source = '<script lang="ts">export default {data(){return {first:{name:1},second:{name:"ok"}};}};</script>\n<template>{{ first.name + second.name.toFixed() }}</template>'
    (ui / "App.html").write_text(source)
    result = check_project([ui])
    target = source.splitlines()[1].index("toFixed") + 1
    assert any(
        f.file == "App.html" and f.line == 2 and f.column == target
        for f in result.findings
    ), result.findings


def test_define_component_wrapper_context(tmp_path):
    ui = project(tmp_path)
    source = '<script lang="ts">function defineComponent<T>(value:T):T {return value;} export default defineComponent({data(){return {count:1};},methods:{save(){this.count=2;}}});</script><template>{{ count }}</template>'
    (ui / "App.html").write_text(source)
    assert check_project([ui]).ok
    (ui / "App.html").write_text(source.replace("this.count=2", 'this.count="bad"'))
    assert not check_project([ui]).ok


def test_named_slot_misspelling_is_checked(tmp_path):
    ui = project(tmp_path)
    (ui / "Counter.html").write_text(
        '<script>export default {};</script><template><slot name="header"></slot></template>'
    )
    source = '<script>import Counter from "./Counter.html";export default {components:{Counter}};</script><template><Counter><b slot="header">Hello</b></Counter></template>'
    (ui / "App.html").write_text(source)
    assert check_project([ui]).ok
    (ui / "App.html").write_text(source.replace('slot="header"', 'slot="hedaer"'))
    assert not check_project([ui]).ok


def test_attribute_entity_and_unicode_offsets(tmp_path):
    ui = project(tmp_path)
    source = '<script lang="ts">export default {data(){return {count:1,title:"x"};}};</script>\n<template>😀<p :title="count &gt; 0 ? title.missing : \'\'">Hello</p></template>'
    (ui / "App.html").write_text(source)
    result = check_project([ui])
    row = source.splitlines()[1]
    prefix = row[: row.index("missing")]
    expected = len(prefix.encode("utf-16-le")) // 2 + 1
    assert any(
        f.line == 2 and f.column == expected and f.code == 2339 for f in result.findings
    ), result.findings


@pytest.mark.parametrize(
    "registration",
    [
        'import Counter from "./Counter.html"; export default {components:{Renamed:Counter}};',
        'import * as UI from "./barrel.ts"; export default {components:{Renamed:UI.Counter}};',
    ],
)
def test_registered_aliases_and_namespace_contracts(tmp_path, registration):
    ui = project(tmp_path)
    (ui / "barrel.ts").write_text(
        'export {default as Counter} from "./Counter.html.ts";'
    )
    source = f'<script lang="ts">{registration}</script><template><Renamed :count="1" /></template>'
    (ui / "App.html").write_text(source)
    assert check_project([ui]).ok
    (ui / "App.html").write_text(source.replace(':count="1"', ":count=\"'bad'\""))
    assert not check_project([ui]).ok
