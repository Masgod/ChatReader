import sys
import tomllib
from pathlib import Path

from chatreader import instance, main
from chatreader.paths import app_dir, parse_args

DEFAULT_PORT = 8765


def read_port(app: Path) -> int:
    """The configured port, read without touching the file (load_config would rewrite a bad one)."""
    try:
        port = tomllib.loads((app / "config.toml").read_text(encoding="utf-8")).get("port", DEFAULT_PORT)
        return port if type(port) is int and 1 <= port <= 65535 else DEFAULT_PORT
    except (OSError, ValueError):
        return DEFAULT_PORT


def run(argv, acquire=instance.acquire, open_running=instance.open_running, start=main.main) -> int:
    args = parse_args(argv)
    if not acquire():
        open_running(read_port(app_dir(args.home)))
        return 0
    start(args.home)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
