"""Restart the app: start a new copy that waits for this one to exit, then quit this one.

The new process cannot simply start first: the single-instance lock and the port are held until this process ends.
"""
import os
import subprocess
import sys

ENV_PID = "CHATREADER_RESTART_PID"
WAIT_SECONDS = 20.0
_DETACHED_PROCESS = 0x00000008
_NEW_PROCESS_GROUP = 0x00000200
_SYNCHRONIZE = 0x00100000


def relaunch_command(orig_argv=None, frozen=None, executable=None, argv=None) -> list[str]:
    """The command line that starts this same app again, with the same --home and flags."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:  # a PyInstaller exe: sys.orig_argv names the bundled interpreter, so rebuild from the exe
        return [executable or sys.executable, *(sys.argv if argv is None else argv)[1:]]
    return list(sys.orig_argv if orig_argv is None else orig_argv)


def spawn(cmd: list[str], popen=subprocess.Popen, env=None, pid=None, cwd=None) -> None:
    """Start cmd detached from this process and console, telling it which pid to wait for."""
    env = dict(os.environ if env is None else env)
    env[ENV_PID] = str(os.getpid() if pid is None else pid)
    popen(cmd, env=env, cwd=cwd or os.getcwd(), close_fds=True, creationflags=_DETACHED_PROCESS | _NEW_PROCESS_GROUP,
          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def relaunch() -> None:
    spawn(relaunch_command())


def wait_for_pid(pid: int, seconds: float) -> None:
    """Block until the process ends, it is gone already, or the time is up."""
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:  # no such process: it has already exited
        return
    try:
        kernel32.WaitForSingleObject(ctypes.c_void_p(handle), int(seconds * 1000))
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def wait_for_previous(env=os.environ, wait=wait_for_pid) -> None:
    """At startup: if a restart started us, wait for the old copy to finish before taking the lock and the port."""
    raw = env.pop(ENV_PID, "")
    if raw.isdigit() and int(raw) > 0:
        wait(int(raw), WAIT_SECONDS)
