from lingua import Language, LanguageDetectorBuilder

from chatreader.announce import event_text
from chatreader.models import Msg

# Built once at import: the lingua model load is slow.
_DETECTOR = LanguageDetectorBuilder.from_languages(Language.PORTUGUESE, Language.ENGLISH).build()
_CODES = {Language.PORTUGUESE: "pt", Language.ENGLISH: "en"}
_MIN_CONFIDENCE = 0.7
_MIN_LENGTH = 12  # shorter texts are too ambiguous for detection


def detect_lang(text: str, default: str) -> str:
    if len(text.strip()) < _MIN_LENGTH:
        return default
    language = _DETECTOR.detect_language_of(text)
    if language is None:
        return default
    if _DETECTOR.compute_language_confidence(text, language) < _MIN_CONFIDENCE:
        return default
    return _CODES[language]


def spoken_text(msg: Msg, lang: str, announce: bool) -> str:
    if msg.kind != "chat":
        return event_text(msg, lang)
    if not announce:
        return msg.text
    name = msg.user.replace("_", " ")
    verb = "disse" if lang == "pt" else "says"
    return f"{name} {verb}: {msg.text}"
