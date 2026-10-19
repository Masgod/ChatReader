"""Bounded message queue with one worker thread that synthesizes and plays speech."""
import collections
import concurrent.futures
import dataclasses
import logging
import re
import threading
from typing import Callable, Protocol

log = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """Split after . ! ? … so the first sentence can start playing sooner. Never returns an empty list."""
    parts = [p.strip() for p in _SENTENCE_END.split(text) if p.strip()]
    return parts if len(parts) > 1 else [text]


@dataclasses.dataclass(frozen=True)
class QueueItem:
    id: int
    text: str
    lang: str
    user: str
    voice: str = ""


class Output(Protocol):
    def play(self, wav: bytes) -> None:
        """Block until the clip finishes, times out or stop() is called."""

    def stop(self) -> None:
        """Interrupt the clip currently being played."""


class Player:
    def __init__(
        self,
        synth: Callable[[str, str], bytes],
        output: Output,
        maxsize: int,
        on_event: Callable[[QueueItem, str], None] | None = None,
    ):
        self._synth = synth
        self._output = output
        self._on_event = on_event
        # deque with maxlen silently drops the oldest item when a new one arrives at capacity.
        self._queue: collections.deque[QueueItem] = collections.deque(maxlen=maxsize)
        self._cond = threading.Condition()
        self._paused = False
        self._shutdown = False
        self._next_id = 0
        self._playing: QueueItem | None = None
        # Bumped by skip(); the worker compares it to the value captured when it popped an item.
        self._skip_gen = 0
        # One worker: at most one synthesis runs at a time, the next sentence prepares while one plays.
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="chatreader-synth")
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

    def submit(self, text: str, lang: str, user: str = "", voice: str = "") -> None:
        with self._cond:
            evicted = self._queue[0] if len(self._queue) == self._queue.maxlen else None
            self._next_id += 1
            self._queue.append(QueueItem(self._next_id, text, lang, user, voice))
            self._cond.notify_all()
        if evicted:
            self._emit([(evicted, "dropped")])

    def snapshot(self) -> dict:
        with self._cond:
            return {"playing": self._playing, "waiting": list(self._queue)}

    def remove(self, item_id: int) -> bool:
        """Remove a waiting item. The one playing is ended with skip(), not removed."""
        with self._cond:
            for i, item in enumerate(self._queue):
                if item.id == item_id:
                    del self._queue[i]
                    break
            else:
                return False
        self._emit([(item, "removed")])
        return True

    def clear(self) -> int:
        with self._cond:
            items = list(self._queue)
            self._queue.clear()
        self._emit([(i, "removed") for i in items])
        return len(items)

    def set_maxsize(self, n: int) -> None:
        n = max(1, n)
        with self._cond:
            # A deque's maxlen is read-only; rebuilding keeps the newest n items (drops oldest).
            items = list(self._queue)
            evicted = items[: max(0, len(items) - n)]
            self._queue = collections.deque(items, maxlen=n)
        self._emit([(i, "dropped") for i in evicted])

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
        self._pool.shutdown(wait=False, cancel_futures=True)
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def _emit(self, events: list[tuple[QueueItem, str]]) -> None:
        """Report outcomes outside the lock; a failing listener must not stop playback."""
        if not self._on_event:
            return
        for item, outcome in events:
            try:
                self._on_event(item, outcome)
            except Exception:
                log.exception("queue event listener failed")

    def _run(self) -> None:
        wait_connected = getattr(self._output, "wait_connected", None)
        while True:
            # Hold messages in the queue (not synthesized, not dropped) until an overlay is listening.
            while wait_connected and not wait_connected(0.5):
                if self._shutdown:
                    return
            with self._cond:
                while not self._shutdown and (self._paused or not self._queue):
                    self._cond.wait()
                if self._shutdown:
                    return
                item = self._queue.popleft()
                self._playing = item
                gen = self._skip_gen
            try:
                outcome = self._play_item(item, gen)
            finally:
                with self._cond:
                    self._playing = None
            if outcome is None:
                return  # shutdown
            self._emit([(item, outcome)])

    def _play_item(self, item: QueueItem, gen: int) -> str | None:
        """Play every sentence of an item. Returns played, failed or skipped; None on shutdown."""
        sentences = split_sentences(item.text)
        try:
            pending = self._pool.submit(self._synth_safe, sentences[0], item.lang, item.voice)
        except RuntimeError:
            return None  # pool already shut down
        any_audio = False
        for i in range(len(sentences)):
            try:
                wav = pending.result()
            except concurrent.futures.CancelledError:
                return None  # shutdown cancelled the queued synthesis
            with self._cond:
                # A skip or shutdown during synth must cancel this item before play() starts.
                if self._shutdown:
                    return None
                if self._skip_gen != gen:
                    return "skipped"
            try:
                nxt = self._pool.submit(self._synth_safe, sentences[i + 1], item.lang, item.voice) if i + 1 < len(sentences) else None
            except RuntimeError:
                return None  # shutdown while this sentence was synthesizing
            if wav is not None:
                any_audio = True
                try:
                    self._output.play(wav)
                except Exception:
                    log.exception("playback failed; skipping sentence")
            pending = nxt
        with self._cond:
            if self._shutdown:
                return None
            if self._skip_gen != gen:
                return "skipped"
        return "played" if any_audio else "failed"

    def _synth_safe(self, text: str, lang: str, voice: str = "") -> bytes | None:
        try:
            return self._synth(text, lang, voice)
        except Exception:
            log.exception("synthesis failed; skipping sentence")
            return None
