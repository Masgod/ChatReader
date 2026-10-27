import os

import pytest

from chatreader import restart
from chatreader.__main__ import run
from chatreader.main import make_control


def test_source_run_is_relaunched_with_the_same_command_line():
    orig = ["C:/py/python.exe", "-m", "chatreader", "--home", "C:/data"]
    assert restart.relaunch_command(orig, frozen=False, executable="C:/py/python.exe", argv=["x"]) == orig


def test_frozen_build_is_relaunched_through_its_exe_and_arguments():
    cmd = restart.relaunch_command(["ignored"], frozen=True, executable="C:/app/ChatReader.exe", argv=["ChatReader.exe", "--home", "C:/d"])
    assert cmd == ["C:/app/ChatReader.exe", "--home", "C:/d"]


def test_spawn_passes_the_old_pid_and_detaches():
    calls = []
    restart.spawn(["py", "-m", "chatreader"], popen=lambda cmd, **kw: calls.append((cmd, kw)), env={"A": "1"}, pid=4242, cwd="C:/w")
    cmd, kw = calls[0]
    assert cmd == ["py", "-m", "chatreader"]
    assert kw["env"] == {"A": "1", restart.ENV_PID: "4242"}
    assert kw["cwd"] == "C:/w" and kw["close_fds"] is True and kw["creationflags"] & 0x00000008  # DETACHED_PROCESS


def test_wait_for_previous_waits_for_that_pid_then_clears_the_marker():
    seen, env = [], {restart.ENV_PID: "77", "X": "y"}
    restart.wait_for_previous(env, wait=lambda pid, seconds: seen.append((pid, seconds)))
    assert seen == [(77, restart.WAIT_SECONDS)] and restart.ENV_PID not in env and env["X"] == "y"


@pytest.mark.parametrize("value", ["", "abc", "-5", "0"])
def test_wait_for_previous_ignores_a_missing_or_bad_marker(value):
    seen, env = [], {restart.ENV_PID: value} if value != "" else {}
    restart.wait_for_previous(env, wait=lambda pid, seconds: seen.append(pid))
    assert seen == [] and restart.ENV_PID not in env


def test_wait_for_pid_returns_at_once_when_the_process_is_already_gone():
    assert restart.wait_for_pid(2**22 + 12345, 1.0) is None  # no such process: must not hang or raise


def test_run_waits_for_the_previous_instance_before_taking_the_single_instance_lock():
    order = []
    run([], acquire=lambda: order.append("acquire") or True, open_running=lambda p: None, start=lambda home: None,
        check=lambda app: 0, wait_previous=lambda: order.append("wait"))
    assert order == ["wait", "acquire"]


class FakeIcon:
    def __init__(self):
        self.stopped = 0

    def stop(self):
        self.stopped += 1


class FakeController:
    def __init__(self):
        self.calls = []

    def skip(self):
        self.calls.append("skip")


def test_control_restart_relaunches_then_stops_the_icon():
    icon, order = FakeIcon(), []
    control = make_control(FakeController(), lambda: icon, relaunch=lambda: order.append("spawn"))
    control("restart")
    assert order == ["spawn"] and icon.stopped == 1


def test_control_restart_that_fails_to_spawn_keeps_the_app_running():
    icon = FakeIcon()

    def boom():
        raise OSError("cannot start")

    control = make_control(FakeController(), lambda: icon, relaunch=boom)
    control("restart")
    assert icon.stopped == 0


def test_control_quit_and_controller_actions_still_work():
    icon, ctl = FakeIcon(), FakeController()
    control = make_control(ctl, lambda: icon, relaunch=lambda: None)
    control("quit")
    control("skip")
    assert icon.stopped == 1 and ctl.calls == ["skip"]
