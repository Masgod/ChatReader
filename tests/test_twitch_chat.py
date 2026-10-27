import json

import pytest

from chatreader.twitch_chat import TwitchChat, TwitchError

CID = "abc123def456ghi789"


class FakeHttp:
    """Answers by (method, url) from a queue of (status, body); records every call."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, method, url, headers=None, form=None, body=None):
        self.calls.append((method, url, headers or {}, form, body))
        return self.answers.pop(0)


def make(tmp_path, *answers):
    http = FakeHttp(*answers)
    return TwitchChat(tmp_path / "twitch_token.json", http=http, sleep=lambda s: None), http


def connected(tmp_path):
    path = tmp_path / "twitch_token.json"
    path.write_text(json.dumps({"client_id": CID, "access_token": "tok", "refresh_token": "ref", "user_id": "42"}), "utf-8")
    return path


def test_start_auth_returns_the_code_to_show(tmp_path):
    chat, http = make(tmp_path, (200, {"device_code": "dc", "user_code": "ABCD", "verification_uri": "https://www.twitch.tv/activate?device-code=ABCD", "expires_in": 1800, "interval": 5}))
    info = chat.start_auth(CID, wait=False)
    assert info == {"user_code": "ABCD", "verification_uri": "https://www.twitch.tv/activate?device-code=ABCD"}
    assert http.calls[0][3] == {"client_id": CID, "scopes": "user:write:chat"}
    assert chat.status() == "waiting"


def test_start_auth_failure_raises(tmp_path):
    chat, _ = make(tmp_path, (400, {"message": "invalid client"}))
    with pytest.raises(TwitchError, match="invalid client"):
        chat.start_auth(CID, wait=False)


def test_approval_is_polled_until_granted_then_saved(tmp_path):
    chat, http = make(
        tmp_path,
        (200, {"device_code": "dc", "user_code": "ABCD", "verification_uri": "u", "expires_in": 1800, "interval": 5}),
        (400, {"message": "authorization_pending"}),
        (200, {"access_token": "tok", "refresh_token": "ref", "expires_in": 14000}),
        (200, {"user_id": "42", "login": "masgod"}),
    )
    chat.start_auth(CID, wait=False)
    chat.wait_for_approval(CID, "dc", 5, 1800)
    assert chat.status() == "connected"
    saved = json.loads((tmp_path / "twitch_token.json").read_text("utf-8"))
    assert (saved["access_token"], saved["refresh_token"], saved["user_id"], saved["client_id"]) == ("tok", "ref", "42", CID)
    assert http.calls[2][3]["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"


def test_denied_or_expired_approval_ends_in_error(tmp_path):
    chat, _ = make(tmp_path, (400, {"message": "access_denied"}))
    chat.wait_for_approval(CID, "dc", 5, 1800)
    assert chat.status() == "error"


def test_token_on_disk_means_connected(tmp_path):
    connected(tmp_path)
    chat, _ = make(tmp_path)
    assert chat.status() == "connected"


def test_send_looks_up_the_channel_then_posts(tmp_path):
    connected(tmp_path)
    chat, http = make(tmp_path, (200, {"data": [{"id": "777"}]}), (200, {"data": [{"is_sent": True}]}))
    assert chat.send(CID, "MasGod", "@alice agora é Wraith")
    assert "login=masgod" in http.calls[0][1]
    method, url, headers, _, body = http.calls[1]
    assert (method, url.endswith("/chat/messages")) == ("POST", True)
    assert body == {"broadcaster_id": "777", "sender_id": "42", "message": "@alice agora é Wraith"}
    assert headers["Authorization"] == "Bearer tok" and headers["Client-Id"] == CID


def test_send_remembers_the_channel_id(tmp_path):
    connected(tmp_path)
    chat, http = make(tmp_path, (200, {"data": [{"id": "777"}]}), (200, {}), (200, {}))
    chat.send(CID, "masgod", "a")
    chat.send(CID, "masgod", "b")
    assert len(http.calls) == 3


def test_send_refreshes_an_expired_token_once(tmp_path):
    path = connected(tmp_path)
    chat, http = make(
        tmp_path,
        (401, {}),
        (200, {"access_token": "tok2", "refresh_token": "ref2"}),
        (200, {"data": [{"id": "777"}]}),
        (200, {}),
    )
    assert chat.send(CID, "masgod", "hi")
    assert http.calls[2][2]["Authorization"] == "Bearer tok2"
    assert json.loads(path.read_text("utf-8"))["refresh_token"] == "ref2"


def test_send_without_a_login_or_with_another_client_id_does_nothing(tmp_path):
    chat, http = make(tmp_path)
    assert chat.send(CID, "masgod", "hi") is False
    connected(tmp_path)
    chat2, http2 = make(tmp_path)
    assert chat2.send("other-client-id-0000", "masgod", "hi") is False
    assert http.calls == [] and http2.calls == []


def test_send_failure_returns_false_and_never_raises(tmp_path):
    connected(tmp_path)
    chat, _ = make(tmp_path, (200, {"data": [{"id": "777"}]}), (403, {"message": "not allowed"}))
    assert chat.send(CID, "masgod", "hi") is False

    def boom(*a, **k):
        raise OSError("offline")

    chat3 = TwitchChat(tmp_path / "twitch_token.json", http=boom, sleep=lambda s: None)
    assert chat3.send(CID, "masgod", "hi") is False


def test_message_is_cut_to_the_twitch_limit(tmp_path):
    connected(tmp_path)
    chat, http = make(tmp_path, (200, {"data": [{"id": "1"}]}), (200, {}))
    chat.send(CID, "masgod", "x" * 900)
    assert len(http.calls[1][4]["message"]) == 500
