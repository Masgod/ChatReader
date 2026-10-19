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
        self.paused = False
        self.pending = 0

    def submit(self, text, lang):
        self.submitted.append((text, lang))

    def set_maxsize(self, n):
        self.calls.append(("maxsize", n))

    def pause(self):
        self.calls.append("pause")
        self.paused = True

    def resume(self):
        self.calls.append("resume")
        self.paused = False

    def skip(self):
        self.calls.append("skip")

    def shutdown(self):
        self.calls.append("shutdown")

    def start(self):
        self.calls.append("start")


class FakeTTS:
    def __init__(self):
        self.reloaded = []
        self.model_state = "ready"
        self.voices_ok = {"pt": True, "en": True}

    def reload(self, cfg):
        self.reloaded.append(cfg)


def test_snapshot_shape_and_values():
    c, player, tts, tw, yt = make()
    c.start()
    try:
        assert tw.started_evt.wait(WAIT)
        snap = c.snapshot()
        assert set(snap) == {"sources", "overlay", "model", "voices", "queue", "paused"}
        assert snap["sources"]["twitch"] == {"configured": True, "state": "connected"}
        assert snap["sources"]["youtube"]["configured"] is False
        assert snap["queue"] == 0 and snap["paused"] is False
        c.pause()
        assert c.snapshot()["paused"] is True
    finally:
        c.shutdown()


def test_snapshot_survives_failing_parts():
    c, player, tts, *_ = make()

    class Boom:
        @property
        def model_state(self):
            raise RuntimeError("x")

    c._tts = Boom()
    snap = c.snapshot()
    assert snap["model"] == "error" and snap["voices"] == {"pt": False, "en": False}


class FakeSource:
    """Factory double: records starts, blocks until its stop_event is set."""

    def __init__(self):
        self.started = []  # values
        self.stopped = []  # values whose stop_event got set
        self.started_evt = threading.Event()
        self.on_status = None

    def __call__(self, value, on_msg, stop_event, on_status, **kw):
        self.kw = kw
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
        c.apply_config(replace(cfg, twitch_channel="other", queue_size=5, voice_en="af_bella"))
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


def test_apply_config_reloads_only_on_voice_or_speed_change():
    c, player, tts, *_ = make()
    c.apply_config(replace(c.cfg, announce_user=False))
    assert tts.reloaded == []
    c.apply_config(replace(c.cfg, speed=1.2))
    assert len(tts.reloaded) == 1


def test_channel_only_starts_youtube_and_restarts_on_change():
    cfg = Config(twitch_channel="", youtube_video_id="", youtube_channel="@one")
    c, player, tts, tw, yt = make(cfg)
    c.start()
    try:
        assert yt.started_evt.wait(WAIT)
        assert yt.started == [""] and yt.kw == {"channel": "@one"}
        assert c.snapshot()["sources"]["youtube"]["configured"] is True
        yt.started_evt.clear()
        c.apply_config(replace(cfg, youtube_channel="@two"))
        assert yt.started_evt.wait(WAIT)
        assert yt.kw == {"channel": "@two"} and tw.started == []
    finally:
        c.shutdown()


def test_slow_reload_does_not_block_on_msg():
    c, player, tts, *_ = make()
    entered, release = threading.Event(), threading.Event()
    tts.reload = lambda cfg: (entered.set(), release.wait(WAIT))
    t = threading.Thread(target=c.apply_config, args=(replace(c.cfg, voice_en="af_bella"),))
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


def test_paused_property_reflects_player():
    p = FakePlayer()
    c = Controller(Config(), p, None, {})
    assert c.paused is False
    p.paused = True
    assert c.paused is True
