import functools
import logging
from pathlib import Path

from chatreader.announce import event_text
from chatreader.languages import LANGUAGES
from chatreader.models import Msg

log = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "data" / "lid.176.ftz"  # fastText language-ID model, CC BY-SA 3.0
_MIN_CONFIDENCE = 0.7  # share of the enabled languages' total probability
_MIN_LENGTH = 12  # shorter texts are too ambiguous for detection


@functools.cache
def _model():
    """The fastText model, loaded once on first use; None when it cannot be loaded."""
    try:
        import fasttext

        return fasttext.load_model(str(MODEL_PATH))
    except Exception:
        log.warning("language detector unavailable; using the default language", exc_info=True)
        return None


def detect_lang(text: str, enabled: list[str], default: str) -> str:
    if len(enabled) == 1:
        return enabled[0]
    text = " ".join(text.split())  # fastText rejects newlines
    if len(text) < _MIN_LENGTH or not any(c.isalpha() for c in text):
        return default
    model = _model()
    if model is None:
        return default
    labels, probs = model.predict(text, k=-1)
    scores = {label.removeprefix("__label__"): float(p) for label, p in zip(labels, probs)}
    scores = {code: scores.get(code, 0.0) for code in enabled}
    total = sum(scores.values())
    if total <= 0:
        return default
    best = max(scores, key=scores.get)
    return best if scores[best] / total >= _MIN_CONFIDENCE else default


def spoken_text(msg: Msg, lang: str, announce: bool) -> str:
    if msg.kind != "chat":
        return event_text(msg, lang)
    if not announce:
        return msg.text
    name = msg.user.replace("_", " ")
    return f"{name} {LANGUAGES[lang].says}: {msg.text}"
