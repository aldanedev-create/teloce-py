"""Real-browser hydration, runtime reports, and signal state seeding."""

import json

import pytest

from teloce.build import Builder
from teloce.server import Renderer
from teloce.cli.server import start_dev_server

pytest.importorskip("playwright.sync_api")


@pytest.mark.parametrize("production", [False, True])
def test_hydration_keeps_nodes_focus_and_signal_updates(tmp_path, production):
    from playwright.sync_api import sync_playwright

    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "App.html").write_text(
        """<template><article><h1>{{ title }}</h1><input :value="title"><button @click="count.value++">Count</button><p>{{ count.value }}</p><ul><li v-for="(item, i) in items" :key="item.id">{{ i }}:{{ item.name }}</li></ul><button @click="fail">Fail</button></article></template><script>export default {data(){return {title:'Default',count:signal(0),items:[]}},methods:{fail(){throw new Error('Example failure')}}}</script><style scoped>article{color:navy}</style>"""
    )
    result = Builder(
        {
            "ssr": True,
            "html_mode": True,
            "source_roots": ["ui"],
            "mode": "production" if production else "development",
            "dev": not production,
            "source_maps": True,
        }
    ).build(tmp_path)
    assert not result["failed"], result["errors"]
    data = {
        "title": "Server title",
        "count": {"value": 4},
        "items": [{"id": 1, "name": "One"}, {"id": 2, "name": "Two"}],
    }
    rendered = Renderer(tmp_path / "dist").render("ui/App.js", data)
    script = """window.reports=[];window.addEventListener('teloce:error',e=>reports.push(e.detail));window.oldArticle=document.querySelector('article');window.oldRows=[...document.querySelectorAll('li')];window.input=document.querySelector('input');input.value='Typed before startup';input.focus();input.setSelectionRange(2,5);window.begin=async()=>{const module=await import('/ui/App.js');window.app=module.hydrate('#app',window.data);};"""
    (tmp_path / "dist/index.html").write_text(
        '<div id="app" data-teloce-ssr="1">'
        + rendered.html
        + "</div><script>window.data="
        + rendered.props_json
        + ";"
        + script
        + "</script>"
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path / "dist", hmr=False)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/?no_hmr=1")
            page.evaluate("begin()")
            page.wait_for_function("window.app")
            assert page.evaluate('oldArticle===document.querySelector("article")')
            assert page.evaluate(
                'oldRows.every((row,i)=>row===document.querySelectorAll("li")[i])'
            )
            assert page.locator("input").input_value() == "Typed before startup"
            assert page.evaluate(
                "document.activeElement===input && input.selectionStart===2"
            )
            assert page.locator("li").all_text_contents() == ["0:One", "1:Two"]
            assert page.locator("p").inner_text() == "4"
            page.get_by_role("button", name="Count", exact=True).click()
            page.wait_for_function('document.querySelector("p").textContent==="5"')
            page.get_by_role("button", name="Fail", exact=True).click()
            page.wait_for_function(
                'reports.some(report=>report.message==="Example failure")'
            )
            assert (
                page.evaluate(
                    'reports.find(report=>report.message==="Example failure").component'
                )
                == "ui/App.html"
            )
            page.evaluate("app.unmount()")
            assert page.locator("#app").inner_html() == ""
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_hydration_reports_structural_mismatch(tmp_path):
    from playwright.sync_api import sync_playwright

    (tmp_path / "ui").mkdir()
    (tmp_path / "ui/App.html").write_text(
        "<template><article><h1>{{ title }}</h1></article></template>"
    )
    result = Builder(
        {"ssr": True, "html_mode": True, "source_roots": ["ui"], "dev": True}
    ).build(tmp_path)
    assert result["failed"] == 0
    (tmp_path / "dist/index.html").write_text(
        """<div id="app" data-teloce-ssr="1"><aside>Old server content</aside></div><script type="module">window.reports=[];window.addEventListener('teloce:error',e=>reports.push(e.detail));import {hydrate} from '/ui/App.js';window.app=hydrate('#app',{title:'New'});</script>"""
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path / "dist", hmr=False)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/?no_hmr=1")
            page.wait_for_selector("h1")
            assert page.locator("h1").inner_text() == "New"
            assert page.evaluate('reports.some(report=>report.category==="hydration")')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def test_child_and_named_slots_hydrate_in_place(tmp_path):
    from playwright.sync_api import sync_playwright

    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "Card.html").write_text(
        """<template><section><h2>{{ title }}</h2><slot name="heading"></slot><slot></slot><button @click="clicks.value++">Child</button><p>{{ clicks.value }}</p></section></template><script>export default {props:{title:String,clicks:Object},data(){return {clicks:signal(0)}}}</script>"""
    )
    (ui / "App.html").write_text(
        """<template><main><Card :title="title" :clicks="clicks"><strong slot="heading">Heading</strong><span>{{ title }}</span></Card></main></template><script>import Card from './Card.html'; export default {components:{Card},data(){return {title:'Default',clicks:{value:0}}}}</script>"""
    )
    result = Builder(
        {"ssr": True, "html_mode": True, "source_roots": ["ui"], "dev": True}
    ).build(tmp_path)
    assert not result["failed"], result["errors"]
    rendered = Renderer(tmp_path / "dist").render(
        "ui/App.js", {"title": "Server", "clicks": {"value": 2}}
    )
    (tmp_path / "dist/index.html").write_text(
        '<div id="app" data-teloce-ssr="1">'
        + rendered.html
        + '</div><script>window.oldSection=document.querySelector("section");window.oldHeading=document.querySelector("strong");</script><script type="module">import {hydrate} from "/ui/App.js";window.app=hydrate("#app",'
        + rendered.props_json
        + ");</script>"
    )
    server = start_dev_server("127.0.0.1", 0, tmp_path / "dist", hmr=False)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/?no_hmr=1")
            page.wait_for_function("window.app")
            assert page.evaluate('oldSection===document.querySelector("section")')
            assert page.evaluate('oldHeading===document.querySelector("strong")')
            assert page.locator("h2").inner_text() == "Server"
            assert page.locator("p").inner_text() == "2"
            page.get_by_role("button", name="Child", exact=True).click()
            page.wait_for_function('document.querySelector("p").textContent==="3"')
            page.evaluate("app.unmount()")
            assert page.locator("#app").inner_html() == ""
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
