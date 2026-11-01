import importlib.util
from pathlib import Path

import pytest


pytest.importorskip("flask")
ROOT = Path(__file__).parents[2] / "examples" / "flask-youtube-ssr"


def load_example():
    path = ROOT / "app.py"
    spec = importlib.util.spec_from_file_location("flask_youtube_ssr_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_youtube_links_are_normalized_to_privacy_embeds():
    module = load_example()
    assert module.youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert module.youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert module.normalize_video(
        "https://www.youtube.com/shorts/dQw4w9WgXcQ", "Demo"
    )["embed_url"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
    with pytest.raises(ValueError):
        module.youtube_video_id("https://evil.example/watch?v=dQw4w9WgXcQ")


def test_flask_route_renders_ssr_iframes_and_rejects_bad_urls():
    module = load_example()
    renderer = module.build_renderer()
    client = module.create_app(renderer).test_client()

    page = client.get("/")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'data-teloce-ssr="1"' in body
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in body
    assert 'rel="stylesheet"' in body
    assert any(
        str(item.get("output", "")).endswith(".css")
        for item in renderer.manifest["files"]
    )
    assert renderer.manifest["bundler"] == "minifyjs"
    assert renderer.manifest["bundle_outputs"]
    assert renderer.entries["ui/App.html"]["client"] in {
        item["output"] for item in renderer.manifest["bundle_outputs"]
    }

    bad = client.post(
        "/add", data={"url": "https://evil.example/video", "title": "Unsafe"}
    )
    assert bad.status_code == 400

    good = client.post(
        "/add",
        data={"url": "https://youtu.be/9bZkp7q19f0", "title": "Added video"},
    )
    assert good.status_code == 302
    assert "youtube-nocookie.com/embed/9bZkp7q19f0" in client.get("/").get_data(as_text=True)
