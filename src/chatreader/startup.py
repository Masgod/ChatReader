"""Start-with-Windows via a shortcut in the user's Startup folder."""
import os
import re
import subprocess
import sys
from pathlib import Path


def shortcut_path() -> Path:
    return (Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Startup" / "ChatReader.lnk")


def _pythonw() -> Path:
    exe = Path(sys.executable)
    return exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe


def _q(p) -> str:
    # PowerShell treats all four single-quote variants as quote characters
    return re.sub("['‘’‚‛]", lambda m: m.group() * 2, str(p))


def set_start_with_windows(enabled: bool, app_dir: Path, run=subprocess.run) -> None:
    lnk = shortcut_path()
    if not enabled:
        lnk.unlink(missing_ok=True)
        return
    lnk.parent.mkdir(parents=True, exist_ok=True)
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$s.TargetPath='%s';$s.Arguments='-m chatreader';"
        "$s.WorkingDirectory='%s';$s.Save()"
    ) % tuple(_q(p) for p in (lnk, _pythonw(), app_dir))
    # the venv's pythonw.exe with -m chatreader; the working dir becomes the app folder
    run(["powershell", "-NoProfile", "-Command", ps], check=True, creationflags=0x08000000)
