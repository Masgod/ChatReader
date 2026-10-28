from fastapi.testclient import TestClient

from chatreader.config import Config
from chatreader.server import Hub, create_app


def _client():
    app = create_app(lambda: Config(), lambda c: None, Hub(), lambda t: None, lambda: {}, lambda a: None)
    return TestClient(app, base_url="http://127.0.0.1")


def test_settings_page_sets_the_style_before_paint_and_offers_the_switch():
    with _client() as c:
        html = c.get("/settings").text
    assert html.index('dataset.ui = ui === "mouse"') < html.index("<header")  # no flash of the other style
    assert 'data-ui="touch"' in html and 'data-ui="mouse"' in html


def test_touch_rules_exist_and_the_mouse_style_has_none():
    with _client() as c:
        css = c.get("/static/app.css").text
    assert "html[data-ui=touch] .btn" in css
    assert "html[data-ui=mouse]" not in css  # mouse is the base style, touch only adds
