"""Where the app keeps its files, plus the command-line options that move it."""
import argparse
import os
import sys
from pathlib import Path


def app_dir(home=None, env=os.environ, frozen=None, cwd=os.getcwd) -> Path:
    """--home, then CHATREADER_HOME, then %APPDATA%/ChatReader when built, else the current folder."""
    if home:
        return Path(home)
    if env.get("CHATREADER_HOME"):
        return Path(env["CHATREADER_HOME"])
    if getattr(sys, "frozen", False) if frozen is None else frozen:
        path = Path(env["APPDATA"]) / "ChatReader"
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(cwd())


def ensure_streams(log_stream) -> None:
    """A windowless build has no stdout/stderr; point them at the log so nothing that prints can crash."""
    if sys.stdout is None:
        sys.stdout = log_stream
    if sys.stderr is None:
        sys.stderr = log_stream


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="chatreader")
    p.add_argument("--home", help="folder for config, log and voices")
    p.add_argument("--check", action="store_true", help="run a headless self test and exit")
    return p.parse_args(argv)
