"""Spoken sentences for stream events (bits, subs, gifts, raids, Super Chat, members)."""
from chatreader.models import Msg

_PT = {
    "bits": lambda n: f"doou {n} bit" + ("" if n == "1" else "s"),
    "subs": lambda n: "se inscreveu" if not n else f"renovou a inscrição, {n} meses",
    "gifts": lambda n: f"deu {n} " + ("inscrição" if n == "1" else "inscrições"),
    "raids": lambda n: f"fez uma raid com {n} pessoas",
    "superchat": lambda n: f"enviou {n}",
    "members": lambda n: "virou membro",
}
_EN = {
    "bits": lambda n: f"cheered {n} bit" + ("" if n == "1" else "s"),
    "subs": lambda n: "subscribed" if not n else f"resubscribed for {n} months",
    "gifts": lambda n: f"gifted {n} sub" + ("" if n == "1" else "s"),
    "raids": lambda n: f"is raiding with {n} viewers",
    "superchat": lambda n: f"sent {n}",
    "members": lambda n: "became a member",
}


def event_text(msg: Msg, lang: str) -> str:
    phrase = (_PT if lang == "pt" else _EN)[msg.kind](msg.detail)
    base = f"{msg.user.replace('_', ' ')} {phrase}"
    return f"{base}: {msg.text}" if msg.text else base
