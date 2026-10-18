import threading
import time

from chatreader.player import Player

WAIT = 2.0


class FakeOutput:
    """Records played WAV payloads. play() blocks until stop() or a per-item release."""

    def __init__(self, fail_on=None):
        self.played = []
        self.started = threading.Event()
        self.played_event = threading.Event()
        self._stop = threading.Event()
        self.stop_calls = 0
        self.fail_on = fail_on
        self.block = False
        self._lock = threading.Lock()

    def play(self, wav: bytes) -> None:
        if self.fail_on is not None and wav == self.fail_on:
            raise RuntimeError("boom")
        # Non-latching: a stop() issued while idle is discarded when the next play starts.
        self._stop.clear()
        with self._lock:
            self.played.append(wav)
        blocking = self.block
        self.started.set()
        if blocking:
            self._stop.wait(10)  # long on purpose: only stop() should end it early
        self.played_event.set()

    def stop(self) -> None:
        # Idempotent and safe when idle.
        with self._lock:
            self.stop_calls += 1
        self._stop.set()


def synth(text: str, lang: str) -> bytes:
    return text.encode()


def wait_until(predicate, timeout=WAIT):
    event = threading.Event()
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return True
        event.wait(0.01)
    return predicate()


def test_plays_in_order():
    out = FakeOutput()
    player = Player(synth, out, maxsize=10)
    player.start()
    try:
        for t in ["a", "b", "c"]:
            player.submit(t, "en")
        assert wait_until(lambda: len(out.played) == 3)
        assert out.played == [b"a", b"b", b"c"]
    finally:
        player.shutdown()


def test_drops_oldest_when_full():
    out = FakeOutput()
    player = Player(synth, out, maxsize=3)
    player.pause()
    player.start()
    try:
        for t in ["1", "2", "3", "4", "5"]:
            player.submit(t, "en")
        assert player.pending == 3
        player.resume()
        assert wait_until(lambda: len(out.played) == 3)
        assert out.played == [b"3", b"4", b"5"]
    finally:
        player.shutdown()


def test_burst_of_100_keeps_cap_and_newest():
    out = FakeOutput()
    player = Player(synth, out, maxsize=20)
    player.pause()
    player.start()
    try:
        for i in range(100):
            player.submit(str(i), "en")
        assert player.pending == 20
        player.resume()
        assert wait_until(lambda: len(out.played) == 20)
        assert out.played[-1] == b"99"
    finally:
        player.shutdown()


def test_pause_holds_items():
    out = FakeOutput()
    player = Player(synth, out, maxsize=10)
    player.pause()
    player.start()
    try:
        assert player.paused is True
        player.submit("x", "en")
        assert not wait_until(lambda: len(out.played) > 0, timeout=0.2)
        assert player.pending == 1
        player.resume()
        assert player.paused is False
        assert wait_until(lambda: out.played == [b"x"])
    finally:
        player.shutdown()


def test_skip_calls_output_stop():
    out = FakeOutput()
    out.block = True
    player = Player(synth, out, maxsize=10)
    player.start()
    try:
        player.submit("first", "en")
        assert out.started.wait(WAIT)
        out.block = False  # only the first play blocks; "second" must not
        player.submit("second", "en")
        player.skip()
        assert out.stop_calls == 1
        assert wait_until(lambda: out.played == [b"first", b"second"])
    finally:
        out.block = False
        player.shutdown()


def test_synth_error_skips_message():
    def flaky(text, lang):
        if text == "bad":
            raise RuntimeError("synth failed")
        return text.encode()

    out = FakeOutput()
    player = Player(flaky, out, maxsize=10)
    player.start()
    try:
        player.submit("bad", "en")
        player.submit("good", "en")
        assert wait_until(lambda: out.played == [b"good"])
    finally:
        player.shutdown()


def gated_synth(entered, release):
    """Synth that signals when item "a" starts and holds it until release is set."""

    def synth(text, lang):
        if text == "a":
            entered.set()
            release.wait(WAIT)
        return text.encode()

    return synth


def test_skip_during_synth_does_not_play_that_item():
    entered, release = threading.Event(), threading.Event()
    out = FakeOutput()
    player = Player(gated_synth(entered, release), out, maxsize=10)
    player.start()
    try:
        player.submit("a", "en")
        assert entered.wait(WAIT)
        player.skip()
        release.set()
        player.submit("b", "en")
        # If "a" were played, the list could never equal [b].
        assert wait_until(lambda: out.played == [b"b"])
    finally:
        release.set()
        player.shutdown()


def test_skip_when_idle_does_not_cancel_next():
    out = FakeOutput()
    player = Player(synth, out, maxsize=10)
    player.start()
    try:
        player.skip()
        player.submit("x", "en")
        assert wait_until(lambda: out.played == [b"x"])
    finally:
        player.shutdown()


def test_shutdown_during_synth_does_not_play():
    entered, release = threading.Event(), threading.Event()
    out = FakeOutput()
    player = Player(gated_synth(entered, release), out, maxsize=10)
    player.start()
    try:
        player.submit("a", "en")
        assert entered.wait(WAIT)
        closer = threading.Thread(target=player.shutdown)
        closer.start()
        assert wait_until(lambda: player._shutdown)  # shutdown flag is set before synth returns
        release.set()
        closer.join(WAIT)
        assert not closer.is_alive()
        assert out.played == []
    finally:
        release.set()
        player.shutdown()


def test_shutdown_unblocks_play_and_joins_promptly():
    out = FakeOutput()
    out.block = True
    player = Player(synth, out, maxsize=10)
    player.start()
    player.submit("a", "en")
    assert out.started.wait(WAIT)
    t0 = time.monotonic()
    player.shutdown()
    elapsed = time.monotonic() - t0
    assert not player._thread.is_alive()
    assert elapsed < WAIT


def test_output_error_skips_message():
    out = FakeOutput(fail_on=b"bad")
    player = Player(synth, out, maxsize=10)
    player.start()
    try:
        player.submit("bad", "en")
        player.submit("good", "en")
        assert wait_until(lambda: out.played == [b"good"])
    finally:
        player.shutdown()
