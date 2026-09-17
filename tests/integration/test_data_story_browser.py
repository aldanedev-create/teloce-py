import shutil
import re
import time
from pathlib import Path

import pytest

from teloce.build import build_project
from teloce.cli.server import start_dev_server
from tests.integration.test_browser_e2e import _chrome, _dump_dom


@pytest.mark.skipif(_chrome() is None, reason="Chrome/Chromium is not installed")
def test_data_story_mounts_csv_virtual_list_and_table_in_real_chrome(tmp_path: Path):
    example = Path(__file__).parents[2] / "examples" / "data-story"
    root = tmp_path / "story"
    shutil.copytree(example / "static", root / "static")
    (root / "templates").mkdir()
    (root / "templates" / "index.html").write_text(
        '<div id="app"></div><script type="module">'
        'import { mount } from "/static/js/App.js"; mount("#app"); '
        'setTimeout(() => document.title = "story:" + '
        'document.querySelectorAll(".virtual-row").length + ":" + '
        'document.querySelectorAll("table").length, 3000);</script>',
        encoding="utf-8",
    )
    result = build_project(root, options={"dev": True, "clean": True, "source_maps": False})
    assert result["failed"] == 0, result["errors"]
    server = start_dev_server("127.0.0.1", 0, root / "dist", hmr=False)
    try:
        time.sleep(0.1)
        browser = _dump_dom(f"http://127.0.0.1:{server.server_port}/?no_hmr=1", 6000)
        assert browser.returncode == 0, browser.stderr
        title = re.search(r"<title>([^<]*)</title>", browser.stdout)
        assert title and title.group(1).startswith("story:"), browser.stdout
        assert title.group(1) == "story:11:1", title.group(1)
        assert 'data-metric="rows"' in browser.stdout
        assert 'data-action-label="evidence chart"' in browser.stdout
        assert "Small data, clear decisions." in browser.stdout
        assert "Sortable, filterable table" in browser.stdout
    finally:
        server.shutdown()
        server.server_close()
