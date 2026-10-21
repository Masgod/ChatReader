"""Wires sources -> filters -> language -> player, and applies config changes live."""
import logging
import threading
from dataclasses import replace
from typing import Callable

from chatreader.config import Config
from chatreader.emotes import speak_emotes, strip_emotes
from chatreader.filters import FilterState, apply, explain
from chatreader.lang import detect_lang, spoken_text
from chatreader.models import Msg
from chatreader.voices import voice_for

log = logging.getLogger(__name__)

_SOURCE_VALUE = {"twitch": "twitch_channel", "youtube": "youtube_video_id"}
_SOURCE_EXTRA = {"youtube": "youtube_channel"}  # extra setting that can start a source on its own
_JOIN_TIMEOUT = 1.0


class Controller:
    def __init__(self, cfg: Config, player, tts, source_factories: dict[str, Callable], events=None):
        self.cfg = cfg
        self._player = player
        self._tts = tts
        self._factories = source_factories
        self._events = events  # optional EventLog; chat outcomes are recorded when set
        self._lock = threading.Lock()  # guards cfg, filter state and the running-source table
        self._filter_state = FilterState(size=cfg.repeat_window)
        self._running: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self._status = {name: "off" for name in _SOURCE_VALUE}

    def on_msg(self, msg: Msg) -> None:
        try:
            with self._lock:
                cfg = self.cfg
                reason = explain(msg, cfg, self._filter_state)
                original = msg
                msg = apply(msg, cfg, self._filter_state)
            if msg is None:
                self._record(original.user, original.text, f"skipped:{reason}" if reason else "skipped")
                return
            # a message that is only laughs/emotes says nothing about its language
            lang = detect_lang(msg.text, cfg.languages, cfg.default_lang) if strip_emotes(msg.text) else cfg.default_lang
            voice = self._pick_voice(cfg, msg, lang)
            spoken = msg
            if cfg.speak_emotes and msg.kind == "chat":
                spoken = replace(msg, text=speak_emotes(msg.text, lang))
                if not spoken.text:
                    self._record(msg.user, msg.text, "skipped:emotes only")
                    return
            self._player.submit(spoken_text(spoken, lang, cfg.announce_user), lang, msg.user, voice)
            self._record(msg.user, msg.text, "queued")
        except Exception:
            log.exception("message dropped")

    def _pick_voice(self, cfg: Config, msg: Msg, lang: str) -> str:
        if not cfg.per_user_voices:
            return ""
        try:
            pool = [v["id"] for v in self._tts.voices()[lang]]
        except Exception:  # no voice list yet (model loading) or a TTS without one: use the default voice
            return ""
        return voice_for(msg.platform, msg.user, pool)

    def _record(self, user: str, text: str, outcome: str) -> None:
        if self._events is not None:
            self._events.add("chat", "info", user=user, text=text, outcome=outcome)

    def record_item_event(self, item, outcome: str) -> None:
        """Player callback: a queued item was played, failed, skipped, removed or dropped."""
        self._record(item.user, item.text, outcome)

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
            for name in _SOURCE_VALUE:
                if self._source_key(new, name) != self._source_key(old, name):
                    to_join.append(self._stop_source(name))
                    self._start_source(name)
        self._join(to_join)
        # Slow disk work stays outside the lock so on_msg is never blocked by a voice load.
        if (new.languages, new.voices(), new.speed) != (old.languages, old.voices(), old.speed):
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
            name: {"configured": any(self._source_key(cfg, name)), "state": self._status[name]}
            for name in _SOURCE_VALUE
        }
        overlay = part(lambda: bool(getattr(getattr(self._player, "_output", None), "connected", False)), False)
        return {
            "sources": sources,
            "overlay": overlay,
            "model": part(lambda: self._tts.model_state, "error"),
            "voices": part(lambda: self._tts.voices_ok, {c: False for c in cfg.languages}),
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

    def speak_test(self, text: str, lang: str = "") -> None:
        if lang not in self.cfg.languages:  # unknown or not yet saved: guess from the text
            lang = detect_lang(text, self.cfg.languages, self.cfg.default_lang)
        self._player.submit(text, lang, "test")

    def shutdown(self) -> None:
        with self._lock:
            threads = [self._stop_source(name) for name in list(self._running)]
        self._join(threads)
        self._player.shutdown()

    @staticmethod
    def _source_key(cfg: Config, name: str) -> tuple[str, str]:
        extra = getattr(cfg, _SOURCE_EXTRA[name]) if name in _SOURCE_EXTRA else ""
        return getattr(cfg, _SOURCE_VALUE[name]), extra

    @staticmethod
    def _join(threads) -> None:
        for thread in threads:
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=_JOIN_TIMEOUT)

    # callers hold self._lock
    def _start_source(self, name: str) -> None:
        value, extra = self._source_key(self.cfg, name)
        if not (value or extra):
            return
        kwargs = {"channel": extra} if name in _SOURCE_EXTRA else {}
        stop = threading.Event()

        def on_status(text: str) -> None:
            if not stop.is_set():  # a replaced source must not overwrite the new one's status
                self._status[name] = text

        def run() -> None:
            try:
                self._factories[name](value, self.on_msg, stop, on_status, **kwargs)
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
