import logging
import re
import urllib.request
from typing import Callable

log = logging.getLogger(__name__)

# A live channel's /live page has a watch?v= canonical link and "isLiveNow":true; an offline
# channel's canonical link is the channel URL. Verified 2026-10-19 (see the spike notes).
CANONICAL_RE = re.compile(r'rel="canonical" href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"')
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _fetch(url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Cookie": "CONSENT=YES+1", "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", "replace")


def resolve_live_video(channel: str, fetch: Callable[[str], tuple[int, str, str]] | None = None) -> str | None:
    """Return the current live video ID of a channel (@handle or UC... ID), or None. Never raises."""
    path = channel if channel.startswith("@") else f"channel/{channel}"
    try:
        status, _, body = (fetch or _fetch)(f"https://www.youtube.com/{path}/live")
        match = CANONICAL_RE.search(body)
        if status == 200 and match and '"isLiveNow":true' in body:
            return match.group(1)
    except Exception:
        log.debug("live lookup failed for %s", channel, exc_info=True)
    return None
