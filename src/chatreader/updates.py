"""Tell the user when a newer release exists.

This is the app's only call home: one GET to the GitHub releases API, nothing is sent except a generic User-Agent.
Every failure is silent (debug log), so no network or a rate limit never disturbs the app.
"""
import json
import logging
import re
import threading
import time
import urllib.request
from collections.abc import Callable

API_URL = "https://api.github.com/repos/Masgod/ChatReader/releases/latest"
RELEASES_URL = "https://github.com/Masgod/ChatReader/releases"
DAY = 24 * 3600
_VERSION_RE = re.compile(r"v?(\d+(?:\.\d+){0,2})")
log = logging.getLogger("chatreader")


def parse_version(tag) -> tuple[int, ...] | None:
    """'v0.10.0' -> (0, 10, 0), so versions compare as numbers. Anything else (rc, nightly) is None."""
    m = _VERSION_RE.fullmatch(tag) if isinstance(tag, str) else None
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def fetch_latest(current: str) -> dict:
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": f"ChatReader/{current}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read(1 << 20))


def latest_release(fetch: Callable[[], dict]) -> dict | None:
    """{"version", "url"} of the newest published release, or None on any error, draft, pre-release or odd tag."""
    try:
        data = fetch()
    except Exception as e:  # 403 rate limit, offline, bad JSON: all the same to the user
        log.debug("update check failed: %s", e)
        return None
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease") or parse_version(data.get("tag_name")) is None:
        return None
    url = data.get("html_url")
    return {"version": data["tag_name"].removeprefix("v"), "url": url if isinstance(url, str) and url.startswith(RELEASES_URL + "/") else RELEASES_URL}


class UpdateChecker:
    def __init__(self, current: str, fetch: Callable[[], dict] | None = None, notify: Callable[[dict], None] = lambda r: None,
                 sleep: Callable[[float], None] = time.sleep, enabled: Callable[[], bool] = lambda: True):
        self._current = parse_version(current) or (0,)
        self._fetch = fetch or (lambda: fetch_latest(current))
        self._notify, self._sleep, self._enabled = notify, sleep, enabled
        self._announced = ""
        self.available: dict | None = None

    def check(self) -> None:
        if not self._enabled():
            return
        rel = latest_release(self._fetch)
        if not rel or parse_version(rel["version"]) <= self._current:
            return
        self.available = rel
        if rel["version"] != self._announced:  # once per version per run, not once a day
            self._announced = rel["version"]
            try:
                self._notify(rel)
            except Exception:
                log.debug("update notification failed", exc_info=True)

    def loop(self) -> None:
        while True:
            self.check()
            self._sleep(DAY)

    def start(self) -> None:
        threading.Thread(target=self.loop, daemon=True, name="update-check").start()
