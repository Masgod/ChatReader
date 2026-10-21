"""Make chat emotes speakable: laughs become a spoken laugh, other emotes are dropped."""
import re

# Whole-word, case-insensitive. shortcut: fixed lists of the common ones, grow them from real chat.
_LAUGH_RE = re.compile(
    r"(?<!\w)(?:lul|lulw|omegalul|kekw|lmao|lmfao|(?:ha){2,}h?|(?:he){2,}h?|(?:rs){2,}|k{3,}|(?:kk)+k?)(?!\w)",
    re.IGNORECASE,
)
_EMOTE_RE = re.compile(
    r"(?<!\w)(?:kappa|kappapride|pogchamp|pog|poggers|pepega|pepehands|monkas|4head|kreygasm|"
    r"residentsleeper|biblethump|sadge|copium|cmonbruh|wutface|trihard|notlikethis|<3)(?!\w)"
    r"|:[\w-]+:",
    re.IGNORECASE,
)
_LAUGH = {"pt": "há há", "en": "ha ha"}


def speak_emotes(text: str, lang: str) -> str:
    text = _LAUGH_RE.sub(_LAUGH[lang], text)
    text = _EMOTE_RE.sub(" ", text)
    return " ".join(text.split())
