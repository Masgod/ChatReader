from chatreader.lang import detect_lang, spoken_text
from chatreader.models import Msg


def test_detects_pt():
    assert detect_lang("eu gostei muito dessa jogada, muito boa", "en") == "pt"


def test_detects_en():
    assert detect_lang("that was an amazing play, well done", "pt") == "en"


def test_short_text_uses_default():
    assert detect_lang("ok", "en") == "en"
    assert detect_lang("ok", "pt") == "pt"


def test_spoken_text_announce():
    msg = Msg("twitch", "alice", "oi", 0)
    assert spoken_text(msg, "pt", True) == "alice disse: oi"
    assert spoken_text(msg, "en", True) == "alice says: oi"
    assert spoken_text(msg, "pt", False) == "oi"


def test_username_underscores_become_spaces():
    assert spoken_text(Msg("twitch", "xX_Gamer_Xx", "oi", 0), "pt", True) == "xX Gamer Xx disse: oi"
    assert spoken_text(Msg("twitch", "João", "oi", 0), "pt", True) == "João disse: oi"
