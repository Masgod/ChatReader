import pytest

from chatreader.languages import DEFAULT_LANGUAGES, LANGUAGES

KINDS = ("bits", "subs", "gifts", "raids", "superchat", "members")


@pytest.mark.parametrize("code", list(LANGUAGES))
@pytest.mark.parametrize("kind", KINDS)
def test_every_language_has_every_event_kind(code, kind):
    assert LANGUAGES[code].events[kind]("3").strip()


@pytest.mark.parametrize("code,name,kokoro,prefixes,voice,says,laugh,beta", [
    ("pt", "Português", "pt-br", "p", "pf_dora", "disse", "há há", False),
    ("en", "English", "en-us", "ab", "af_heart", "says", "ha ha", False),
    ("es", "Español", "es", "e", "ef_dora", "dijo", "ja ja", True),
    ("fr", "Français", "fr-fr", "f", "ff_siwis", "dit", "ha ha", True),
    ("it", "Italiano", "it", "i", "if_sara", "ha detto", "ah ah", True),
])
def test_values_match_spec(code, name, kokoro, prefixes, voice, says, laugh, beta):
    lang = LANGUAGES[code]
    assert (lang.code, lang.name, lang.kokoro, lang.voice_prefixes) == (code, name, kokoro, prefixes)
    assert (lang.default_voice, lang.says, lang.laugh, lang.beta) == (voice, says, laugh, beta)


def test_order_and_defaults():
    assert list(LANGUAGES) == ["pt", "en", "es", "fr", "it"]
    assert DEFAULT_LANGUAGES == ["pt", "en"]


def test_pt_en_phrases_unchanged():
    assert LANGUAGES["pt"].events["bits"]("1") == "doou 1 bit"
    assert LANGUAGES["en"].events["raids"]("5") == "is raiding with 5 viewers"
    assert LANGUAGES["pt"].events["subs"]("") == "se inscreveu"
