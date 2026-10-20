"""Start-with-Windows through the per-user registry Run key."""
import os
import subprocess
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # not Windows; set_start_with_windows needs an injected registry then
    winreg = None

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ChatReader"


def shortcut_path() -> Path:
    """The Startup-folder shortcut earlier versions made; removed so users are migrated."""
    return (Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Startup" / "ChatReader.lnk")


def _pythonw() -> Path:
    exe = Path(sys.executable)
    return exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe


def startup_command(app_dir: Path, frozen: bool, executable: str) -> str:
    """The Run-key command line. list2cmdline quotes only where needed and keeps a trailing backslash safe."""
    args = [executable, "--home", str(app_dir.resolve())] if frozen else [executable, "-m", "chatreader", "--home", str(app_dir.resolve())]
    return subprocess.list2cmdline(args)


def set_start_with_windows(enabled: bool, app_dir: Path, reg=winreg, frozen: bool | None = None,
                           executable: str | None = None) -> None:
    if enabled:
        frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        exe = executable or (sys.executable if frozen else str(_pythonw()))
        with reg.CreateKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, startup_command(app_dir, frozen, exe))
    else:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                reg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass  # never enabled
    shortcut_path().unlink(missing_ok=True)  # only after the registry accepted the change
