"""Spoken sentences for stream events (bits, subs, gifts, raids, Super Chat, members)."""
from chatreader.languages import LANGUAGES
from chatreader.models import Msg


def event_text(msg: Msg, lang: str) -> str:
    phrase = LANGUAGES[lang].events[msg.kind](msg.detail)
    base = f"{msg.user.replace('_', ' ')} {phrase}"
    return f"{base}: {msg.text}" if msg.text else base
