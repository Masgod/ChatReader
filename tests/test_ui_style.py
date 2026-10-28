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


def test_touch_home_has_four_buttons_and_every_page_target_exists():
    with _client() as c:
        html = c.get("/settings").text
        js = c.get("/static/touchnav.js").text
    assert html.count('class="tile"') == 4 and 'id="subs"' in html and 'id="back"' in html
    assert 'dataset.view = "home"' in html
    for sect in ("sources", "voices", "reading", "events", "ignored", "overlay", "system"):
        assert f'id="sect-{sect}"' in html and f"sect-{sect}" in js  # a renamed section must not leave a dead menu entry


def test_touch_menu_is_hidden_in_mouse_style_and_the_tabs_are_hidden_in_touch():
    with _client() as c:
        css = c.get("/static/app.css").text
    assert "#home, #subs, #back { display: none; }" in css  # base = mouse style: tabs only
    assert "html[data-ui=touch] .tabs { display: none; }" in css


def test_touch_rules_exist_and_the_mouse_style_has_none():
    with _client() as c:
        css = c.get("/static/app.css").text
    assert "html[data-ui=touch] .btn" in css
    assert "html[data-ui=mouse]" not in css  # mouse is the base style, touch only adds
