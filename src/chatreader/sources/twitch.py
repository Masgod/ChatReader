import random
import threading
import time
from typing import Callable

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from chatreader.models import Msg
from chatreader.sources.common import run_with_backoff

URL = "wss://irc-ws.chat.twitch.tv:443"


def parse_privmsg(line: str) -> Msg | None:
    line = line.rstrip("\r\n")
    tags: dict[str, str] = {}
    if line.startswith("@"):
        tag_str, _, line = line.partition(" ")
        tags = dict(t.split("=", 1) for t in tag_str[1:].split(";") if "=" in t)
    if not line.startswith(":"):
        return None
    prefix, _, cmd = line.partition(" ")
    if not cmd.startswith("PRIVMSG "):
        return None
    _, sep, text = cmd.partition(" :")
    if not sep:
        return None
    nick = prefix[1:].split("!", 1)[0]
    return Msg("twitch", tags.get("display-name") or nick, text, time.time())


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
            ws.send("CAP REQ :twitch.tv/tags")
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
                    msg = parse_privmsg(line)
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
