import logging
import threading
import time
from typing import Callable

import pytchat

from chatreader.models import Msg
from chatreader.sources.common import run_with_backoff
from chatreader.sources.youtube_live import resolve_live_video

log = logging.getLogger(__name__)


def to_msg(item) -> Msg:
    return Msg("youtube", item.author.name, item.message or "", time.time())


def _session(
    video_id: str,
    on_msg: Callable[[Msg], None],
    stop: threading.Event,
    on_status: Callable[[str], None],
    chat_factory: Callable[..., object],
) -> bool:
    """One chat session. Returns True if at least one message was delivered."""
    delivered = False
    chat = chat_factory(video_id=video_id)
    try:
        on_status("connected")
        while chat.is_alive() and not stop.is_set():
            for item in chat.get().sync_items():
                delivered = True
                on_msg(to_msg(item))
            stop.wait(0.5)
    except Exception:
        # Keep `delivered` so the runner resets backoff after a mid-stream error.
        log.warning("youtube chat loop failed", exc_info=True)
    finally:
        # pytchat runs a background thread per chat; release it on every exit path.
        try:
            chat.terminate()
        except Exception:
            log.debug("youtube chat terminate failed", exc_info=True)
    return delivered


def _create_chat(**kw):
    # interruptable=True installs a SIGINT handler, which only works on the main thread.
    return pytchat.create(interruptable=False, **kw)


def run_youtube(
    video_id: str,
    on_msg: Callable[[Msg], None],
    stop: threading.Event,
    on_status: Callable[[str], None],
    chat_factory: Callable[..., object] = _create_chat,
    channel: str = "",
    resolver: Callable[[str], str | None] = resolve_live_video,
    poll_seconds: float = 30,
) -> None:
    """Read chat for video_id. With only a channel, wait for its live stream, and again after it ends."""
    follow_channel = not video_id and bool(channel)
    while not stop.is_set():
        if follow_channel:
            on_status("waiting for live")
            video_id = None
            while not video_id:
                video_id = resolver(channel)
                if video_id:
                    break
                if stop.wait(poll_seconds):
                    return
        run_with_backoff(
            lambda: _session(video_id, on_msg, stop, on_status, chat_factory),
            stop,
            on_status,
            max_failures=5,
        )
        if not follow_channel:
            return
