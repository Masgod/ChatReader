from chatreader.voices import voice_for

POOL = [f"af_v{i}" for i in range(10)]


def test_voice_for_is_stable_and_case_insensitive():
    assert voice_for("twitch", "Ana", POOL) == voice_for("twitch", "Ana", POOL) == voice_for("twitch", "ana", POOL)


def test_voice_for_depends_on_platform():
    big = [f"af_v{i}" for i in range(20)]
    assert any(voice_for("twitch", f"n{i}", big) != voice_for("youtube", f"n{i}", big) for i in range(30))


def test_voice_for_spreads_over_pool():
    used = {voice_for("twitch", f"viewer{i}", POOL) for i in range(200)}
    assert len(used) >= 8


def test_voice_for_empty_pool_and_odd_names():
    assert voice_for("twitch", "ana", []) == ""
    for name in ("🔥 Ana  Maria", "", "x" * 300):
        assert voice_for("twitch", name, POOL) in POOL
