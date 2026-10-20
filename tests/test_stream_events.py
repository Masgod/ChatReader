from types import SimpleNamespace

import pytest

from chatreader.announce import event_text
from chatreader.config import Config, validate
from chatreader.filters import FilterState, apply, explain
from chatreader.lang import spoken_text
from chatreader.models import Msg
from chatreader.sources.twitch import parse_notice, parse_privmsg
from chatreader.sources.youtube import to_msg

HOST = ":tmi.twitch.tv USERNOTICE #chan"


def notice(tags: str, text: str = "") -> str:
    return f"@{tags} {HOST}" + (f" :{text}" if text else "")


# --- Twitch --------------------------------------------------------------

def test_bits_privmsg_becomes_a_bits_event():
    m = parse_privmsg("@badges=;bits=100;display-name=Fulano :fulano!fulano@fulano.tmi.twitch.tv PRIVMSG #chan :cheer100 great stream")
    assert (m.kind, m.detail, m.user) == ("bits", "100", "Fulano")
    assert m.text == "great stream"  # the cheermote token is not read


def test_plain_privmsg_stays_chat():
    m = parse_privmsg("@display-name=Fulano :fulano!fulano@fulano.tmi.twitch.tv PRIVMSG #chan :oi pessoal")
    assert (m.kind, m.detail) == ("chat", "")


def test_new_sub_has_no_months():
    m = parse_notice(notice("display-name=Fulano;msg-id=sub;login=fulano"))
    assert (m.kind, m.detail, m.text, m.user) == ("subs", "", "", "Fulano")


def test_resub_carries_months_and_message():
    m = parse_notice(notice("display-name=Fulano;msg-id=resub;msg-param-cumulative-months=7", "love it"))
    assert (m.kind, m.detail, m.text) == ("subs", "7", "love it")


def test_mystery_gift_counts_the_whole_gift():
    m = parse_notice(notice("display-name=Gifter;msg-id=submysterygift;msg-param-mass-gift-count=5"))
    assert (m.kind, m.detail, m.user) == ("gifts", "5", "Gifter")


def test_single_gift_counts_one():
    m = parse_notice(notice("display-name=Gifter;msg-id=subgift;msg-param-recipient-display-name=Other"))
    assert (m.kind, m.detail) == ("gifts", "1")


def test_gift_that_belongs_to_a_mystery_gift_is_skipped():
    assert parse_notice(notice("display-name=Gifter;msg-id=subgift;msg-param-community-gift-id=123")) is None


def test_raid_carries_viewer_count():
    m = parse_notice(notice("display-name=Raider;msg-id=raid;msg-param-viewerCount=40"))
    assert (m.kind, m.detail, m.user) == ("raids", "40", "Raider")


@pytest.mark.parametrize("line", [
    notice("display-name=X;msg-id=ritual"),
    "@display-name=X :x!x@x.tmi.twitch.tv PRIVMSG #chan :oi",
    "PING :tmi.twitch.tv",
    f"@msg-id=raid {HOST}",  # no name
])
def test_notice_ignores_other_lines(line):
    assert parse_notice(line) is None


# --- YouTube -------------------------------------------------------------

def item(type_, message="", amount=""):
    author = SimpleNamespace(name="Fulano", isChatOwner=False, isChatModerator=False, isChatSponsor=False)
    return SimpleNamespace(type=type_, author=author, message=message, amountString=amount)


def test_super_chat():
    m = to_msg(item("superChat", "valeu", "R$10.00"))
    assert (m.kind, m.detail, m.text) == ("superchat", "R$10.00", "valeu")


def test_super_sticker_has_no_text():
    m = to_msg(item("superSticker", None, "$2.00"))
    assert (m.kind, m.detail, m.text) == ("superchat", "$2.00", "")


def test_new_member_text_is_dropped():
    m = to_msg(item("newSponsor", "Welcome New Member!"))
    assert (m.kind, m.text) == ("members", "")


def test_youtube_text_message_is_chat():
    assert to_msg(item("textMessage", "oi")).kind == "chat"


# --- Spoken text ---------------------------------------------------------

def ev(kind, detail="", text="", user="Fulano"):
    return Msg("twitch", user, text, 0.0, kind=kind, detail=detail)


@pytest.mark.parametrize("msg,lang,expected", [
    (ev("bits", "100", "mensagem"), "pt", "Fulano doou 100 bits: mensagem"),
    (ev("bits", "1"), "pt", "Fulano doou 1 bit"),
    (ev("bits", "100", "nice"), "en", "Fulano cheered 100 bits: nice"),
    (ev("subs"), "pt", "Fulano se inscreveu"),
    (ev("subs", "7", "oi"), "pt", "Fulano renovou a inscrição, 7 meses: oi"),
    (ev("subs", "7"), "en", "Fulano resubscribed for 7 months"),
    (ev("gifts", "5"), "pt", "Fulano deu 5 inscrições"),
    (ev("gifts", "1"), "pt", "Fulano deu 1 inscrição"),
    (ev("gifts", "5"), "en", "Fulano gifted 5 subs"),
    (ev("raids", "40"), "pt", "Fulano fez uma raid com 40 pessoas"),
    (ev("raids", "40"), "en", "Fulano is raiding with 40 viewers"),
    (ev("superchat", "R$10.00", "valeu"), "pt", "Fulano enviou R$10.00: valeu"),
    (ev("members"), "pt", "Fulano virou membro"),
    (ev("members"), "en", "Fulano became a member"),
    (ev("bits", "5", user="the_user"), "en", "the user cheered 5 bits"),
])
def test_event_text(msg, lang, expected):
    assert event_text(msg, lang) == expected


def test_spoken_text_uses_the_event_phrase_even_without_announce():
    assert spoken_text(ev("bits", "100", "oi"), "pt", False) == "Fulano doou 100 bits: oi"


def test_chat_spoken_text_is_unchanged():
    assert spoken_text(Msg("twitch", "Fulano", "oi", 0.0), "pt", True) == "Fulano disse: oi"


# --- Filters -------------------------------------------------------------

def run(msg, **cfg):
    c = Config(**cfg)
    s = FilterState(size=c.repeat_window)
    return explain(msg, c, s), apply(msg, c, s)


def test_event_ignores_role_filter_command_and_repeats():
    c, s = Config(twitch_roles=["mod"]), FilterState(size=5)
    m = ev("bits", "50", "oi")
    assert apply(m, c, s) is not None
    assert apply(m, c, s) is not None  # same text again is fine for a donation


def test_event_kind_can_be_switched_off():
    reason, out = run(ev("raids", "40"), event_kinds=["bits"])
    assert (reason, out) == ("event off", None)


def test_small_bit_donations_can_be_ignored():
    assert run(ev("bits", "3"), min_bits=10)[0] == "min bits"
    assert run(ev("bits", "10"), min_bits=10)[0] is None


def test_ignored_user_blocks_events_too():
    assert run(ev("bits", "100", user="nightbot"))[0] == "ignored user"


@pytest.mark.parametrize("text", ["https://spam.example", "!!!", "aaaaaaaaaaaa", "!play"])
def test_bad_event_message_is_dropped_but_the_announcement_stays(text):
    reason, out = run(ev("bits", "100", text))
    assert reason is None and out.text == ""


def test_event_message_is_truncated():
    _, out = run(ev("bits", "100", "palavra " * 50), max_chars=20)
    assert len(out.text) <= 20


# --- Config --------------------------------------------------------------

def test_defaults_read_every_kind_and_no_bits_minimum():
    c = Config()
    assert set(c.event_kinds) == {"bits", "subs", "gifts", "raids", "superchat", "members"} and c.min_bits == 0


def test_event_kinds_and_min_bits_are_validated():
    assert validate(Config(event_kinds=["nope"])) != []
    assert validate(Config(event_kinds=[])) == []
    assert validate(Config(min_bits=-1)) != []
    assert validate(Config(min_bits=100001)) != []
