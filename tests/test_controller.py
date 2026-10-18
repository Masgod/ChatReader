import threading
from dataclasses import replace

from chatreader.config import Config
from chatreader.controller import Controller
from chatreader.filters import FilterState
from chatreader.models import Msg

WAIT = 2.0


class FakePlayer:
    def __init__(self):
        self.submitted = []
        self.calls = []

    def submit(self, text, lang):
        self.submitted.append((text, lang))

    def set_maxsize(self, n):
        self.calls.append(("maxsize", n))

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")

    def skip(self):
        self.calls.append("skip")

    def shutdown(self):
        self.calls.append("shutdown")

    def start(self):
        self.calls.append("start")


class FakeTTS:
    def __init__(self):
        self.reloaded = []

    def reload(self, cfg):
        self.reloaded.append(cfg)


class FakeSource:
    """Factory double: records starts, blocks until its stop_event is set."""

    def __init__(self):
        self.started = []  # values
        self.stopped = []  # values whose stop_event got set
        self.started_evt = threading.Event()
        self.on_status = None

    def __call__(self, value, on_msg, stop_event, on_status):
        self.started.append(value)
        self.on_status = on_status
        self.started_evt.set()
        on_status("connected")
        stop_event.wait()
        self.stopped.append(value)


def make(cfg=None):
    cfg = cfg or Config(twitch_channel="chan", youtube_video_id="")
    player, tts = FakePlayer(), FakeTTS()
    tw, yt = FakeSource(), FakeSource()
    c = Controller(cfg, player, tts, {"twitch": tw, "youtube": yt})
    return c, player, tts, tw, yt


def test_on_msg_pipeline():
    c, player, *_ = make()
    c.on_msg(Msg("twitch", "alice", "eu gostei muito dessa jogada", 0.0))
    assert player.submitted == [("alice disse: eu gostei muito dessa jogada", "pt")]


def test_filtered_message_not_submitted():
    c, player, *_ = make()
    c.on_msg(Msg("twitch", "nightbot", "hello everyone there", 0.0))
    c.on_msg(Msg("twitch", "bob", "!command", 0.0))
    assert player.submitted == []


def test_apply_config_restarts_only_changed_source():
    cfg = Config(twitch_channel="chan", youtube_video_id="abcdefghijk")
    c, player, tts, tw, yt = make(cfg)
    c.start()
    try:
        assert tw.started_evt.wait(WAIT) and yt.started_evt.wait(WAIT)
        tw.started_evt.clear()
        c.apply_config(replace(cfg, twitch_channel="other", queue_size=5))
        assert tw.started_evt.wait(WAIT)
        assert tw.started == ["chan", "other"]
        assert tw.stopped == ["chan"]
        assert yt.started == ["abcdefghijk"] and yt.stopped == []
        assert tts.reloaded and ("maxsize", 5) in player.calls
    finally:
        c.shutdown()


def test_apply_config_empty_channel_stops_source():
    c, _, _, tw, yt = make()
    c.start()
    try:
        assert tw.started_evt.wait(WAIT)
        c.apply_config(replace(c.cfg, twitch_channel=""))
        assert tw.stopped == ["chan"]
        assert tw.started == ["chan"]
        assert c.status()["twitch"] == "off"
        assert yt.started == []
    finally:
        c.shutdown()


def test_announce_toggle_applies_live():
    c, player, *_ = make()
    c.apply_config(replace(c.cfg, announce_user=False))
    c.on_msg(Msg("twitch", "alice", "eu gostei muito dessa jogada", 0.0))
    assert player.submitted == [("eu gostei muito dessa jogada", "pt")]


def test_status_reports_source_states():
    c, *_ , tw, yt = make()
    assert c.status() == {"twitch": "off", "youtube": "off", "overlay": "n/a"}
    c.start()
    try:
        assert tw.started_evt.wait(WAIT)
        assert c.status()["twitch"] == "connected"
        assert c.status()["youtube"] == "off"
    finally:
        c.shutdown()


def test_overlay_status_from_output_connected():
    class Hub:
        connected = 2

    c, player, *_ = make()
    player._output = Hub()
    assert c.status()["overlay"] == "2"


def test_source_crash_does_not_propagate():
    boom = threading.Event()

    def bad(value, on_msg, stop_event, on_status):
        boom.set()
        raise RuntimeError("x")

    c = Controller(Config(twitch_channel="chan"), FakePlayer(), FakeTTS(), {"twitch": bad, "youtube": FakeSource()})
    c.start()
    assert boom.wait(WAIT)
    c.shutdown()


def test_pause_resume_skip_speak_test():
    c, player, *_ = make()
    c.pause(); c.resume(); c.skip()
    c.speak_test("hello there my friends")
    assert player.calls == ["pause", "resume", "skip"]
    assert player.submitted == [("hello there my friends", "en")]


def test_on_msg_exception_is_isolated():
    c, player, *_ = make()

    def flaky(text, lang):
        if "boom" in text:
            raise RuntimeError("x")
        player.submitted.append((text, lang))

    player.submit = flaky
    c.on_msg(Msg("twitch", "alice", "boom boom this fails", 0.0))
    c.on_msg(Msg("twitch", "bob", "this one works fine ok", 0.0))
    assert len(player.submitted) == 1 and "works" in player.submitted[0][0]


def test_slow_reload_does_not_block_on_msg():
    c, player, tts, *_ = make()
    entered, release = threading.Event(), threading.Event()
    tts.reload = lambda cfg: (entered.set(), release.wait(WAIT))
    t = threading.Thread(target=c.apply_config, args=(replace(c.cfg, announce_user=False),))
    t.start()
    try:
        assert entered.wait(WAIT)
        done = threading.Event()
        threading.Thread(
            target=lambda: (c.on_msg(Msg("twitch", "al", "eu gostei muito dessa jogada", 0.0)), done.set())
        ).start()
        assert done.wait(WAIT)
    finally:
        release.set()
        t.join(WAIT)


def test_raising_reload_still_swaps_and_restarts():
    c, player, tts, tw, yt = make()
    c.start()
    try:
        assert tw.started_evt.wait(WAIT)

        def bad(cfg):
            raise RuntimeError("disk")

        tts.reload = bad
        tw.started_evt.clear()
        new = replace(c.cfg, twitch_channel="other", queue_size=3)
        c.apply_config(new)
        assert c.cfg is new
        assert tw.started_evt.wait(WAIT) and tw.started == ["chan", "other"]
        assert ("maxsize", 3) in player.calls
    finally:
        c.shutdown()


def test_identical_config_does_not_restart():
    c, _, _, tw, _ = make()
    c.start()
    try:
        assert tw.started_evt.wait(WAIT)
        c.apply_config(replace(c.cfg))
        assert tw.started == ["chan"] and tw.stopped == []
    finally:
        c.shutdown()
