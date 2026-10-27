import os
from pathlib import Path

import pytest

from chatreader.themes import ThemeError, list_themes, load_named, load_theme, resolve_file

PNG = b"\x89PNG\r\n\x1a\n"

GOOD = """
name = "Heroes"
author = "me"
font = "fonts/f.woff2"
fallback = "neutral"

[bubble]
background = "#112233"
color = "#fff"
radius = 8
animation = "fade"

[events]
background = "#4b2a86"
color = "#ffffff"

[[expressions]]
name = "happy"
chance = 0.3

[[expressions]]
name = "neutral"
chance = 0.7
"""


def make(root: Path, toml: str = GOOD, heroes=("wraith", "abrams"), files=("happy.png", "neutral.png")) -> Path:
    folder = root / "heroes_theme"
    folder.mkdir(parents=True)
    (folder / "theme.toml").write_text(toml, encoding="utf-8")
    (folder / "fonts").mkdir()
    (folder / "fonts" / "f.woff2").write_bytes(b"font")
    for hero in heroes:
        (folder / "heroes" / hero).mkdir(parents=True)
        for f in files:
            (folder / "heroes" / hero / f).write_bytes(PNG)
    return folder


def test_valid_theme_loads_with_sorted_heroes_and_urls(tmp_path):
    t = load_theme(make(tmp_path), "heroes_theme")
    assert [h["name"] for h in t["heroes"]] == ["abrams", "wraith"]
    assert t["heroes"][0]["images"]["happy"] == "/themes/heroes_theme/heroes/abrams/happy.png"
    assert t["font"] == "/themes/heroes_theme/fonts/f.woff2"
    assert t["bubble"] == {"background": "#112233", "color": "#fff", "radius": 8, "animation": "fade", "layout": "side",
                         "portrait": {"width": 56, "height": 56}}
    assert t["fallback"] == "neutral" and [e["name"] for e in t["expressions"]] == ["happy", "neutral"]


def test_bubble_layout_defaults_to_side_and_accepts_top(tmp_path):
    assert load_named(None, "default")["bubble"]["layout"] == "side"
    top = load_theme(make(tmp_path, '[bubble]\nlayout = "top"', heroes=()), "heroes_theme")
    assert top["bubble"]["layout"] == "top"


@pytest.mark.parametrize("value", ['"diagonal"', "3", '""'])
def test_bubble_layout_rejects_other_values(tmp_path, value):
    with pytest.raises(ThemeError, match="layout"):
        load_theme(make(tmp_path, f"[bubble]\nlayout = {value}", heroes=()), "heroes_theme")


def test_portrait_size_defaults_follow_the_layout(tmp_path):
    assert load_named(None, "default")["bubble"]["portrait"] == {"width": 56, "height": 56}
    top = load_theme(make(tmp_path, '[bubble]\nlayout = "top"', heroes=()), "heroes_theme")
    assert top["bubble"]["portrait"] == {"width": 96, "height": 96}


def test_portrait_size_can_be_set_by_the_theme(tmp_path):
    t = load_theme(make(tmp_path, "[bubble]\nportrait_width = 120\nportrait_height = 160", heroes=()), "heroes_theme")
    assert t["bubble"]["portrait"] == {"width": 120, "height": 160}


@pytest.mark.parametrize("key,value", [
    ("portrait_width", 15), ("portrait_width", 321), ("portrait_height", 0), ("portrait_height", 999),
    ("portrait_width", '"big"'), ("portrait_height", 80.5), ("portrait_width", "true"),
])
def test_portrait_size_out_of_range_or_wrong_type_is_rejected(tmp_path, key, value):
    with pytest.raises(ThemeError, match=key):
        load_theme(make(tmp_path, f"[bubble]\n{key} = {value}", heroes=()), "heroes_theme")


def test_builtin_default_is_valid_and_has_no_heroes():
    t = load_named(None, "default")
    assert t["heroes"] == [] and t["bubble"]["animation"] == "slide"


@pytest.mark.parametrize("toml,fragment", [
    ("this is = = not toml", "not valid"),
    ("[bubble]\nanimation = 'spin'", "animation"),
    ("[bubble]\nbackground = 'red'", "background"),
    ("[bubble]\nbackground = 5", "background"),
    ("[bubble]\nradius = 41", "radius"),
    ("[bubble]\nradius = -1", "radius"),
    ("[events]\ncolor = '#12'", "color"),
    ("[[expressions]]\nname = 'a'\nchance = 1.5", "chance"),
    ("[[expressions]]\nname = 'a'\nchance = 0.6\n[[expressions]]\nname = 'b'\nchance = 0.6", "at most 1"),
    ("fallback = 'ghost'", "fallback"),
    ("font = '../x.ttf'", "fonts folder"),
    ("font = 'fonts/missing.woff2'", "does not exist"),
    ("font = 'fonts/f.exe'", ".woff2"),
    ("bubble = 3", "table"),
])
def test_invalid_theme_raises_with_a_useful_message(tmp_path, toml, fragment):
    folder = make(tmp_path, toml, heroes=())
    with pytest.raises(ThemeError, match=fragment):
        load_theme(folder, "heroes_theme")


@pytest.mark.parametrize("toml", ['fallback = ["a"]', "x = " + "[" * 5000 + "]" * 5000, 'font = ["a"]'])
def test_odd_manifest_contents_raise_theme_error_not_crash(tmp_path, toml):
    with pytest.raises(ThemeError):
        load_theme(make(tmp_path, toml, heroes=()), "heroes_theme")


def test_manifest_that_is_a_folder_raises_theme_error(tmp_path):
    folder = tmp_path / "t"
    (folder / "theme.toml").mkdir(parents=True)
    with pytest.raises(ThemeError):
        load_theme(folder, "t")
    assert list_themes(tmp_path)[1]["valid"] is False  # one bad folder must not break the listing


def test_missing_manifest_is_an_error(tmp_path):
    (tmp_path / "t").mkdir()
    with pytest.raises(ThemeError, match="missing"):
        load_theme(tmp_path / "t", "t")


def test_too_many_images_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr("chatreader.themes.MAX_IMAGES", 3)
    with pytest.raises(ThemeError, match="more than"):
        load_theme(make(tmp_path), "heroes_theme")  # 2 heroes x 2 images


def test_oversized_image_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr("chatreader.themes.MAX_FILE_BYTES", 4)
    with pytest.raises(ThemeError, match="5 MB"):
        load_theme(make(tmp_path), "heroes_theme")


def test_list_themes_puts_default_first_and_flags_bad_ones(tmp_path):
    make(tmp_path)
    (tmp_path / "default").mkdir()
    (tmp_path / "broken").mkdir()
    (tmp_path / "bad name").mkdir()
    listed = list_themes(tmp_path)
    rows = {r["name"]: r for r in listed[1:]}
    assert listed[0]["name"] == "default" and listed[0]["valid"]  # the built-in, first
    assert rows["default"]["valid"] is False  # a user folder named default never shadows it
    assert rows["heroes_theme"]["valid"] and rows["heroes_theme"]["title"] == "Heroes"
    assert not rows["broken"]["valid"] and rows["broken"]["error"]
    assert not rows["bad name"]["valid"]


def test_list_themes_without_a_user_folder():
    assert [r["name"] for r in list_themes(None)] == ["default"]


def test_resolve_file_serves_an_allowed_image(tmp_path):
    make(tmp_path)
    got = resolve_file(tmp_path, "heroes_theme", "heroes/wraith/happy.png")
    assert got is not None and got.read_bytes() == PNG


@pytest.mark.parametrize("rel", [
    "../heroes_theme/theme.toml", "../../x.png", "theme.toml", "heroes/wraith/happy.exe", "heroes\\wraith\\happy.png",
    "/etc/passwd.png", "C:/Windows/x.png", "", "heroes/nope.png", "heroes",
])
def test_resolve_file_refuses_everything_else(tmp_path, rel):
    make(tmp_path)
    assert resolve_file(tmp_path, "heroes_theme", rel) is None


@pytest.mark.parametrize("name", ["../heroes_theme", "a b", "", "missing"])
def test_resolve_file_refuses_bad_theme_names(tmp_path, name):
    make(tmp_path)
    assert resolve_file(tmp_path, name, "heroes/wraith/happy.png") is None


def test_resolve_file_refuses_a_symlink_that_escapes(tmp_path):
    folder = make(tmp_path / "themes")
    secret = tmp_path / "secret.png"
    secret.write_bytes(PNG)
    link = folder / "heroes" / "wraith" / "link.png"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not allowed here")
    assert resolve_file(tmp_path / "themes", "heroes_theme", "heroes/wraith/link.png") is None
    with pytest.raises(ThemeError, match="outside"):
        load_theme(folder, "heroes_theme")


def test_resolve_file_serves_nothing_for_the_builtin_toml():
    assert resolve_file(None, "default", "theme.toml") is None
