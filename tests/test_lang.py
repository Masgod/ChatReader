import pytest

from chatreader import lang
from chatreader.lang import detect_lang, spoken_text
from chatreader.models import Msg

ALL = ["pt", "en", "es", "fr", "it"]


@pytest.mark.parametrize("code,text", [
    ("pt", "eu gostei muito dessa jogada, muito boa"),
    ("en", "that was an amazing play, well done"),
    ("es", "me gustó mucho esa jugada, muy buena"),
    ("fr", "j'ai beaucoup aimé cette action, très bien"),
    ("it", "mi è piaciuta molto questa giocata, bravo"),
])
def test_detects_each_language(code, text):
    assert detect_lang(text, ALL, "pt" if code != "pt" else "en") == code


def test_only_enabled_languages_are_returned():
    assert detect_lang("me gustó mucho esa jugada, muy buena", ["pt", "en"], "en") in ("pt", "en")


def test_single_language_skips_the_model(monkeypatch):
    def boom():
        raise AssertionError("model must not load")

    monkeypatch.setattr(lang, "_model", boom)
    assert detect_lang("anything goes here, really", ["es"], "es") == "es"


def test_short_text_uses_default():
    assert detect_lang("ok", ["pt", "en"], "en") == "en"
    assert detect_lang("ok", ["pt", "en"], "pt") == "pt"


@pytest.mark.parametrize("text", ["hola\nque tal amigo", "12345 67890 !!!!", "😀😀😀😀😀😀😀😀😀😀😀😀"])
def test_newlines_and_symbols_do_not_raise(text):
    assert detect_lang(text, ALL, "pt") in ALL


def test_missing_model_returns_default(monkeypatch):
    monkeypatch.setattr(lang, "_model", lambda: None)
    assert detect_lang("that was an amazing play, well done", ["pt", "en"], "pt") == "pt"


def test_spoken_text_announce():
    msg = Msg("twitch", "alice", "oi", 0)
    assert spoken_text(msg, "pt", True) == "alice disse: oi"
    assert spoken_text(msg, "en", True) == "alice says: oi"
    assert spoken_text(msg, "es", True) == "alice dijo: oi"
    assert spoken_text(msg, "pt", False) == "oi"


def test_username_underscores_become_spaces():
    assert spoken_text(Msg("twitch", "xX_Gamer_Xx", "oi", 0), "pt", True) == "xX Gamer Xx disse: oi"
    assert spoken_text(Msg("twitch", "João", "oi", 0), "pt", True) == "João disse: oi"
