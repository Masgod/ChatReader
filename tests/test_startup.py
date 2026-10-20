from pathlib import Path

import pytest

from chatreader import startup

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class FakeReg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self, fail=None):
        self.values, self.fail = {}, fail

    def CreateKey(self, root, path):
        assert (root, path) == ("HKCU", RUN_KEY)
        if self.fail:
            raise self.fail
        return self

    OpenKey = lambda self, root, path, res, access: self.CreateKey(root, path)  # noqa: E731

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def SetValueEx(self, key, name, res, kind, value):
        self.values[name] = (kind, value)

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


@pytest.fixture
def lnk(tmp_path, monkeypatch):
    p = tmp_path / "ChatReader.lnk"
    monkeypatch.setattr(startup, "shortcut_path", lambda: p)
    return p


def test_shortcut_path_in_startup_folder(monkeypatch):
    monkeypatch.setenv("APPDATA", "C:/AppData")
    assert str(startup.shortcut_path()).replace("\\", "/").endswith("Startup/ChatReader.lnk")


def test_enable_writes_run_value_frozen(tmp_path, lnk):
    reg = FakeReg()
    startup.set_start_with_windows(True, tmp_path, reg=reg, frozen=True, executable=r"C:\Apps\Chat Reader\ChatReader.exe")
    assert reg.values["ChatReader"] == (1, r'"C:\Apps\Chat Reader\ChatReader.exe"')


def test_enable_source_command(tmp_path, lnk):
    reg = FakeReg()
    startup.set_start_with_windows(True, tmp_path / "app dir", reg=reg, frozen=False, executable=r"C:\py\pythonw.exe")
    assert reg.values["ChatReader"][1] == f'"C:\py\pythonw.exe" -m chatreader --home "{tmp_path / "app dir"}"'


def test_command_quotes_spaces_apostrophes_and_unicode():
    app = Path("C:/Users/Ana María's PC/Chat Reader")
    cmd = startup.startup_command(app, False, "C:/Py 3/pythonw.exe")
    assert cmd == f'"C:/Py 3/pythonw.exe" -m chatreader --home "{app}"'
    assert cmd.count('"') == 4


def test_disable_deletes_value_and_old_shortcut(tmp_path, lnk):
    lnk.write_text("x")
    reg = FakeReg()
    reg.values["ChatReader"] = (1, "x")
    startup.set_start_with_windows(False, tmp_path, reg=reg)
    assert "ChatReader" not in reg.values and not lnk.exists()


def test_disable_missing_value_is_not_an_error(tmp_path, lnk):
    startup.set_start_with_windows(False, tmp_path, reg=FakeReg())


def test_enable_removes_old_shortcut(tmp_path, lnk):
    lnk.write_text("x")
    startup.set_start_with_windows(True, tmp_path, reg=FakeReg(), frozen=True, executable="C:/a.exe")
    assert not lnk.exists()


def test_registry_error_propagates(tmp_path, lnk):
    with pytest.raises(PermissionError):
        startup.set_start_with_windows(True, tmp_path, reg=FakeReg(fail=PermissionError("policy")), frozen=True, executable="C:/a.exe")
