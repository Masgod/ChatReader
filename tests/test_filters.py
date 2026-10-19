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


# ---- roles and duplicates ----

from chatreader.filters import explain  # noqa: E402


def r(text="hello there friend", user="alice", platform="twitch", roles=(), ts=0.0):
    return Msg(platform, user, text, ts, frozenset(roles))


def test_role_filter_empty_reads_everyone():
    assert explain(r(), Config(), FilterState(5)) is None


def test_role_filter_requires_listed_role():
    cfg = Config(twitch_roles=["sub"])
    assert explain(r(roles={"sub"}), cfg, FilterState(5)) is None
    assert explain(r(), cfg, FilterState(5)) == "role"
    assert explain(r(roles={"mod"}), cfg, FilterState(5)) == "role"


def test_role_filter_is_per_platform():
    cfg = Config(twitch_roles=["sub"])
    assert explain(r(platform="youtube"), cfg, FilterState(5)) is None


def test_owner_always_passes_role_filter():
    assert explain(r(roles={"owner"}), Config(twitch_roles=["mod"]), FilterState(5)) is None


def test_role_filter_unreportable_role():
    cfg = Config(youtube_roles=["vip"])
    assert explain(r(platform="youtube", roles={"sub", "mod"}), cfg, FilterState(5)) == "role"
    assert explain(r(platform="youtube", roles={"owner"}), cfg, FilterState(5)) is None


def test_explain_role_before_history():
    state = FilterState(5)
    assert explain(r(), Config(twitch_roles=["mod"]), state) == "role"
    assert state.recent == {} and state.seen == {}


def test_duplicate_from_other_user_within_window():
    state, cfg = FilterState(5), Config()
    assert apply(r(user="a", ts=0.0), cfg, state) is not None
    assert explain(r(user="b", ts=10.0), cfg, state) == "duplicate"


def test_duplicate_normalizes_case_and_spaces():
    state, cfg = FilterState(5), Config()
    apply(r("Hello   THERE friend", user="a", ts=0.0), cfg, state)
    assert explain(r("hello there  friend", user="b", ts=1.0), cfg, state) == "duplicate"


def test_duplicate_outside_window_passes():
    state, cfg = FilterState(5), Config()
    apply(r(user="a", ts=0.0), cfg, state)
    assert explain(r(user="b", ts=31.0), cfg, state) is None


def test_duplicate_window_zero_off():
    state, cfg = FilterState(5), Config(repeat_seconds=0)
    apply(r(user="a", ts=0.0), cfg, state)
    assert explain(r(user="b", ts=1.0), cfg, state) is None


def test_skipped_message_does_not_enter_seen():
    state, cfg = FilterState(5), Config()
    assert apply(r("see https://x.com now", user="a"), cfg, state) is None
    assert state.seen == {}
    cfg_roles = Config(twitch_roles=["mod"])
    assert apply(r("nice play everyone", user="a"), cfg_roles, state) is None
    assert apply(r("nice play everyone", user="b"), cfg, state) is not None


def test_seen_is_pruned_and_capped():
    state, cfg = FilterState(5), Config()
    for i in range(250):
        apply(r(f"distinct message number {i}", user=f"u{i}", ts=float(i) / 100), cfg, state)
    assert len(state.seen) <= 200
    apply(r("much later message here", ts=1000.0), cfg, state)
    assert list(state.seen) == ["much later message here"]


def test_per_user_repeat_still_reports_repeat():
    state, cfg = FilterState(5), Config()
    apply(r(user="a", ts=0.0), cfg, state)
    assert explain(r(user="a", ts=1.0), cfg, state) == "repeat"


def test_explain_agrees_with_apply_for_new_reasons():
    cfg = Config(twitch_roles=["sub"])
    state = FilterState(5)
    for msg in (r(), r(roles={"sub"}), r(roles={"sub"}, user="b", ts=1.0)):
        assert (explain(msg, cfg, state) is None) == (apply(msg, cfg, copy.deepcopy(state)) is not None)
        apply(msg, cfg, state)
