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


def test_set_maxsize_drops_oldest_when_shrinking():
    player = Player(synth, FakeOutput(), maxsize=5)  # not started: items stay queued
    for t in "abcde":
        player.submit(t, "en")
    player.set_maxsize(2)
    assert player.pending == 2
    assert [(i.text, i.lang) for i in player._queue] == [("d", "en"), ("e", "en")]
    player.submit("f", "en")
    assert [(i.text, i.lang) for i in player._queue] == [("e", "en"), ("f", "en")]
    player.set_maxsize(4)
    for t in "ghi":
        player.submit(t, "en")
    assert player.pending == 4


def test_set_maxsize_clamps_to_one():
    player = Player(synth, FakeOutput(), maxsize=3)
    player.submit("a", "en")
    player.submit("b", "en")
    player.set_maxsize(0)
    assert [(i.text, i.lang) for i in player._queue] == [("b", "en")]


def test_split_sentences_cases():
    from chatreader.player import split_sentences

    assert split_sentences("Oi. Tudo bem? Sim!") == ["Oi.", "Tudo bem?", "Sim!"]
    assert split_sentences("sem pontuacao") == ["sem pontuacao"]
    assert split_sentences("...") == ["..."]
    assert split_sentences("?!") == ["?!"]
    assert split_sentences("  ") == ["  "]
    assert split_sentences("a" * 500) == ["a" * 500]


def test_message_plays_sentences_in_order():
    out = FakeOutput()
    player = Player(synth, out, maxsize=10)
    player.start()
    try:
        player.submit("A. B. C.", "pt")
        assert wait_until(lambda: len(out.played) == 3)
        assert out.played == [b"A.", b"B.", b"C."]
    finally:
        player.shutdown()


def test_next_sentence_synth_overlaps_playback():
    out = FakeOutput()
    out.block = True
    log, inflight, peak = [], [0], [0]
    lock = threading.Lock()

    def slow_synth(text, lang):
        with lock:
            inflight[0] += 1
            peak[0] = max(peak[0], inflight[0])
            log.append(text)
        time.sleep(0.05)
        with lock:
            inflight[0] -= 1
        return text.encode()

    player = Player(slow_synth, out, maxsize=10)
    player.start()
    try:
        player.submit("A. B. C.", "pt")
        assert out.started.wait(WAIT)  # sentence 1 is playing (blocked)
        assert wait_until(lambda: "B." in log)  # sentence 2 synthesizes meanwhile
        assert out.played == [b"A."]
        assert peak[0] == 1
    finally:
        player.shutdown()


def test_skip_drops_remaining_sentences():
    out = FakeOutput()
    out.block = True
    player = Player(synth, out, maxsize=10)
    player.start()
    try:
        player.submit("A. B. C.", "pt")
        assert out.started.wait(WAIT)
        out.block = False
        player.skip()
        player.submit("next", "pt")
        assert wait_until(lambda: b"next" in out.played)
        assert b"B." not in out.played and b"C." not in out.played
    finally:
        player.shutdown()


def test_shutdown_during_prefetch_exits_cleanly():
    out = FakeOutput()
    out.block = True
    gate = threading.Event()

    def gated(text, lang):
        if text == "B.":
            gate.wait(5)
        return text.encode()

    player = Player(gated, out, maxsize=10)
    player.start()
    player.submit("A. B.", "pt")
    assert out.started.wait(WAIT)
    start = time.monotonic()
    gate.set()
    player.shutdown()
    assert time.monotonic() - start < 3


def test_failed_later_sentence_skips_only_it():
    out = FakeOutput()

    def flaky(text, lang):
        if text == "B.":
            raise RuntimeError("boom")
        return text.encode()

    player = Player(flaky, out, maxsize=10)
    player.start()
    try:
        player.submit("A. B. C.", "pt")
        assert wait_until(lambda: len(out.played) == 2)
        assert out.played == [b"A.", b"C."]
    finally:
        player.shutdown()


def _ev_player(out=None, synth_fn=synth, maxsize=10):
    events, lock = [], threading.Lock()

    def on_event(item, outcome):
        with lock:
            events.append((item.id, outcome))

    out = out or FakeOutput()
    return Player(synth_fn, out, maxsize=maxsize, on_event=on_event), out, events


def test_submit_assigns_unique_ids_and_snapshot_orders_waiting():
    player, out, events = _ev_player()
    player.pause()
    player.submit("a", "pt", "u1")
    player.submit("b", "pt", "u2")
    player.submit("c", "en", "u3")
    snap = player.snapshot()
    assert snap["playing"] is None
    assert [i.text for i in snap["waiting"]] == ["a", "b", "c"]
    assert [i.user for i in snap["waiting"]] == ["u1", "u2", "u3"]
    ids = [i.id for i in snap["waiting"]]
    assert ids == sorted(set(ids))


def test_snapshot_reports_playing_item():
    player, out, events = _ev_player()
    out.block = True
    player.start()
    try:
        player.submit("a", "pt", "u1")
        assert out.started.wait(WAIT)
        snap = player.snapshot()
        assert snap["playing"].text == "a" and snap["waiting"] == []
        out.block = False
        player.skip()
        assert wait_until(lambda: player.snapshot()["playing"] is None)
    finally:
        player.shutdown()


def test_remove_waiting_unknown_and_playing():
    player, out, events = _ev_player()
    out.block = True
    player.start()
    try:
        player.submit("playing", "pt")
        assert out.started.wait(WAIT)
        player.submit("waiting", "pt")
        playing_id = player.snapshot()["playing"].id
        waiting_id = player.snapshot()["waiting"][0].id
        assert player.remove(9999) is False
        assert player.remove(playing_id) is False
        assert player.remove(waiting_id) is True
        assert (waiting_id, "removed") in events
        out.block = False
        player.skip()
        assert wait_until(lambda: player.pending == 0)
        assert b"waiting" not in out.played
    finally:
        player.shutdown()


def test_clear_returns_count_and_emits_removed():
    player, out, events = _ev_player()
    player.pause()
    for t in "abc":
        player.submit(t, "pt")
    assert player.clear() == 3
    assert [o for _, o in events] == ["removed"] * 3 and player.pending == 0


def test_full_queue_emits_dropped_with_evicted_item():
    player, out, events = _ev_player(maxsize=2)
    player.pause()
    player.submit("a", "pt")
    first_id = player.snapshot()["waiting"][0].id
    player.submit("b", "pt")
    player.submit("c", "pt")
    assert events == [(first_id, "dropped")]


def test_played_failed_skipped_outcomes():
    player, out, events = _ev_player()
    player.start()
    try:
        player.submit("fine", "pt")
        assert wait_until(lambda: any(o == "played" for _, o in events))
    finally:
        player.shutdown()

    def bad(text, lang):
        raise RuntimeError("boom")

    player, out, events = _ev_player(synth_fn=bad)
    player.start()
    try:
        player.submit("x", "pt")
        assert wait_until(lambda: any(o == "failed" for _, o in events))
        assert not any(o == "played" for _, o in events)
    finally:
        player.shutdown()

    player, out, events = _ev_player()
    out.block = True
    player.start()
    try:
        player.submit("s", "pt")
        assert out.started.wait(WAIT)
        player.skip()
        assert wait_until(lambda: any(o == "skipped" for _, o in events))
        assert not any(o == "played" for _, o in events)
    finally:
        player.shutdown()


def test_remove_races_with_worker():
    out = FakeOutput()

    def slow(text, lang):
        time.sleep(0.002)
        return text.encode()

    player, out, events = _ev_player(out=out, synth_fn=slow, maxsize=100)
    player.start()
    try:
        for i in range(40):
            player.submit(f"m{i}", "pt")
        ids = [i.id for i in player.snapshot()["waiting"]]
        removed = [i for i in ids if player.remove(i)]
        assert wait_until(lambda: player.pending == 0 and player.snapshot()["playing"] is None, 5)
        time.sleep(0.1)
        by_id = {}
        for i, o in events:
            by_id.setdefault(i, []).append(o)
        for i in removed:
            assert by_id[i] == ["removed"]
        for i, outs in by_id.items():
            assert len(outs) == 1, (i, outs)
    finally:
        player.shutdown()


def test_on_event_exception_is_ignored():
    out = FakeOutput()

    def boom(item, outcome):
        raise RuntimeError("x")

    player = Player(synth, out, maxsize=10, on_event=boom)
    player.start()
    try:
        player.submit("a", "pt")
        player.submit("b", "pt")
        assert wait_until(lambda: len(out.played) == 2)
    finally:
        player.shutdown()


def test_shutdown_during_last_sentence_is_not_reported_played():
    out = FakeOutput()
    out.block = True
    player, out, events = _ev_player(out)
    player.start()
    player.submit("hello", "en")
    assert out.started.wait(WAIT)
    player.shutdown()
    assert (1, "played") not in events
