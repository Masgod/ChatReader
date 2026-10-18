"""Bounded message queue with one worker thread that synthesizes and plays speech."""
import collections
import logging
import threading
from typing import Callable, Protocol

log = logging.getLogger(__name__)


class Output(Protocol):
    def play(self, wav: bytes) -> None:
        """Block until the clip finishes, times out or stop() is called."""

    def stop(self) -> None:
        """Interrupt the clip currently being played."""


class Player:
    def __init__(self, synth: Callable[[str, str], bytes], output: Output, maxsize: int):
        self._synth = synth
        self._output = output
        # deque with maxlen silently drops the oldest item when a new one arrives at capacity.
        self._queue: collections.deque[tuple[str, str]] = collections.deque(maxlen=maxsize)
        self._cond = threading.Condition()
        self._paused = False
        self._shutdown = False
        # Bumped by skip(); the worker compares it to the value captured when it popped an item.
        self._skip_gen = 0
        self._thread = threading.Thread(target=self._run, name="chatreader-player", daemon=True)

    @property
    def paused(self) -> bool:
        with self._cond:
            return self._paused

    @property
    def pending(self) -> int:
        with self._cond:
            return len(self._queue)

    def start(self) -> None:
        self._thread.start()

    def submit(self, text: str, lang: str) -> None:
        with self._cond:
            self._queue.append((text, lang))
            self._cond.notify_all()

    def set_maxsize(self, n: int) -> None:
        with self._cond:
            # A deque's maxlen is read-only; rebuilding keeps the newest n items (drops oldest).
            self._queue = collections.deque(self._queue, maxlen=n)

    def pause(self) -> None:
        with self._cond:
            self._paused = True

    def resume(self) -> None:
        with self._cond:
            self._paused = False
            self._cond.notify_all()

    def skip(self) -> None:
        with self._cond:
            self._skip_gen += 1
        self._output.stop()

    def shutdown(self) -> None:
        with self._cond:
            self._shutdown = True
            self._cond.notify_all()
        self._output.stop()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._shutdown and (self._paused or not self._queue):
                    self._cond.wait()
                if self._shutdown:
                    return
                text, lang = self._queue.popleft()
                gen = self._skip_gen
            try:
                wav = self._synth(text, lang)
            except Exception:
                log.exception("synthesis failed; skipping message")
                continue
            with self._cond:
                # A skip or shutdown during synth must cancel this item before play() starts.
                if self._shutdown:
                    return
                if self._skip_gen != gen:
                    continue
            try:
                self._output.play(wav)
            except Exception:
                log.exception("playback failed; skipping message")
