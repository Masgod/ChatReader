
import pytest

from chatreader.pronounce import apply_pronunciations as ap


def test_case_insensitive_and_accents():
    assert ap("oi Zé", {"zé": "ze"}) == "oi ze"
    assert ap("oi ZÉ e João", {"zé": "ze", "joão": "joao"}) == "oi ze e joao"


def test_name_before_punctuation_or_end():
    assert ap("kekw!", {"kekw": "kek double you"}) == "kek double you!"
    assert ap("oi fulano, tudo bem", {"fulano": "fulaninho"}) == "oi fulaninho, tudo bem"
    assert ap("ola kekw", {"kekw": "k"}) == "ola k"


def test_whole_word_only():
    assert ap("bits e bit", {"bit": "x"}) == "bits e x"
    assert ap("subbit", {"bit": "x"}) == "subbit"


@pytest.mark.parametrize("key", ["c++", "a.b", "(x)", "[a]", "a|b", "$5", "^"])
def test_regex_characters_match_literally(key):
    assert ap(f"say {key} now", {key: "OK"}) == "say OK now"
    assert ap("say axb now", {"a.b": "OK"}) == "say axb now"


def test_longer_key_wins():
    assert ap("hi there you", {"hi": "A", "hi there": "B"}) == "B you"
    assert ap("hi there you", {"hi there": "B", "hi": "A"}) == "B you"


def test_empty_rules_untouched():
    assert ap("anything  at all", {}) == "anything  at all"


def test_replacement_is_literal_not_a_pattern():
    assert ap("x", {"x": r"\1 $1 \g<0>"}) == r"\1 $1 \g<0>"


def test_no_chain_replacement():
    assert ap("a", {"a": "b", "b": "c"}) == "b"
