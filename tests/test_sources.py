import logging
import threading

from websockets.exceptions import ConnectionClosed

from chatreader.models import Msg
from chatreader.sources import twitch
from chatreader.sources.common import run_with_backoff
from chatreader.sources.twitch import _session, parse_privmsg


class FakeWS:
    """Yields queued frames, then raises ConnectionClosed like a dropped socket."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)

    def recv(self, timeout=None):
        if not self.frames:
            raise ConnectionClosed(None, None)
        return self.frames.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_parse_privmsg_with_tags():
    msg = parse_privmsg(
        "@display-name=Alice;color=#fff :alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :oi pessoal"
    )
    assert msg is not None
    assert (msg.platform, msg.user, msg.text) == ("twitch", "Alice", "oi pessoal")
    assert msg.ts > 0


def test_parse_privmsg_without_tags_uses_nick():
    msg = parse_privmsg(":alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :hi\r\n")
    assert msg is not None
    assert (msg.user, msg.text) == ("alice", "hi")


def test_parse_privmsg_empty_display_name_uses_nick():
    msg = parse_privmsg(
        "@display-name=;color=#fff :bob!bob@bob.tmi.twitch.tv PRIVMSG #chan :yo"
    )
    assert msg is not None
    assert msg.user == "bob"


def test_parse_ignores_ping_and_join():
    assert parse_privmsg("PING :tmi.twitch.tv") is None
    assert parse_privmsg(":alice!alice@alice.tmi.twitch.tv JOIN #chan") is None


def test_parse_message_containing_colons():
    msg = parse_privmsg(
        ":alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :oi: tudo bem: sim"
    )
    assert msg is not None
    assert msg.text == "oi: tudo bem: sim"


def test_backoff_delays():
    stop = threading.Event()
    waits = []

    def fake_sleep(s):
        waits.append(s)
        if len(waits) == 7:
            stop.set()

    def fn():
        raise RuntimeError("boom")

    run_with_backoff(fn, stop, lambda s: None, sleep=fake_sleep)
    assert waits == [1, 2, 4, 8, 16, 30, 30]


def test_backoff_resets_after_success():
    stop = threading.Event()
    waits = []
    outcomes = iter(["fail", "fail", "fail", "ok", "fail"])

    def fake_sleep(s):
        waits.append(s)

    def fn():
        try:
            outcome = next(outcomes)
        except StopIteration:
            stop.set()
            return None
        if outcome == "fail":
            raise RuntimeError("boom")
        return True  # delivered at least one message

    run_with_backoff(fn, stop, lambda s: None, sleep=fake_sleep)
    assert waits == [1, 2, 4, 1, 2]


def test_failed_status_after_max_failures():
    stop = threading.Event()
    statuses = []
    waits = []

    def fn():
        raise RuntimeError("boom")

    run_with_backoff(
        fn,
        stop,
        statuses.append,
        sleep=waits.append,
        max_failures=3,
    )
    assert statuses[-1] == "failed"
    assert waits == [1, 2]


def test_stop_event_ends_loop():
    stop = threading.Event()
    waits = []
    calls = []

    def fn():
        calls.append(1)
        stop.set()
        raise RuntimeError("boom")

    run_with_backoff(fn, stop, lambda s: None, sleep=waits.append)
    assert len(calls) == 1
    assert waits == []


def test_failing_fn_is_logged(caplog):
    stop = threading.Event()

    def fn():
        raise RuntimeError("boom")

    caplog.set_level(logging.WARNING)
    run_with_backoff(fn, stop, lambda s: None, sleep=lambda s: stop.set())
    records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert records
    assert records[0].exc_info is not None
    assert "boom" in str(records[0].exc_info[1])


def test_session_delivering_then_dropped_returns_truthy(monkeypatch):
    frame = ":alice!alice@alice.tmi.twitch.tv PRIVMSG #chan :hi"
    ws = FakeWS([frame])
    monkeypatch.setattr(twitch, "connect", lambda url: ws)
    got = []
    result = _session("chan", got.append, threading.Event(), lambda s: None)
    assert result
    assert [m.text for m in got] == ["hi"]


def test_session_dropped_without_messages_returns_falsy(monkeypatch):
    ws = FakeWS([])
    monkeypatch.setattr(twitch, "connect", lambda url: ws)
    result = _session("chan", lambda m: None, threading.Event(), lambda s: None)
    assert not result


# --- YouTube source ---------------------------------------------------------
import functools
from types import SimpleNamespace

from chatreader.sources import youtube


class FakeYTChat:
    """Serves queued batches of items; sets `stop` once they run out."""

    def __init__(self, batches, stop, alive=True):
        self.batches = list(batches)
        self.stop = stop
        self.alive = alive
        self.terminated = False

    def is_alive(self):
        return self.alive

    def get(self):
        return self

    def sync_items(self):
        if self.batches:
            return self.batches.pop(0)
        self.stop.set()
        return []

    def terminate(self):
        self.terminated = True


def _item(name, text):
    return SimpleNamespace(author=SimpleNamespace(name=name), message=text)


def test_to_msg_maps_fields():
    msg = youtube.to_msg(_item("Bob", "ola"))
    assert (msg.platform, msg.user, msg.text) == ("youtube", "Bob", "ola")
    assert msg.ts > 0


def test_run_youtube_delivers_items_then_stops():
    stop = threading.Event()
    chat = FakeYTChat([[_item("A", "um"), _item("B", "dois")]], stop)
    got = []
    youtube.run_youtube("vid", got.append, stop, lambda s: None,
                        chat_factory=lambda video_id: chat)
    assert [(m.user, m.text) for m in got] == [("A", "um"), ("B", "dois")]
    assert chat.terminated


def test_chat_ended_reports_failed_after_retries(monkeypatch):
    stop = threading.Event()
    chat = FakeYTChat([], stop, alive=False)
    real = youtube.run_with_backoff
    monkeypatch.setattr(
        youtube, "run_with_backoff",
        functools.partial(real, sleep=lambda s: None),
    )
    statuses = []
    youtube.run_youtube("vid", lambda m: None, stop, statuses.append,
                        chat_factory=lambda video_id: chat)
    assert statuses[-1] == "failed"
    assert statuses.count("connected") == 5
