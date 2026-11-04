
from importlib import resources
from pathlib import Path

from fastapi.testclient import TestClient

from chatreader.config import Config
from chatreader.server import Hub, create_app

ROOT = Path(__file__).resolve().parent.parent


def _client():
    app = create_app(lambda: Config(), lambda c: None, Hub(), lambda t: None, lambda: {}, lambda a: None)
    return TestClient(app, base_url="http://127.0.0.1")


def test_stream_page_loads_the_audio_and_the_bubbles_once_each():
    with _client() as c:
        page = c.get("/stream")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert page.text.count("/static/audio.js") == 1 and page.text.count("/static/chat-overlay.js") == 1
    assert page.text.count("/static/chat-overlay.css") == 1


def test_overlay_page_still_works_and_loads_the_shared_audio_script():
    with _client() as c:
        page = c.get("/overlay")
        assert page.status_code == 200 and page.text.count("/static/audio.js") == 1
        assert "new WebSocket" not in page.text  # the script lives in audio.js only, so it cannot drift
        js = c.get("/static/audio.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    body = js.text.replace(chr(13), "")
    assert "(() => {" in body.split(chr(10))[1] and body.rstrip().endswith("})();")  # no globals: /stream also loads chat-overlay.js
    assert js.text.count("new WebSocket") == 1 and '"/ws"' in js.text and "done:" in js.text


def test_old_chat_overlay_page_is_unchanged_and_has_no_audio_script():
    with _client() as c:
        page = c.get("/chat-overlay")
    assert page.status_code == 200 and "/static/audio.js" not in page.text


def test_live_tab_and_tray_copy_the_stream_url():
    web = resources.files("chatreader") / "web"
    assert 'location.origin + "/stream"' in (web / "live.js").read_text("utf-8")
    assert 'f"{base}/stream"' in (ROOT / "src" / "chatreader" / "main.py").read_text("utf-8")


def test_new_static_files_are_inside_the_bundled_web_folder():
    spec = (ROOT / "packaging" / "chatreader.spec").read_text("utf-8")
    assert '"chatreader" / "web"' in spec.replace("'", '"') or "chatreader/web" in spec  # the whole folder is bundled
    for name in ("audio.js", "stream.html"):
        assert (resources.files("chatreader") / "web" / name).is_file()
