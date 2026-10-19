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


def explain(msg: Msg, cfg: Config, state: FilterState) -> str | None:
    """Why a message would be dropped, or None if it passes. Never records history."""
    text = msg.text.strip()
    if msg.user.lower() in {name.lower() for name in cfg.ignored_users}:
        return "ignored user"
    if text.startswith("!"):
        return "command"
    if LINK_RE.search(text):
        return "link"
    if not any(c.isalnum() for c in text):
        return "no text"
    if text in state.recent.get(msg.user, ()):
        return "repeat"
    if _is_spam(text):
        return "spam"
    return None


def apply(msg: Msg, cfg: Config, state: FilterState) -> Msg | None:
    if explain(msg, cfg, state):
        return None
    text = msg.text.strip()
    state.recent.setdefault(msg.user, deque(maxlen=state.size)).append(text)
    return replace(msg, text=_truncate(text, cfg.max_chars))
