"""Bounded message queue with one worker thread that synthesizes and plays speech."""
import collections
import concurrent.futures
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

    def submit(self, text: str, lang: str) -> None:
        with self._cond:
            self._queue.append((text, lang))
            self._cond.notify_all()

    def set_maxsize(self, n: int) -> None:
        with self._cond:
            # A deque's maxlen is read-only; rebuilding keeps the newest n items (drops oldest).
            self._queue = collections.deque(self._queue, maxlen=max(1, n))

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
                text, lang = self._queue.popleft()
                gen = self._skip_gen
            sentences = split_sentences(text)
            try:
                pending = self._pool.submit(self._synth_safe, sentences[0], lang)
            except RuntimeError:
                return  # pool already shut down
            for i in range(len(sentences)):
                try:
                    wav = pending.result()
                except concurrent.futures.CancelledError:
                    return  # shutdown cancelled the queued synthesis
                try:
                    nxt = self._pool.submit(self._synth_safe, sentences[i + 1], lang) if i + 1 < len(sentences) else None
                except RuntimeError:
                    return  # shutdown while this sentence was synthesizing
                with self._cond:
                    # A skip or shutdown during synth must cancel this item before play() starts.
                    if self._shutdown:
                        return
                    if self._skip_gen != gen:
                        if nxt:
                            nxt.cancel()
                        break
                if wav is not None:
                    try:
                        self._output.play(wav)
                    except Exception:
                        log.exception("playback failed; skipping sentence")
                pending = nxt

    def _synth_safe(self, text: str, lang: str) -> bytes | None:
        try:
            return self._synth(text, lang)
        except Exception:
            log.exception("synthesis failed; skipping sentence")
            return None
