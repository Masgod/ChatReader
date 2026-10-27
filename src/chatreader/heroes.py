"""Per-viewer hero re-rolls (`!random`): saved slots plus escalating waits."""
import json
import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Callable

from chatreader.config import Config
from chatreader.voices import slot_for

log = logging.getLogger(__name__)

WINDOW = 60.0  # seconds of quiet after a wait ends before the streak starts over
_MAX_DOUBLINGS = 30


class _Cooldown:
    def __init__(self) -> None:
        self.until = 0.0
        self.streak = 0

    def ready(self, now: float) -> bool:
        return now >= self.until

    def hit(self, now: float, base: float, cap: float) -> None:
        if now > self.until + WINDOW:
            self.streak = 0
        self.streak += 1
        self.until = now + min(base * 2 ** min(self.streak - 1, _MAX_DOUBLINGS), cap)


class HeroPicker:
    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic, rng: Callable[[int], int] = random.getrandbits):
        self._path = path
        self._clock = clock
        self._rng = rng
        self._lock = threading.Lock()
        self._global = _Cooldown()
        self._viewers: dict[str, _Cooldown] = {}  # shortcut: never pruned (tens of bytes per viewer), upgrade if memory ever matters
        self._slots = self._load()

    def slot(self, platform: str, user: str) -> int:
        return self._slots.get(self._key(platform, user), slot_for(platform, user))

    def reroll(self, platform: str, user: str, cfg: Config) -> int | None:
        """A new slot for the viewer, or None while a wait (theirs or the chat's) is still running."""
        key = self._key(platform, user)
        with self._lock:
            now = self._clock()
            mine = self._viewers.setdefault(key, _Cooldown())
            if not (mine.ready(now) and self._global.ready(now)):
                return None
            mine.hit(now, cfg.random_cooldown_base, cfg.random_cooldown_max)
            self._global.hit(now, cfg.random_global_base, cfg.random_global_max)
            old = self.slot(platform, user)
            new = old
            while new == old:
                new = self._rng(32)
            self._slots[key] = new
            self._save()
            return new

    @staticmethod
    def _key(platform: str, user: str) -> str:
        return f"{platform}:{user.lower()}"

    def _load(self) -> dict[str, int]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return {k: v for k, v in data.items() if isinstance(v, int)}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, AttributeError):
            log.warning("%s is unreadable, starting with no saved heroes", self._path)
            return {}

    def _save(self) -> None:
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(self._slots), encoding="utf-8")
            os.replace(tmp, self._path)  # the old file stays intact if we die mid-write
        except OSError:
            log.exception("could not save %s", self._path)
