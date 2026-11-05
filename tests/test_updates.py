
import json

import pytest

from chatreader.updates import API_URL, UpdateChecker, latest_release, parse_version

REL = "https://github.com/Masgod/ChatReader/releases/tag/"


def rel(tag, **kw):
    return {"tag_name": tag, "html_url": REL + tag, "draft": False, "prerelease": False, **kw}


@pytest.mark.parametrize("tag,expected", [("v0.5.0", (0, 5, 0)), ("0.5.0", (0, 5, 0)), ("v0.10.0", (0, 10, 0)), ("v1.2", (1, 2)), ("v1", (1,)),
                                          ("beta", None), ("v0.5.0-rc1", None), ("", None), ("v1.x", None), (None, None), (5, None)])
def test_parse_version(tag, expected):
    assert parse_version(tag) == expected


def test_numbers_are_compared_not_strings():
    assert parse_version("v0.10.0") > parse_version("v0.9.0")


def test_latest_release_returns_version_and_url():
    assert latest_release(lambda: rel("v0.6.0")) == {"version": "0.6.0", "url": REL + "v0.6.0"}


@pytest.mark.parametrize("data", [rel("v0.6.0", draft=True), rel("v0.6.0", prerelease=True), rel("nightly"), {"message": "rate limit"}, [], "x", None, {}])
def test_drafts_prereleases_and_garbage_are_ignored(data):
    assert latest_release(lambda: data) is None


def test_a_foreign_release_url_is_replaced_by_the_releases_page():
    out = latest_release(lambda: rel("v0.6.0", html_url="http://evil.example/x"))
    assert out["url"] == "https://github.com/Masgod/ChatReader/releases"


def test_fetch_errors_never_raise():
    def boom():
        raise OSError("403 rate limit or no network")

    assert latest_release(boom) is None


def test_the_one_call_goes_to_the_fixed_github_url():
    assert API_URL == "https://api.github.com/repos/Masgod/ChatReader/releases/latest"


def test_default_fetch_uses_https_headers_and_a_timeout(monkeypatch):
    from chatreader import updates

    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return json.dumps(rel("v9.9.9")).encode()

    def fake_urlopen(req, timeout):
        seen["url"], seen["headers"], seen["timeout"] = req.full_url, dict(req.header_items()), timeout
        return Resp()

    monkeypatch.setattr(updates.urllib.request, "urlopen", fake_urlopen)
    assert updates.fetch_latest("0.5.0")["tag_name"] == "v9.9.9"
    assert seen["url"] == API_URL and seen["timeout"] == 10
    assert seen["headers"]["Accept"] == "application/vnd.github+json" and seen["headers"]["User-agent"] == "ChatReader/0.5.0"


def checker(current, answers, enabled=True):
    calls, notes = [], []

    def fetch():
        calls.append(1)
        a = answers[min(len(calls), len(answers)) - 1]
        if isinstance(a, Exception):
            raise a
        return a

    return UpdateChecker(current, fetch, notes.append, sleep=lambda s: None, enabled=lambda: enabled), calls, notes


def test_a_newer_release_is_available_and_announced():
    c, calls, notes = checker("0.5.0", [rel("v0.6.0")])
    c.check()
    assert c.available == {"version": "0.6.0", "url": REL + "v0.6.0"} and notes == [c.available]


@pytest.mark.parametrize("current,tag", [("0.5.0", "v0.5.0"), ("0.5.0", "v0.4.9"), ("0.10.0", "v0.9.0")])
def test_same_or_older_is_not_available(current, tag):
    c, _, notes = checker(current, [rel(tag)])
    c.check()
    assert c.available is None and notes == []


def test_the_same_version_is_announced_once_per_run():
    c, calls, notes = checker("0.5.0", [rel("v0.6.0")])
    for _ in range(3):
        c.check()
    assert len(calls) == 3 and len(notes) == 1
    c2, _, notes2 = checker("0.5.0", [rel("v0.6.0"), rel("v0.7.0")])
    c2.check()
    c2.check()
    assert [n["version"] for n in notes2] == ["0.6.0", "0.7.0"]  # a newer one after that is news again


def test_check_updates_off_means_no_request_at_all():
    c, calls, notes = checker("0.5.0", [rel("v0.6.0")], enabled=False)
    c.check()
    assert calls == [] and c.available is None and notes == []


def test_a_failing_check_keeps_what_was_found_and_does_not_raise():
    c, _, notes = checker("0.5.0", [rel("v0.6.0"), OSError("down")])
    c.check()
    c.check()
    assert c.available["version"] == "0.6.0" and len(notes) == 1


def test_a_failing_notify_does_not_stop_the_checker():
    def bad(_):
        raise RuntimeError("tray gone")

    c = UpdateChecker("0.5.0", lambda: rel("v0.6.0"), bad, sleep=lambda s: None)
    c.check()
    assert c.available["version"] == "0.6.0"


def test_loop_checks_at_start_then_every_day():
    class Stop(Exception):
        pass

    waits, calls = [], []

    def sleep(s):
        waits.append(s)
        if len(waits) == 2:
            raise Stop

    c = UpdateChecker("0.5.0", lambda: calls.append(1) or rel("v0.5.0"), lambda r: None, sleep=sleep)
    with pytest.raises(Stop):
        c.loop()
    assert len(calls) == 2 and waits == [24 * 3600, 24 * 3600]
