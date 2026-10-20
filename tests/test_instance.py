from chatreader import instance
from chatreader.__main__ import read_port, run


def test_first_launch_acquires():
    assert instance.acquire(create_mutex=lambda name: (object(), False)) is True


def test_second_launch_does_not_acquire():
    assert instance.acquire(create_mutex=lambda name: (object(), True)) is False


def test_open_running_opens_root_url():
    urls = []
    instance.open_running(8765, open_url=urls.append)
    assert urls == ["http://127.0.0.1:8765/"]


def test_main_second_launch_opens_page_and_exits(tmp_path):
    calls = []
    code = run(["--home", str(tmp_path)], acquire=lambda: False, open_running=lambda port: calls.append(("open", port)),
               start=lambda home: calls.append(("start", home)))
    assert code == 0 and calls == [("open", 8765)]


def test_main_first_launch_starts(tmp_path):
    calls = []
    code = run(["--home", str(tmp_path)], acquire=lambda: True, open_running=lambda port: calls.append("open"),
               start=lambda home: calls.append(("start", home)))
    assert code == 0 and calls == [("start", str(tmp_path))]


def test_port_read_from_config(tmp_path):
    assert read_port(tmp_path) == 8765  # no file
    (tmp_path / "config.toml").write_text("port = 9001\n", encoding="utf-8")
    assert read_port(tmp_path) == 9001
    (tmp_path / "config.toml").write_text("not toml [[[", encoding="utf-8")
    assert read_port(tmp_path) == 8765
    (tmp_path / "config.toml").write_text('port = "x"\n', encoding="utf-8")
    assert read_port(tmp_path) == 8765
    assert not (tmp_path / "config.toml.bad").exists()  # reading must never rename or rewrite the file
