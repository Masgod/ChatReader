"""Wires sources -> filters -> language -> player, and applies config changes live."""
import logging
import threading
from typing import Callable

from chatreader.config import Config
from chatreader.filters import FilterState, apply
from chatreader.lang import detect_lang, spoken_text
from chatreader.models import Msg

log = logging.getLogger(__name__)

_SOURCE_VALUE = {"twitch": "twitch_channel", "youtube": "youtube_video_id"}
_JOIN_TIMEOUT = 1.0


class Controller:
    def __init__(self, cfg: Config, player, tts, source_factories: dict[str, Callable]):
        self.cfg = cfg
        self._player = player
        self._tts = tts
        self._factories = source_factories
        self._lock = threading.Lock()  # guards cfg, filter state and the running-source table
        self._filter_state = FilterState(size=cfg.repeat_window)
        self._running: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self._status = {name: "off" for name in _SOURCE_VALUE}

    def on_msg(self, msg: Msg) -> None:
        try:
            with self._lock:
                cfg = self.cfg
                msg = apply(msg, cfg, self._filter_state)
            if msg is None:
                return
            lang = detect_lang(msg.text, cfg.default_lang)
            self._player.submit(spoken_text(msg, lang, cfg.announce_user), lang)
        except Exception:
            log.exception("message dropped")

    def start(self) -> None:
        with self._lock:
            for name in _SOURCE_VALUE:
                if name not in self._running:  # a settings save may already have started it
                    self._start_source(name)

    def apply_config(self, new: Config) -> None:
        to_join = []
        with self._lock:
            old, self.cfg = self.cfg, new
            if new.repeat_window != old.repeat_window:
                self._filter_state = FilterState(size=new.repeat_window)
            for name, attr in _SOURCE_VALUE.items():
                if getattr(new, attr) != getattr(old, attr):
                    to_join.append(self._stop_source(name))
                    self._start_source(name)
        self._join(to_join)
        # Slow disk work stays outside the lock so on_msg is never blocked by a voice load.
        if (new.voice_pt, new.voice_en, new.speed) != (old.voice_pt, old.voice_en, old.speed):
            try:
                self._tts.reload(new)
            except Exception:
                log.exception("tts reload failed")
        if new.queue_size != old.queue_size:
            self._player.set_maxsize(new.queue_size)

    def status(self) -> dict[str, str]:
        out = getattr(getattr(self._player, "_output", None), "connected", None)
        return {**self._status, "overlay": "n/a" if out is None else str(out)}

    def snapshot(self) -> dict:
        """Full status for the web UI. Never raises: a failing part reports error/False/0."""

        def part(fn, fallback):
            try:
                return fn()
            except Exception:
                return fallback

        cfg = self.cfg
        sources = {
            name: {"configured": bool(getattr(cfg, attr)), "state": self._status[name]}
            for name, attr in _SOURCE_VALUE.items()
        }
        overlay = part(lambda: bool(getattr(getattr(self._player, "_output", None), "connected", False)), False)
        return {
            "sources": sources,
            "overlay": overlay,
            "model": part(lambda: self._tts.model_state, "error"),
            "voices": part(lambda: self._tts.voices_ok, {"pt": False, "en": False}),
            "queue": part(lambda: int(self._player.pending), 0),
            "paused": part(lambda: bool(self._player.paused), False),
        }

    @property
    def paused(self) -> bool:
        return bool(getattr(self._player, "paused", False))

    def pause(self) -> None:
        self._player.pause()

    def resume(self) -> None:
        self._player.resume()

    def skip(self) -> None:
        self._player.skip()

    def speak_test(self, text: str) -> None:
        lang = detect_lang(text, self.cfg.default_lang)
        self._player.submit(text, lang)

    def shutdown(self) -> None:
        with self._lock:
            threads = [self._stop_source(name) for name in list(self._running)]
        self._join(threads)
        self._player.shutdown()

    @staticmethod
    def _join(threads) -> None:
        for thread in threads:
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=_JOIN_TIMEOUT)

    # callers hold self._lock
    def _start_source(self, name: str) -> None:
        value = getattr(self.cfg, _SOURCE_VALUE[name])
        if not value:
            return
        stop = threading.Event()

        def on_status(text: str) -> None:
            if not stop.is_set():  # a replaced source must not overwrite the new one's status
                self._status[name] = text

        def run() -> None:
            try:
                self._factories[name](value, self.on_msg, stop, on_status)
            except Exception:
                log.exception("%s source crashed", name)
                on_status("error")

        thread = threading.Thread(target=run, name=f"chatreader-{name}", daemon=True)
        self._running[name] = (thread, stop)
        self._status[name] = "starting"
        thread.start()

    def _stop_source(self, name: str) -> threading.Thread | None:
        self._status[name] = "off"
        entry = self._running.pop(name, None)
        if entry is None:
            return None
        entry[1].set()
        return entry[0]
