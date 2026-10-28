from chatreader.themes import hero_name

PNG = b"\x89PNG\r\n\x1a\n"


def make(root, heroes):
    folder = root / "mine"
    folder.mkdir(parents=True)
    (folder / "theme.toml").write_text('name = "Mine"\n', encoding="utf-8")
    for hero in heroes:
        (folder / "heroes" / hero).mkdir(parents=True)
        (folder / "heroes" / hero / "card.png").write_bytes(PNG)


def test_name_follows_the_same_slot_rule_as_the_page(tmp_path):
    make(tmp_path, ["wraith", "abrams", "grey_talon"])  # sorted: abrams, grey_talon, wraith
    assert hero_name(tmp_path, "mine", 0) == "Abrams"
    assert hero_name(tmp_path, "mine", 1) == "Grey Talon"
    assert hero_name(tmp_path, "mine", 5) == "Wraith"  # 5 % 3 == 2


def test_hero_slot_finds_a_hero_by_typed_name(tmp_path):
    from chatreader.themes import hero_slot

    make(tmp_path, ["wraith", "abrams", "grey_talon"])  # sorted: abrams, grey_talon, wraith
    assert hero_slot(tmp_path, "mine", "Grey Talon") == 1
    assert hero_slot(tmp_path, "mine", "  grey-talon ") == 1
    assert hero_slot(tmp_path, "mine", "WRAITH") == 2
    assert hero_slot(tmp_path, "mine", "nobody") is None
    assert hero_slot(tmp_path, "mine", "") is None
    assert hero_name(tmp_path, "mine", hero_slot(tmp_path, "mine", "wraith")) == "Wraith"  # the page lands on the same hero


def test_no_name_without_heroes_or_with_a_broken_theme(tmp_path):
    make(tmp_path, [])
    assert hero_name(tmp_path, "mine", 3) is None
    assert hero_name(tmp_path, "missing", 3) is None
    assert hero_name(None, "default", 3) is None
