import logging
import threading

from chatreader.events import EventLog, LogMirror


def test_ids_increase_and_since_slices():
    log = EventLog()
    for i in range(3):
        log.add("chat", "info", text=str(i))
    got = log.since(1)
    assert [e["id"] for e in got["events"]] == [2, 3] and got["last"] == 3
    assert log.since(3) == {"events": [], "last": 3}


def test_capacity_drops_oldest_and_old_cursor_returns_remaining():
    log = EventLog(capacity=3)
    for _ in range(5):
        log.add("chat", "info")
    assert [e["id"] for e in log.since(0)["events"]] == [3, 4, 5]
    assert [e["id"] for e in log.since(1)["events"]] == [3, 4, 5]
    assert log.since(0)["last"] == 5


def test_concurrent_writers():
    log = EventLog(capacity=2000)

    def work():
        for _ in range(250):
            log.add("chat", "info")

    threads = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    ids = [e["id"] for e in log.since(0)["events"]]
    assert len(set(ids)) == 1000 and log.since(0)["last"] == 1000


def test_event_has_fields():
    log = EventLog()
    log.add("chat", "info", user="a", text="hi", outcome="queued")
    e = log.since(0)["events"][0]
    assert (e["kind"], e["level"], e["user"], e["outcome"]) == ("chat", "info", "a", "queued") and e["ts"] > 0


def _logger(name, level):
    lg = logging.getLogger(name)
    lg.handlers.clear()
    lg.propagate = False
    lg.setLevel(level)
    return lg


def test_mirror_copies_records_with_levels():
    log = EventLog()
    lg = _logger("mirror.t1", logging.INFO)
    lg.addHandler(LogMirror(log))
    lg.debug("d")
    lg.info("i")
    lg.warning("w")
    lg.error("e")
    got = [(e["level"], e["message"], e["kind"]) for e in log.since(0)["events"]]
    assert got == [("info", "i", "app"), ("warn", "w", "app"), ("error", "e", "app")]
    lg.setLevel(logging.DEBUG)
    lg.debug("d2")
    assert log.since(0)["events"][-1]["level"] == "debug"


def test_mirror_swallows_errors():
    class Boom(EventLog):
        def add(self, *a, **k):
            raise RuntimeError("x")

    lg = _logger("mirror.t2", logging.INFO)
    lg.addHandler(LogMirror(Boom()))
    lg.error("still fine")
