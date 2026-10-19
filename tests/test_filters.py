import copy

import pytest

from chatreader.config import Config
from chatreader.filters import FilterState, apply
from chatreader.models import Msg


def m(text, user="alice"):
    return Msg("twitch", user, text, 0.0)


@pytest.mark.parametrize(
    "msg",
    [
        m("hi", user="Nightbot"),
        m("!so someone"),
        m("look https://x.com"),
        m("www.example.com"),
        m("   "),
        m(""),
        m("😂😂😂"),
        m("Kappa Kappa Kappa Kappa Kappa"),
        m("aaaaaaaaaaaaaaaa"),
    ],
)
def test_dropped(msg):
    assert apply(msg, Config(), FilterState(5)) is None


@pytest.mark.parametrize("text", ["oi pessoal", "Kappa nice play"])
def test_kept(text):
    result = apply(m(text), Config(), FilterState(5))
    assert result is not None
    assert result.text == text


def test_repeat_same_user_second_only():
    cfg, state = Config(), FilterState(5)
    assert apply(m("oi pessoal"), cfg, state) is not None
    assert apply(m("oi pessoal"), cfg, state) is None


def test_truncates_to_max_chars():
    cfg = Config(max_chars=200)
    text = " ".join(f"p{i:03d}" for i in range(101))  # ~500 chars, no emote spam
    result = apply(m(text), cfg, FilterState(5))
    assert result is not None
    assert len(result.text) <= 200


def test_rule_order():
    cfg, state = Config(), FilterState(5)
    before = copy.deepcopy(state)
    assert apply(m("!so someone", user="Nightbot"), cfg, state) is None
    assert state == before


from chatreader.filters import explain  # noqa: E402


@pytest.mark.parametrize(
    "msg,reason",
    [
        (m("hi", user="Nightbot"), "ignored user"),
        (m("!so someone"), "command"),
        (m("look https://x.com"), "link"),
        (m("www.example.com"), "link"),
        (m("..."), "no text"),
        (m("   "), "no text"),
        (m("Kappa Kappa Kappa Kappa Kappa"), "spam"),
        (m("aaaaaaaaaaaaaaaa"), "spam"),
    ],
)
def test_explain_reasons(msg, reason):
    assert explain(msg, Config(), FilterState(5)) == reason


def test_explain_repeat_and_no_history_side_effect():
    state = FilterState(5)
    assert explain(m("good play there"), Config(), state) is None
    assert explain(m("good play there"), Config(), state) is None  # explain never records
    assert apply(m("good play there"), Config(), state) is not None
    assert explain(m("good play there"), Config(), state) == "repeat"


@pytest.mark.parametrize(
    "msg",
    [m("hi", user="Nightbot"), m("!so x"), m("https://x.com"), m("   "), m("😂😂😂"), m("aaaaaaaaaaaaaaaa"), m("hello there friend"), m("boa jogada")],
)
def test_explain_agrees_with_apply(msg):
    assert (explain(msg, Config(), FilterState(5)) is None) == (apply(msg, Config(), FilterState(5)) is not None)
