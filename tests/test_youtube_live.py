import threading
import time

from chatreader.sources import youtube
from chatreader.sources.youtube_live import resolve_live_video

LIVE = ('<html><link rel="canonical" href="https://www.youtube.com/watch?v=1-LpQekNa9g">'
        '<script>{"isLiveNow":true,"videoId":"1-LpQekNa9g"}</script></html>')
UPCOMING = LIVE.replace('"isLiveNow":true', '"isLiveNow":false')
OFFLINE = ('<html><link rel="canonical" href="https://www.youtube.com/channel/UCK8sQmJBp8GCxrOtXWBpyEA">'
           '<script>{"videoId":"wYSncx9zLIU"}</script></html>')


def fetch_of(body, status=200):
    return lambda url: (status, url, body)


def test_resolver_live_and_not_live():
    assert resolve_live_video("@LofiGirl", fetch_of(LIVE)) == "1-LpQekNa9g"
    assert resolve_live_video("@google", fetch_of(OFFLINE)) is None
    assert resolve_live_video("@x", fetch_of(UPCOMING)) is None


def test_resolver_never_raises_and_rejects_garbage():
    def boom(url):
        raise OSError("down")

    assert resolve_live_video("@x", boom) is None
    assert resolve_live_video("@x", fetch_of(LIVE, status=404)) is None
    assert resolve_live_video("@x", fetch_of("<html>garbage")) is None
    assert resolve_live_video("@x", fetch_of("")) is None


def test_resolver_builds_url_for_handle_and_channel_id():
    seen = []
    resolve_live_video("@LofiGirl", lambda u: seen.append(u) or (200, u, ""))
    resolve_live_video("UC" + "a" * 22, lambda u: seen.append(u) or (200, u, ""))
    assert seen == ["https://www.youtube.com/@LofiGirl/live", "https://www.youtube.com/channel/UC" + "a" * 22 + "/live"]


def test_video_id_wins_over_channel(monkeypatch):
    called = []
    monkeypatch.setattr(youtube, "run_with_backoff", lambda *a, **k: None)
    youtube.run_youtube("abcdefghijk", lambda m: None, threading.Event(), lambda s: None,
                        channel="@x", resolver=lambda c: called.append(c))
    assert called == []


def test_waits_for_live_without_failing(monkeypatch):
    answers = iter([None, None, None, "abcdefghijk"])
    statuses, sessions = [], []
    stop = threading.Event()

    def fake_backoff(fn, stop_, on_status, **kw):
        sessions.append(1)
        on_status("connected")
        stop_.set()  # end after the first session

    monkeypatch.setattr(youtube, "run_with_backoff", fake_backoff)
    youtube.run_youtube("", lambda m: None, stop, statuses.append,
                        channel="@x", resolver=lambda c: next(answers), poll_seconds=0.01)
    assert statuses[0] == "waiting for live" and "failed" not in statuses
    assert statuses[-1] == "connected" and sessions == [1]


def test_waiting_stops_promptly():
    stop = threading.Event()
    t = threading.Thread(target=youtube.run_youtube, args=("", lambda m: None, stop, lambda s: None),
                         kwargs={"channel": "@x", "resolver": lambda c: None, "poll_seconds": 30}, daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join(1)
    assert not t.is_alive()


def test_returns_to_waiting_after_stream_ends(monkeypatch):
    calls = []
    stop = threading.Event()

    def resolver(c):
        calls.append(c)
        if len(calls) == 2:
            stop.set()
        return "abcdefghijk"

    monkeypatch.setattr(youtube, "run_with_backoff", lambda *a, **k: None)  # stream ends at once
    youtube.run_youtube("", lambda m: None, stop, lambda s: None, channel="@x", resolver=resolver, poll_seconds=0.01)
    assert len(calls) == 2
