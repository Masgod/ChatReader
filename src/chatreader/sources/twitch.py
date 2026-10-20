import random
import re
import threading
import time
from typing import Callable

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from chatreader.models import Msg
from chatreader.sources.common import run_with_backoff

URL = "wss://irc-ws.chat.twitch.tv:443"


_BADGE_ROLES = {"broadcaster": "owner", "moderator": "mod", "vip": "vip", "subscriber": "sub", "founder": "sub"}


def _roles(badges: str) -> frozenset[str]:
    names = (b.split("/", 1)[0] for b in badges.split(",") if b)
    return frozenset(_BADGE_ROLES[n] for n in names if n in _BADGE_ROLES)


def _split_tags(line: str) -> tuple[dict[str, str], str]:
    line = line.rstrip("\r\n")
    tags: dict[str, str] = {}
    if line.startswith("@"):
        tag_str, _, line = line.partition(" ")
        tags = dict(t.split("=", 1) for t in tag_str[1:].split(";") if "=" in t)
    return tags, line


CHEERMOTE_RE = re.compile(r"^[A-Za-z]+\d+$")


def parse_privmsg(line: str) -> Msg | None:
    tags, line = _split_tags(line)
    if not line.startswith(":"):
        return None
    prefix, _, cmd = line.partition(" ")
    if not cmd.startswith("PRIVMSG "):
        return None
    _, sep, text = cmd.partition(" :")
    if not sep:
        return None
    nick = prefix[1:].split("!", 1)[0]
    user, roles = tags.get("display-name") or nick, _roles(tags.get("badges", ""))
    if tags.get("bits", "").isdigit():
        text = " ".join(w for w in text.split() if not CHEERMOTE_RE.match(w))
        return Msg("twitch", user, text, time.time(), roles, "bits", tags["bits"])
    return Msg("twitch", user, text, time.time(), roles)


def parse_notice(line: str) -> Msg | None:
    """Subs, resubs, gifts and raids (USERNOTICE). Anything else, or a line without a name, gives None."""
    tags, line = _split_tags(line)
    _, _, rest = line.partition(" ")
    if not rest.startswith("USERNOTICE "):
        return None
    user = tags.get("display-name") or tags.get("login", "")
    _, _, text = rest.partition(" :")
    kind_id = tags.get("msg-id", "")
    if not user:
        return None
    if kind_id in ("sub", "resub"):
        kind, detail = "subs", tags.get("msg-param-cumulative-months", "") if kind_id == "resub" else ""
    elif kind_id == "submysterygift":
        kind, detail = "gifts", tags.get("msg-param-mass-gift-count", "1")
    elif kind_id == "subgift" and not tags.get("msg-param-community-gift-id"):
        kind, detail = "gifts", "1"  # gifts inside a mystery gift are counted by the mystery gift
    elif kind_id == "raid":
        kind, detail = "raids", tags.get("msg-param-viewerCount", "")
    else:
        return None
    return Msg("twitch", user, text, time.time(), kind=kind, detail=detail)


def _session(
    channel: str,
    on_msg: Callable[[Msg], None],
    stop: threading.Event,
    on_status: Callable[[str], None],
) -> bool:
    """One connection. Returns True if at least one message was delivered."""
    delivered = False
    try:
        with connect(URL) as ws:
            ws.send(f"NICK justinfan{random.randint(10000, 99999)}")
            ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
            ws.send(f"JOIN #{channel}")
            on_status("connected")
            while not stop.is_set():
                try:
                    frame = ws.recv(timeout=1)
                except TimeoutError:
                    continue
                for line in frame.split("\r\n"):
                    if line.startswith("PING"):
                        ws.send("PONG :tmi.twitch.tv")
                        continue
                    msg = parse_privmsg(line) or parse_notice(line)
                    if msg is not None:
                        delivered = True
                        on_msg(msg)
    except (ConnectionClosed, OSError):
        # Dropped connection: report what we got so the runner can decide on backoff.
        return delivered
    return delivered


def run_twitch(
    channel: str,
    on_msg: Callable[[Msg], None],
    stop: threading.Event,
    on_status: Callable[[str], None],
) -> None:
    channel = channel.lstrip("#").lower()
    run_with_backoff(
        lambda: _session(channel, on_msg, stop, on_status), stop, on_status
    )
