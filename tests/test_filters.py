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
