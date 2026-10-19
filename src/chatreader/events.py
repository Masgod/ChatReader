"""In-memory event feed for the console: chat outcomes and app log lines. Never persisted."""
import collections
import logging
import threading
import time

_LEVELS = {logging.DEBUG: "debug", logging.INFO: "info", logging.WARNING: "warn"}


class EventLog:
    def __init__(self, capacity: int = 500):
        self._events: collections.deque[dict] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._last = 0

    def add(self, kind: str, level: str, **fields) -> int:
        with self._lock:
            self._last += 1
            self._events.append({"id": self._last, "ts": time.time(), "kind": kind, "level": level, **fields})
            return self._last

    def since(self, n: int = 0) -> dict:
        with self._lock:
            return {"events": [e for e in self._events if e["id"] > n], "last": self._last}

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class LogMirror(logging.Handler):
    """Copies log records into an EventLog. Never raises and never logs itself."""

    def __init__(self, events: EventLog):
        super().__init__()
        self._events = events

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = "error" if record.levelno >= logging.ERROR else _LEVELS.get(record.levelno, "info")
            self._events.add("app", level, message=record.getMessage(), logger=record.name)
        except Exception:
            pass
