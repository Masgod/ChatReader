from dataclasses import replace

import pytest

from chatreader.config import Config
from chatreader.main import make_apply


class Ctl:
    def __init__(self):
        self.cfg = Config()
        self.applied = []

    def apply_config(self, new):
        self.applied.append(new)


def test_toggles_shortcut_only_when_flag_changes(tmp_path):
    ctl, toggles, saves = Ctl(), [], []
    apply = make_apply(ctl, tmp_path, toggles.append, save=lambda p, c: saves.append(c))
    apply(replace(ctl.cfg, queue_size=3))
    assert toggles == [] and len(ctl.applied) == 1 and len(saves) == 1
    apply(replace(ctl.cfg, start_with_windows=True))
    assert toggles == [True]


def test_failing_toggle_applies_and_saves_nothing(tmp_path):
    ctl, saves = Ctl(), []

    def boom(on):
        raise OSError("no powershell")

    apply = make_apply(ctl, tmp_path, boom, save=lambda p, c: saves.append(c))
    with pytest.raises(OSError):
        apply(replace(ctl.cfg, start_with_windows=True))
    assert ctl.applied == [] and saves == []


def test_make_apply_calls_on_saved_after_save(tmp_path):
    ctl, order = Ctl(), []
    apply = make_apply(ctl, tmp_path, lambda on: None, save=lambda p, c: order.append("save"), on_saved=lambda: order.append("saved"))
    apply(replace(ctl.cfg, queue_size=3))
    assert order == ["save", "saved"]


def test_make_apply_survives_a_failing_on_saved(tmp_path):
    ctl, saves = Ctl(), []

    def boom():
        raise RuntimeError("overlay gone")

    apply = make_apply(ctl, tmp_path, lambda on: None, save=lambda p, c: saves.append(c), on_saved=boom)
    apply(replace(ctl.cfg, queue_size=3))
    assert len(saves) == 1 and len(ctl.applied) == 1


def test_make_toggle_flips_debug_through_apply():
    from chatreader.main import make_toggle

    ctl = Ctl()
    toggle = make_toggle(ctl)
    toggle("debug", True)
    assert ctl.applied[-1].debug is True
