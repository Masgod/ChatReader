import asyncio
import io
import threading
import time
import wave
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from chatreader import server
from chatreader.config import Config
from chatreader.server import Hub, create_app


def make_wav(seconds: float = 0.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def clip_id(frame: bytes) -> int:
    return int.from_bytes(frame[:4], "big")


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out waiting for condition"
        time.sleep(0.005)


@pytest.fixture
def env():
    applied, spoken = [], []
    hub = Hub()
    hub.actions = []
    app = create_app(lambda: Config(), applied.append, hub, spoken.append, lambda: {"queue": 3}, hub.actions.append)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, hub, applied, spoken


def test_get_config_returns_current(env):
    client, *_ = env
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == asdict(Config())


def test_put_valid_config_calls_apply(env):
    client, _, applied, _ = env
    body = {**asdict(Config()), "queue_size": 7}
    assert client.put("/api/config", json=body).status_code == 200
    assert applied == [Config(queue_size=7)]


def test_put_normalizes_pasted_youtube_url_and_channel(env):
    client, _, applied, _ = env
    body = {
        **asdict(Config()),
        "twitch_channel": "#SomeChannel",
        "youtube_video_id": "https://youtu.be/dQw4w9WgXcQ?t=3",
    }
    assert client.put("/api/config", json=body).status_code == 200
    assert applied[0].twitch_channel == "somechannel"
    assert applied[0].youtube_video_id == "dQw4w9WgXcQ"


def test_put_invalid_returns_422_and_keeps_old(env):
    client, _, applied, _ = env
    r = client.put("/api/config", json={**asdict(Config()), "queue_size": 0})
    assert r.status_code == 422
    assert isinstance(r.json()["errors"], list) and r.json()["errors"]
    assert applied == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"port": "abc"},
        [],
        {**asdict(Config()), "port": True},
        {**asdict(Config()), "debug": 1},
        {**asdict(Config()), "ignored_users": ["a", 1]},
        {**asdict(Config()), "twitch_channel": None},
    ],
)
def test_put_missing_fields_or_wrong_types_422(env, body):
    client, _, applied, _ = env
    assert client.put("/api/config", json=body).status_code == 422
    assert applied == []


def test_put_empty_channel_is_ok(env):
    client, _, applied, _ = env
    body = {**asdict(Config()), "twitch_channel": "", "youtube_video_id": ""}
    assert client.put("/api/config", json=body).status_code == 200
    assert len(applied) == 1


def test_overlay_and_settings_pages_served(env):
    client, *_ = env
    for path in ("/overlay", "/settings", "/dock"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")


def test_hub_play_waits_for_done(env):
    client, hub, *_ = env
    wav = make_wav(30)  # long: only "done" can end it within the test
    with client.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
        wait_for(lambda: hub.connected)
        t = threading.Thread(target=hub.play, args=(wav,))
        t.start()
        frame = ws.receive_bytes()
        assert frame[4:] == wav
        time.sleep(0.05)
        assert t.is_alive()
        ws.send_text(f"done:{clip_id(frame)}")
        t.join(5)
        assert not t.is_alive()


def test_hub_stop_sends_stop_and_unblocks(env):
    client, hub, *_ = env
    with client.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
        wait_for(lambda: hub.connected)
        t = threading.Thread(target=hub.play, args=(make_wav(30),))
        t.start()
        ws.receive_bytes()
        hub.stop()
        assert ws.receive_text() == "stop"
        t.join(5)
        assert not t.is_alive()


def test_hub_play_times_out(env, monkeypatch):
    monkeypatch.setattr(server, "EXTRA_WAIT", 0.05)
    client, hub, *_ = env
    with client.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
        wait_for(lambda: hub.connected)
        t = threading.Thread(target=hub.play, args=(make_wav(),))
        t.start()
        ws.receive_bytes()  # never reply
        t.join(5)
        assert not t.is_alive()


def test_hub_play_without_overlay_returns_immediately(env):
    _, hub, *_ = env
    assert not hub.connected
    start = time.monotonic()
    hub.play(make_wav(30))
    assert time.monotonic() - start < 1


def test_hub_disconnect_clears_connected(env):
    client, hub, *_ = env
    with client.websocket_connect("/ws", headers={"host": "127.0.0.1"}):
        wait_for(lambda: hub.connected)
    wait_for(lambda: not hub.connected)


def test_post_test_calls_speak_test(env):
    client, _, _, spoken = env
    assert client.post("/api/test", json={"text": "hello"}).status_code == 200
    assert spoken == ["hello"]


def test_stale_done_does_not_release_next_play(env):
    client, hub, *_ = env
    with client.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as ws:
        wait_for(lambda: hub.connected)
        server.EXTRA_WAIT = 0.05
        try:
            hub.play(make_wav())  # clip A times out
        finally:
            server.EXTRA_WAIT = 2.0
        a = clip_id(ws.receive_bytes())
        t = threading.Thread(target=hub.play, args=(make_wav(30),))
        t.start()
        b = clip_id(ws.receive_bytes())
        assert b != a
        ws.send_text(f"done:{a}")  # late reply for A
        time.sleep(0.1)
        assert t.is_alive()
        ws.send_text(f"done:{b}")
        t.join(5)
        assert not t.is_alive()


def test_closing_stale_socket_does_not_end_current_play(env):
    client, hub, *_ = env
    with client.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as old:
        wait_for(lambda: hub.connected)
        first = hub._ws
        with client.websocket_connect("/ws", headers={"host": "127.0.0.1"}) as new:
            wait_for(lambda: hub._ws is not first)
            t = threading.Thread(target=hub.play, args=(make_wav(30),))
            t.start()
            frame = new.receive_bytes()
            old.close()
            time.sleep(0.2)
            assert t.is_alive()
            new.send_text(f"done:{clip_id(frame)}")
            t.join(5)
            assert not t.is_alive()


def test_run_server_starts_and_shuts_down():
    import socket
    from fastapi import FastAPI
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    stop = server.run_server(FastAPI(), port)
    with socket.create_connection(("127.0.0.1", port), timeout=2):
        pass
    stop()


def test_run_server_raises_when_port_taken():
    import socket
    from fastapi import FastAPI
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        with pytest.raises(RuntimeError):
            server.run_server(FastAPI(), s.getsockname()[1])


def test_put_returns_500_when_apply_fails():
    def boom(cfg):
        raise OSError("disk full")

    with TestClient(create_app(lambda: Config(), boom, Hub(), lambda t: None, lambda: {}, lambda a: None), base_url="http://127.0.0.1") as client:
        r = client.put("/api/config", json=asdict(Config()))
    assert r.status_code == 500 and "disk full" in r.json()["errors"][0]


def test_foreign_origin_host_and_non_json_rejected(env):
    client, hub, _, spoken = env
    evil = {"Origin": "http://evil.example", "Content-Type": "text/plain"}
    assert client.post("/api/test", content='{"text":"x"}', headers=evil).status_code == 403
    assert client.post("/api/test", content='{"text":"x"}', headers={"Content-Type": "text/plain"}).status_code == 403
    assert client.get("/api/config", headers={"Host": "evil.example"}).status_code == 403
    with pytest.raises(Exception):
        with client.websocket_connect("/ws", headers={"host": "127.0.0.1", "origin": "http://evil.example"}):
            pass
    assert spoken == []


def test_status_returns_snapshot(env):
    client, *_ = env
    r = client.get("/api/status")
    assert r.status_code == 200 and r.json() == {"queue": 3}


def test_status_survives_exception():
    def boom():
        raise RuntimeError("nope")

    app = create_app(lambda: Config(), lambda c: None, Hub(), lambda t: None, boom, lambda a: None)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        r = client.get("/api/status")
    assert r.status_code == 200 and "error" in r.json()


@pytest.mark.parametrize("action", ["pause", "resume", "skip"])
def test_control_calls_action(env, action):
    client, hub, *_ = env
    r = client.post("/api/control", json={"action": action})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert hub.actions == [action]


def test_control_rejects_bad_requests(env):
    client, hub, *_ = env
    assert client.post("/api/control", json={"action": "explode"}).status_code == 422
    assert client.post("/api/control", content="not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/control", json={"action": "skip"}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/control", content='{"action":"skip"}', headers={"Content-Type": "text/plain"}).status_code == 403
    assert hub.actions == []


def _ids(body, idents):
    for ident in idents:
        assert f'id="{ident}"' in body, ident


def test_app_page_has_shell(env):
    client, *_ = env
    _ids(client.get("/").text, ("tab-live", "tab-console", "tab-settings", "panel-live", "panel-console",
                                "panel-settings", "status-text", "banner"))


def test_dock_and_settings_serve_app(env):
    client, *_ = env
    assert client.get("/dock").text == client.get("/settings").text == client.get("/").text


def test_static_whitelist(env):
    client, *_ = env
    assert client.get("/static/app.js").headers["content-type"].startswith(("text/javascript", "application/javascript"))
    assert client.get("/static/app.css").headers["content-type"].startswith("text/css")
    for name in ("live.js", "console.js", "settings.js"):
        assert client.get(f"/static/{name}").status_code == 200
    for bad in ("../server.py", "nope.js", "%2e%2e%2fconfig.py", "app.html", "..%5cserver.py"):
        assert client.get(f"/static/{bad}").status_code == 404


def test_web_js_never_uses_innerhtml():
    from importlib import resources

    web = resources.files("chatreader") / "web"
    files = [f for f in web.iterdir() if f.name.endswith(".js")]
    assert files
    for f in files:
        assert "innerHTML" not in f.read_text("utf-8"), f.name


def test_live_panel_has_controls(env):
    client, *_ = env
    body = client.get("/").text
    _ids(body, ("st-twitch", "st-youtube", "st-overlay", "st-model", "btn-pause", "btn-skip", "btn-copy",
                "btn-quit", "queue-list", "btn-clear"))
    assert 'src="/static/live.js"' in body


def test_console_panel_has_controls(env):
    client, *_ = env
    body = client.get("/").text
    _ids(body, ("console-lines", "filter-all", "filter-chat", "filter-log", "toggle-debug", "btn-pause-scroll",
                "btn-clear-view", "btn-jump"))
    assert 'src="/static/console.js"' in body


def test_settings_panel_has_fields(env):
    client, *_ = env
    body = client.get("/").text
    _ids(body, ("voice_pt", "voice_en", "speed", "cpu_threads", "youtube_channel", "twitch_channel",
                "youtube_video_id", "queue_size", "max_chars", "repeat_window", "port", "btn-save", "btn-test",
                "checklist", "chk-model", "chk-source", "chk-overlay"))
    assert 'src="/static/settings.js"' in body


def test_old_page_files_removed():
    from importlib import resources

    web = resources.files("chatreader") / "web"
    assert not (web / "settings.html").is_file() and not (web / "dock.html").is_file()


# ---- control-center endpoints ----

class FakeQueue:
    def __init__(self):
        from chatreader.player import QueueItem

        self.playing = QueueItem(1, "now", "en", "ann")
        self.waiting = [QueueItem(2, "next", "pt", "bob")]
        self.cleared = 0

    def snapshot(self):
        return {"playing": self.playing, "waiting": list(self.waiting)}

    def remove(self, item_id):
        before = len(self.waiting)
        self.waiting = [i for i in self.waiting if i.id != item_id]
        return len(self.waiting) < before

    def clear(self):
        n, self.waiting = len(self.waiting), []
        return n


@pytest.fixture
def cc():
    from chatreader.events import EventLog

    events, toggles, actions = EventLog(), [], []
    q = FakeQueue()
    app = create_app(
        lambda: Config(), lambda c: None, Hub(), lambda t: None, lambda: {}, actions.append,
        queue=q, events=events, toggle=lambda n, v: toggles.append((n, v)),
        voices=lambda: {"pt": [{"id": "pf_dora", "label": "Dora (female)"}], "en": []},
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, q, events, toggles, actions


def test_queue_snapshot(cc):
    client, *_ = cc
    body = client.get("/api/queue").json()
    assert body["playing"] == {"id": 1, "text": "now", "lang": "en", "user": "ann", "voice": ""}
    assert [i["id"] for i in body["waiting"]] == [2]


def test_queue_remove_ok_and_404(cc):
    client, q, *_ = cc
    assert client.post("/api/queue/remove", json={"id": 2}).json() == {"ok": True}
    assert client.post("/api/queue/remove", json={"id": 2}).status_code == 404


@pytest.mark.parametrize("body", [{}, {"id": "x"}, {"id": True}, [1], {"id": 1.5}])
def test_queue_remove_bad_body(cc, body):
    client, *_ = cc
    assert client.post("/api/queue/remove", json=body).status_code == 422


def test_queue_clear(cc):
    client, *_ = cc
    assert client.post("/api/queue/clear", json={}).json() == {"removed": 1}


def test_events_since_and_bad_since(cc):
    client, _, events, *_ = cc
    events.add("app", "info", message="a")
    events.add("app", "info", message="b")
    assert [e["message"] for e in client.get("/api/events?since=1").json()["events"]] == ["b"]
    for bad in ("abc", "-5", "", "1e9999", "99999999999999999999"):
        r = client.get(f"/api/events?since={bad}")
        assert r.status_code == 200 and r.json()["last"] == 2


def test_toggle_debug_and_unknown(cc):
    client, _, _, toggles, _ = cc
    assert client.post("/api/toggle", json={"name": "debug", "value": True}).json() == {"ok": True}
    assert toggles == [("debug", True)]
    assert client.post("/api/toggle", json={"name": "other", "value": True}).status_code == 422
    assert client.post("/api/toggle", json={"name": "debug", "value": "yes"}).status_code == 422


def test_voices(cc):
    client, *_ = cc
    assert client.get("/api/voices").json()["pt"][0]["id"] == "pf_dora"


def test_quit_calls_control_after_response(cc):
    client, *_, actions = cc
    assert client.post("/api/control", json={"action": "quit"}).json() == {"ok": True}
    assert actions == ["quit"]


def test_new_routes_503_without_deps(env):
    client, *_ = env
    for path in ("/api/queue", "/api/events", "/api/voices"):
        assert client.get(path).status_code == 503
    assert client.post("/api/queue/clear", json={}).status_code == 503
    assert client.post("/api/toggle", json={"name": "debug", "value": True}).status_code == 503


def test_new_routes_reject_foreign_origin(cc):
    client, *_ = cc
    assert client.post("/api/queue/clear", json={}, headers={"Origin": "http://evil.com"}).status_code == 403
    assert client.post("/api/queue/clear", content="{}", headers={"Content-Type": "text/plain"}).status_code == 403


def test_control_actions_run_off_the_event_loop():
    seen = []

    def control(action):
        try:
            asyncio.get_running_loop()
            seen.append("on-loop")
        except RuntimeError:
            seen.append("off-loop")

    app = create_app(lambda: Config(), lambda c: None, Hub(), lambda t: None, lambda: {}, control)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.post("/api/control", json={"action": "skip"}).status_code == 200
    assert seen == ["off-loop"]  # Skip blocks on the overlay socket and must not stall the loop


def test_settings_panel_has_chat_rule_controls(env):
    client, *_ = env
    _ids(client.get("/").text, ("twitch_roles", "youtube_roles", "repeat_seconds", "per_user_voices"))


def test_put_rejects_bad_roles(env):
    client, _, applied, _ = env
    r = client.put("/api/config", json={**asdict(Config()), "twitch_roles": ["admin"]})
    assert r.status_code == 422 and any("twitch_roles" in e for e in r.json()["errors"]) and applied == []


def test_put_accepts_new_keys(env):
    client, _, applied, _ = env
    body = {**asdict(Config()), "twitch_roles": ["sub", "mod"], "youtube_roles": ["mod"], "repeat_seconds": 60, "per_user_voices": False}
    assert client.put("/api/config", json=body).status_code == 200
    assert (applied[0].twitch_roles, applied[0].repeat_seconds, applied[0].per_user_voices) == (["sub", "mod"], 60, False)


def test_page_icon_is_served_and_linked():
    from fastapi.testclient import TestClient

    from chatreader.config import Config
    from chatreader.server import Hub, create_app

    c = TestClient(create_app(lambda: Config(), lambda cfg: None, Hub(), lambda t: None, lambda: {"ok": True}, lambda a: None), base_url="http://127.0.0.1")
    r = c.get("/static/icon.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and b"<svg" in r.content
    assert 'rel="icon" href="/static/icon.svg"' in c.get("/").text
