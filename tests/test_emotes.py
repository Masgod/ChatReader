import pytest

from chatreader.emotes import speak_emotes


@pytest.mark.parametrize("text,lang,out", [
    ("KEKW", "en", "ha ha"),
    ("kkkkkk que isso", "pt", "há há que isso"),
    ("rsrsrs", "pt", "há há"),
    ("hahaha nice", "en", "ha ha nice"),
    ("great play Kappa", "en", "great play"),
    ("Kappa", "en", ""),
    ("love it <3", "en", "love it"),
    ("oi :face-blue-smiling: gente", "pt", "oi gente"),
    ("LUL LUL", "en", "ha ha ha ha"),
])
def test_emotes(text, lang, out):
    assert speak_emotes(text, lang) == out


@pytest.mark.parametrize("text", ["eu gostei muito dessa jogada", "that was a great play", "pogo stick and kappas", "shake the kitchen, thanks"])
def test_normal_words_untouched(text):
    assert speak_emotes(text, "en") == text


@pytest.mark.parametrize("code", ["pt", "en", "es", "fr", "it"])
def test_laugh_comes_from_the_language_table(code):
    from chatreader.languages import LANGUAGES

    assert speak_emotes("KEKW", code) == LANGUAGES[code].laugh
