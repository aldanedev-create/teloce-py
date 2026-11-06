"""The generated teloce-runtime.js barrel exposes the network clients, in every build mode."""
import json
import shutil
import subprocess

import pytest

from teloce.build import build_project

NAMES = ["http", "action", "createHttp", "createActionClient", "createSocket", "createScope",
         "networkPlugin", "NetworkError", "HttpClient", "ActionClient", "SocketClient"]


@pytest.mark.parametrize("options", [{}, {"minify": True}, {"minify": True, "hash_assets": True}], ids=["dev", "minify", "hashed"])
def test_barrel_exports_network_clients(tmp_path, options):
    js = tmp_path / "static" / "js"
    js.mkdir(parents=True)
    (js / "App.vel").write_text("<template><main>hi</main></template>\n<script>export default {}</script>\n")
    result = build_project(str(tmp_path), str(tmp_path / "dist"), options=options)
    assert result["failed"] == 0
    barrel = next((tmp_path / "dist").rglob("teloce-runtime*.js"))
    assert (barrel.parent / "network.js").is_file()  # emitted next to signals.js, which it imports
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to import the barrel")
    probe = tmp_path / "probe.mjs"
    probe.write_text(f"""import * as rt from {json.dumps(barrel.as_posix())};
const a = new rt.ActionClient({{ fetch: async (url, init) => new Response(JSON.stringify({{ success: true, data: {{ url }} }}), {{ headers: {{ 'content-type': 'application/json' }} }}) }});
const result = await a.call('todos.create', {{}});
console.log(JSON.stringify({{ missing: {json.dumps(NAMES)}.filter(name => !(name in rt)), url: result.data.url, signal: typeof rt.signal }}));
""")
    out = subprocess.run([node, str(probe)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    assert json.loads(out.stdout) == {"missing": [], "url": "/_teloce/actions/todos.create", "signal": "function"}
