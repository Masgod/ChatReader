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
    seen: dict[str, float] = field(default_factory=dict)  # normalized text -> time last accepted


def _is_spam(text: str) -> bool:
    if CHAR_RUN_RE.search(text):
        return True
    tokens = text.split()
    if len(tokens) < 4:
        return False
    top_count = Counter(tokens).most_common(1)[0][1]
    return top_count >= 0.6 * len(tokens)


SEEN_CAP = 200


def _key(text: str) -> str:
    return " ".join(text.casefold().split())


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
    if msg.kind != "chat":  # donations skip the chat rules: whoever paid is read
        if msg.kind not in cfg.event_kinds:
            return "event off"
        if msg.kind == "bits" and msg.detail.isdigit() and int(msg.detail) < cfg.min_bits:
            return "min bits"
        return None
    allowed = getattr(cfg, f"{msg.platform}_roles", [])
    if allowed and "owner" not in msg.roles and not msg.roles.intersection(allowed):
        return "role"
    if text.startswith("!"):
        return "command"
    if LINK_RE.search(text):
        return "link"
    if not any(c.isalnum() for c in text):
        return "no text"
    if text in state.recent.get(msg.user, ()):
        return "repeat"
    if cfg.repeat_seconds > 0:
        last = state.seen.get(_key(text))
        if last is not None and msg.ts - last <= cfg.repeat_seconds:
            return "duplicate"
    if _is_spam(text):
        return "spam"
    return None


def apply(msg: Msg, cfg: Config, state: FilterState) -> Msg | None:
    if explain(msg, cfg, state):
        return None
    text = msg.text.strip()
    if msg.kind != "chat":  # the announcement is always read; a bad attached message is left out
        bad = text.startswith("!") or LINK_RE.search(text) or not any(c.isalnum() for c in text) or _is_spam(text)
        return replace(msg, text="" if bad else _truncate(text, cfg.max_chars))
    state.recent.setdefault(msg.user, deque(maxlen=state.size)).append(text)
    state.seen[_key(text)] = msg.ts
    for k in [k for k, t in state.seen.items() if msg.ts - t > cfg.repeat_seconds]:
        del state.seen[k]
    while len(state.seen) > SEEN_CAP:
        del state.seen[next(iter(state.seen))]
    return replace(msg, text=_truncate(text, cfg.max_chars))
