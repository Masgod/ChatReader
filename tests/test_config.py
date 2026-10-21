import pytest

from chatreader.config import Config, load_config, normalize, save_config, validate


def test_missing_file_creates_defaults(tmp_path):
    path = tmp_path / "config.toml"
    cfg = load_config(path)
    assert path.exists()
    assert cfg == Config()


def test_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    cfg = Config(twitch_channel="somechannel", queue_size=7, announce_user=False)
    save_config(path, cfg)
    assert load_config(path) == cfg


def test_corrupt_file_renamed_and_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is = not [valid toml", encoding="utf-8")
    cfg = load_config(path)
    assert (tmp_path / "config.toml.bad").exists()
    assert cfg == Config()


def test_normalize_twitch():
    cfg = normalize(Config(twitch_channel="#SomeChannel"))
    assert cfg.twitch_channel == "somechannel"


def test_normalize_youtube_urls():
    urls = [
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5",
        "dQw4w9WgXcQ",
    ]
    for url in urls:
        assert normalize(Config(youtube_video_id=url)).youtube_video_id == "dQw4w9WgXcQ"


def test_validate_rejects_bad_values():
    assert validate(Config(twitch_channel="a b")) != []
    assert validate(Config(youtube_video_id="short")) != []
    assert validate(Config(queue_size=0)) != []
    assert validate(Config(port=70000)) != []
    assert validate(Config()) == []


def test_new_config_defaults():
    c = Config()
    assert (c.twitch_roles, c.youtube_roles, c.repeat_seconds, c.per_user_voices) == ([], [], 30, True)


def test_roles_validation():
    assert validate(Config(twitch_roles=["sub", "mod"], youtube_roles=[])) == []
    assert any("twitch_roles" in e for e in validate(Config(twitch_roles=["owner"])))
    assert any("youtube_roles" in e for e in validate(Config(youtube_roles=["admin"])))


def test_repeat_seconds_validation():
    for bad in (-1, 601):
        assert any("repeat_seconds" in e for e in validate(Config(repeat_seconds=bad)))
    assert validate(Config(repeat_seconds=0)) == [] and validate(Config(repeat_seconds=600)) == []


def test_new_keys_round_trip_toml(tmp_path):
    p = tmp_path / "c.toml"
    cfg = Config(twitch_roles=["sub"], youtube_roles=["mod"], repeat_seconds=45, per_user_voices=False)
    save_config(p, cfg)
    assert load_config(p) == cfg


def test_bad_roles_in_toml_load_defaults(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('twitch_roles = ["admin"]\n', encoding="utf-8")
    assert load_config(p) == Config()
    assert (tmp_path / "c.toml.bad").exists()


def test_languages_default():
    c = Config()
    assert c.languages == ["pt", "en"]
    assert c.voices() == {"pt": "pf_dora", "en": "af_heart"}


@pytest.mark.parametrize("langs", [[], ["xx"], ["pt", "pt"]])
def test_bad_languages_are_rejected(langs):
    assert validate(Config(languages=langs))


def test_default_lang_must_be_enabled():
    assert any("default_lang" in e for e in validate(Config(languages=["es"], default_lang="pt")))
    assert validate(Config(languages=["es"], default_lang="es")) == []


def test_old_config_file_loads(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('voice_pt = "pm_alex"\ndefault_lang = "en"\n', encoding="utf-8")
    c = load_config(p)
    assert (c.languages, c.voice_pt, c.default_lang) == (["pt", "en"], "pm_alex", "en")


def test_voice_names_validated_for_every_language():
    assert validate(Config(voice_it="../x"))
