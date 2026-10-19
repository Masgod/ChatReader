import sys
from pathlib import Path

from chatreader.paths import app_dir, ensure_streams, parse_args


def test_home_option_wins(tmp_path):
    env = {"CHATREADER_HOME": str(tmp_path / "env"), "APPDATA": str(tmp_path / "ad")}
    assert app_dir(str(tmp_path / "opt"), env, frozen=True) == tmp_path / "opt"


def test_env_override(tmp_path):
    env = {"CHATREADER_HOME": str(tmp_path / "env"), "APPDATA": str(tmp_path / "ad")}
    assert app_dir(None, env, frozen=True) == tmp_path / "env"


def test_frozen_uses_appdata_and_creates_it(tmp_path):
    got = app_dir(None, {"APPDATA": str(tmp_path)}, frozen=True)
    assert got == tmp_path / "ChatReader" and got.is_dir()


def test_plain_run_uses_cwd(tmp_path):
    assert app_dir(None, {}, frozen=False, cwd=lambda: str(tmp_path)) == tmp_path


def test_ensure_streams_replaces_none(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    with open(tmp_path / "log.txt", "a", encoding="utf-8") as f:
        ensure_streams(f)
        print("x")
        sys.stderr.write("y")
        assert sys.stdout is f and sys.stderr is f


def test_ensure_streams_leaves_real_streams(monkeypatch, tmp_path):
    out, err = sys.stdout, sys.stderr
    with open(tmp_path / "log.txt", "a", encoding="utf-8") as f:
        ensure_streams(f)
    assert sys.stdout is out and sys.stderr is err


def test_parse_args():
    a = parse_args(["--home", r"C:\x y", "--check"])
    assert a.home == r"C:\x y" and a.check is True
    b = parse_args([])
    assert b.home is None and b.check is False
