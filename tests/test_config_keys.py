import dataclasses

import pytest
from fastapi.testclient import TestClient

from chatreader.config import Config, load_config, normalize, validate
from chatreader.server import Hub, create_app

UC = "UC" + "a" * 22


@pytest.mark.parametrize("v,ok", [(0.8, True), (1.4, True), (1.0, True), (0.79, False), (1.41, False), (float("nan"), False)])
def test_speed_bounds(v, ok):
    assert (validate(Config(speed=v)) == []) is ok


@pytest.mark.parametrize("v,ok", [(1, True), (8, True), (0, False), (9, False)])
def test_cpu_threads_bounds(v, ok):
    assert (validate(Config(cpu_threads=v)) == []) is ok


@pytest.mark.parametrize("v,ok", [("@some.name-1", True), (UC, True), ("", True), ("some name", False), ("@", False), ("UCshort", False)])
def test_channel_forms(v, ok):
    assert (validate(Config(youtube_channel=v)) == []) is ok


def test_channel_url_normalizes():
    assert normalize(Config(youtube_channel="https://www.youtube.com/@Foo/live")).youtube_channel == "@Foo"
    assert normalize(Config(youtube_channel=f"youtube.com/channel/{UC}")).youtube_channel == UC


def _client():
    app = create_app(lambda: Config(), lambda c: None, Hub(), lambda t: None, lambda: {}, lambda a: None)
    return TestClient(app, base_url="http://127.0.0.1")


def test_put_accepts_int_for_float_speed_but_not_bool():
    body = dataclasses.asdict(Config())
    with _client() as c:
        assert c.put("/api/config", json={**body, "speed": 1}).status_code == 200
        assert c.put("/api/config", json={**body, "speed": True}).status_code == 422


def test_load_config_accepts_int_speed(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("speed = 1\n", encoding="utf-8")
    assert load_config(path).speed == 1
