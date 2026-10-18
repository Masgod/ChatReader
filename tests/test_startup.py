from chatreader import startup


def test_shortcut_path_in_startup_folder():
    assert str(startup.shortcut_path()).replace("\\", "/").endswith("Startup/ChatReader.lnk")


def test_enable_runs_powershell_once(tmp_path, monkeypatch):
    monkeypatch.setattr(startup, "shortcut_path", lambda: tmp_path / "ChatReader.lnk")
    calls = []
    startup.set_start_with_windows(True, tmp_path / "app", run=lambda *a, **k: calls.append(a))
    assert len(calls) == 1
    cmd = " ".join(map(str, calls[0][0]))
    assert "pythonw" in cmd and "-m chatreader" in cmd and str(tmp_path / "app") in cmd


def test_disable_removes_file_without_run(tmp_path, monkeypatch):
    lnk = tmp_path / "ChatReader.lnk"
    lnk.write_text("x")
    monkeypatch.setattr(startup, "shortcut_path", lambda: lnk)
    startup.set_start_with_windows(False, tmp_path, run=lambda *a, **k: 1 / 0)
    assert not lnk.exists()
