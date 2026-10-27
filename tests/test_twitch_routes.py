from fastapi.testclient import TestClient

from chatreader.config import Config
from chatreader.server import Hub, create_app
from chatreader.twitch_chat import TwitchError

CID = "abcdefghij0123456789"


class FakeTwitch:
    def __init__(self, error=None):
        self.error, self.started = error, []

    def start_auth(self, client_id):
        if self.error:
            raise self.error
        self.started.append(client_id)
        return {"user_code": "ABCD", "verification_uri": "https://www.twitch.tv/activate"}

    def status(self):
        return "waiting"


def _client(cfg, twitch):
    app = create_app(lambda: cfg, lambda c: None, Hub(), lambda t: None, lambda: {}, lambda a: None, twitch=twitch)
    return TestClient(app, base_url="http://127.0.0.1")


def test_login_returns_the_code_and_link():
    twitch = FakeTwitch()
    with _client(Config(twitch_client_id=CID), twitch) as c:
        r = c.post("/api/twitch/login", json={})
        assert r.status_code == 200 and r.json() == {"user_code": "ABCD", "verification_uri": "https://www.twitch.tv/activate"}
        assert c.get("/api/twitch/status").json() == {"state": "waiting"}
    assert twitch.started == [CID]


def test_login_needs_a_saved_client_id():
    with _client(Config(), FakeTwitch()) as c:
        assert c.post("/api/twitch/login", json={}).status_code == 422


def test_login_failure_is_reported():
    with _client(Config(twitch_client_id=CID), FakeTwitch(TwitchError("invalid client"))) as c:
        r = c.post("/api/twitch/login", json={})
    assert r.status_code == 502 and "invalid client" in r.json()["errors"][0]


def test_routes_degrade_without_a_sender():
    with _client(Config(), None) as c:
        assert c.post("/api/twitch/login", json={}).status_code == 503
        assert c.get("/api/twitch/status").json() == {"state": "off"}
