from pathlib import Path
import os

from flask import Flask, jsonify, send_from_directory
from teloce.build import build_project


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# The documented fast path is simply ``python app.py``. Build from the
# checked-out editable compiler before Flask starts so a stale generated
# runtime cannot mask a compiler change.
build_project(ROOT, out_dir=DIST, options={"dev": True, "clean": True, "source_maps": False})

app = Flask(__name__, static_folder=str(DIST / "static"), static_url_path="/static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.get("/")
def home():
    return send_from_directory(DIST, "index.html")


@app.get("/api/stats")
def stats():
    # A real API response. In production this can be replaced with a database
    # query without changing the .vel component.
    return jsonify({"stats": {"updated": "live", "requests": 12842, "growth": 18.4}})


if __name__ == "__main__":
    # 5060 is rejected by Chromium as an unsafe port. 5057 keeps the
    # one-command example browser-compatible on Windows and CI. Override it
    # when another local service already owns the default port.
    port = int(os.environ.get("TELOCE_DATA_STORY_PORT", "5057"))
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
