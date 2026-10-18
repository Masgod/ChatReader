import re
from collections import Counter, deque
from dataclasses import dataclass, field, replace

from chatreader.config import Config
from chatreader.models import Msg

LINK_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
CHAR_RUN_RE = re.compile(r"(.)\1{9}", re.DOTALL)


@dataclass
class FilterState:
    size: int
    recent: dict[str, deque[str]] = field(default_factory=dict)


def _is_spam(text: str) -> bool:
    if CHAR_RUN_RE.search(text):
        return True
    tokens = text.split()
    if len(tokens) < 4:
        return False
    top_count = Counter(tokens).most_common(1)[0][1]
    return top_count >= 0.6 * len(tokens)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    space = cut.rfind(" ")
    return (cut[:space] if space > 0 else cut).rstrip()


def apply(msg: Msg, cfg: Config, state: FilterState) -> Msg | None:
    text = msg.text.strip()
    ignored = {name.lower() for name in cfg.ignored_users}
    if msg.user.lower() in ignored or text.startswith("!"):
        return None
    if LINK_RE.search(text) or not any(c.isalnum() for c in text):
        return None
    history = state.recent.setdefault(msg.user, deque(maxlen=state.size))
    if text in history or _is_spam(text):
        return None
    history.append(text)
    return replace(msg, text=_truncate(text, cfg.max_chars))
