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
