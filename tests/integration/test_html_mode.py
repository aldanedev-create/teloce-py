from pathlib import Path

from teloce.build import Builder
from teloce.compiler import compile as compile_component
from teloce.project.scanner import ProjectScanner
from teloce.router import generate_spa_router


def test_html_component_imports_compile_to_javascript(tmp_path: Path) -> None:
    ui = tmp_path / "ui"
    components = ui / "components"
    components.mkdir(parents=True)
    (components / "Greeting.html").write_text(
        "<template><p>Hello {{ name }}</p></template>"
        "<script>export default { props: ['name'] };</script>",
        encoding="utf-8",
    )
    (ui / "app.html").write_text(
        "<template><main><Greeting name=\"Flaxon\" /></main></template>"
        '<script>import Greeting from "./components/Greeting.html"; '
        "export default { components: { Greeting } };</script>",
        encoding="utf-8",
    )

    result = Builder(
        {
            "html_mode": True,
            "source_roots": ["ui"],
            "spa": False,
            "source_maps": False,
        }
    ).build(tmp_path, tmp_path / ".flaxon" / "build")

    assert result["failed"] == 0
    assert result["total"] == 2
    app = (tmp_path / ".flaxon" / "build" / "ui" / "app.js").read_text(
        encoding="utf-8"
    )
    assert 'from "./components/Greeting.js"' in app
    assert (tmp_path / ".flaxon" / "build" / "ui" / "components" / "Greeting.js").is_file()


def test_html_mode_keeps_vel_compatibility_and_multiple_roots(tmp_path: Path) -> None:
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "app.html").write_text(
        "<template><main>Shell</main></template>", encoding="utf-8"
    )
    module_ui = tmp_path / "modules" / "orders" / "ui" / "pages"
    module_ui.mkdir(parents=True)
    (module_ui / "Orders.vel").write_text(
        "<template><h1>Orders</h1></template>", encoding="utf-8"
    )

    result = Builder(
        {
            "html_mode": True,
            "source_roots": ["ui", "modules/orders/ui"],
            "spa": False,
            "source_maps": False,
        }
    ).build(tmp_path, tmp_path / ".flaxon" / "build")

    assert result["failed"] == 0
    assert {item["input"] for item in result["files"]} >= {
        "ui/app.html",
        "modules/orders/ui/pages/Orders.vel",
    }


def test_direct_html_compile_rewrites_html_import() -> None:
    result = compile_component(
        "<template><Card /></template>"
        '<script>import Card from "./Card.html"; export default { components: { Card } };</script>',
        filename="App.html",
        source_maps=False,
    )

    assert result["success"] is True
    assert 'from "./Card.js"' in result["code"]
    assert result["code"].count('from "./Card.js"') == 1
    assert "./Card.html" not in result["code"]


def test_scanner_accepts_configured_extensions(tmp_path: Path) -> None:
    (tmp_path / "App.html").write_text("", encoding="utf-8")
    (tmp_path / "Legacy.vel").write_text("", encoding="utf-8")

    files = ProjectScanner([".html", ".vel"]).scan(tmp_path)

    assert [path.name for path in files] == ["App.html", "Legacy.vel"]


def test_spa_router_combines_page_directories(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    orders = tmp_path / "orders"
    catalog.mkdir()
    orders.mkdir()
    (catalog / "Products.js").write_text("export default {};", encoding="utf-8")
    (orders / "Orders.js").write_text("export default {};", encoding="utf-8")

    output = generate_spa_router(tmp_path / "router.js", [catalog, orders])
    source = output.read_text(encoding="utf-8")

    assert 'path: "/products"' in source
    assert 'path: "/orders"' in source


def test_dashboard_page_is_the_conventional_root_route(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "Dashboard.js").write_text("export default {};", encoding="utf-8")

    source = generate_spa_router(tmp_path / "router.js", pages).read_text(encoding="utf-8")

    assert 'path: "/"' in source
