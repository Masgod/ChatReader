import json

from chatreader.config import Config
from chatreader.heroes import HeroPicker
from chatreader.voices import slot_for

CFG = Config()  # viewer 10 s .. 300 s, global 2 s .. 60 s


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(tmp_path, clock=None, rolls=()):
    seq = iter(rolls)
    return HeroPicker(tmp_path / "viewer_heroes.json", clock or Clock(), rng=lambda bits: next(seq))


def test_slot_defaults_to_the_hash_slot(tmp_path):
    assert make(tmp_path).slot("twitch", "Alice") == slot_for("twitch", "Alice")


def test_reroll_replaces_the_slot_case_insensitively(tmp_path):
    p = make(tmp_path, rolls=[777])
    assert p.reroll("twitch", "Alice", CFG) == 777
    assert p.slot("twitch", "alice") == 777
    assert p.slot("youtube", "alice") == slot_for("youtube", "alice")


def test_reroll_never_returns_the_current_slot(tmp_path):
    same = slot_for("twitch", "bob")
    p = make(tmp_path, rolls=[same, same, 5])
    assert p.reroll("twitch", "bob", CFG) == 5


def test_first_use_blocks_the_viewer_for_the_base_wait(tmp_path):
    clock = Clock()
    cfg = Config(random_cooldown_base=10, random_cooldown_max=300, random_global_base=0, random_global_max=0)
    p = make(tmp_path, clock, rolls=range(1, 50))
    assert p.reroll("twitch", "a", cfg)
    clock.t += 9
    assert p.reroll("twitch", "a", cfg) is None
    clock.t += 1
    assert p.reroll("twitch", "a", cfg)


def test_second_use_waits_twice_as_long_and_cap_applies(tmp_path):
    clock = Clock()
    cfg = Config(random_cooldown_base=10, random_cooldown_max=30, random_global_base=0, random_global_max=0)
    p = make(tmp_path, clock, rolls=range(1, 50))
    assert p.reroll("twitch", "a", cfg)  # wait 10
    clock.t += 10
    assert p.reroll("twitch", "a", cfg)  # wait 20
    clock.t += 19
    assert p.reroll("twitch", "a", cfg) is None
    clock.t += 1
    assert p.reroll("twitch", "a", cfg)  # wait 30 (cap, not 40)
    clock.t += 29
    assert p.reroll("twitch", "a", cfg) is None
    clock.t += 1
    assert p.reroll("twitch", "a", cfg)


def test_streak_resets_after_a_quiet_minute(tmp_path):
    clock = Clock()
    cfg = Config(random_cooldown_base=10, random_cooldown_max=300, random_global_base=0, random_global_max=0)
    p = make(tmp_path, clock, rolls=range(1, 50))
    p.reroll("twitch", "a", cfg)
    clock.t += 10
    p.reroll("twitch", "a", cfg)  # wait 20
    clock.t += 20 + 61  # a full quiet minute after the wait ended
    assert p.reroll("twitch", "a", cfg)  # back to wait 10
    clock.t += 10
    assert p.reroll("twitch", "a", cfg)


def test_global_wait_blocks_other_viewers_and_grows(tmp_path):
    clock = Clock()
    cfg = Config(random_cooldown_base=0, random_cooldown_max=0, random_global_base=2, random_global_max=60)
    p = make(tmp_path, clock, rolls=range(1, 50))
    assert p.reroll("twitch", "a", cfg)
    assert p.reroll("twitch", "b", cfg) is None  # global wait is 2 s
    clock.t += 2
    assert p.reroll("twitch", "b", cfg)  # next global wait is 4 s
    clock.t += 3
    assert p.reroll("twitch", "c", cfg) is None
    clock.t += 1
    assert p.reroll("twitch", "c", cfg)


def test_blocked_by_global_does_not_charge_the_viewer(tmp_path):
    clock = Clock()
    cfg = Config(random_cooldown_base=100, random_cooldown_max=300, random_global_base=2, random_global_max=60)
    p = make(tmp_path, clock, rolls=range(1, 50))
    assert p.reroll("twitch", "a", cfg)
    assert p.reroll("twitch", "b", cfg) is None
    clock.t += 2
    assert p.reroll("twitch", "b", cfg)  # b was never charged by the blocked try


def test_slots_survive_a_restart(tmp_path):
    p = make(tmp_path, rolls=[4242])
    p.reroll("twitch", "Alice", CFG)
    assert json.loads((tmp_path / "viewer_heroes.json").read_text("utf-8")) == {"twitch:alice": 4242}
    assert make(tmp_path).slot("twitch", "alice") == 4242


def test_damaged_file_starts_empty(tmp_path):
    (tmp_path / "viewer_heroes.json").write_text("{not json", encoding="utf-8")
    assert make(tmp_path).slot("twitch", "a") == slot_for("twitch", "a")


def test_unwritable_path_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    p = HeroPicker(blocker / "viewer_heroes.json", Clock(), rng=lambda bits: 9)
    assert p.reroll("twitch", "a", CFG) == 9  # still works in memory
