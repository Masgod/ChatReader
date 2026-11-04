import sys
import time
import tomllib
from pathlib import Path

from chatreader import instance, main, restart, selfcheck
from chatreader.paths import app_dir, parse_args

DEFAULT_PORT = 8765


def read_port(app: Path) -> int:
    """The configured port, read without touching the file (load_config would rewrite a bad one)."""
    try:
        port = tomllib.loads((app / "config.toml").read_text(encoding="utf-8")).get("port", DEFAULT_PORT)
        return port if type(port) is int and 1 <= port <= 65535 else DEFAULT_PORT
    except (OSError, ValueError):
        return DEFAULT_PORT


def run(argv, acquire=instance.acquire, open_running=instance.open_running, start=main.main,
        check=selfcheck.main_check, wait_previous=restart.wait_for_previous, sleep=time.sleep) -> int:
    args = parse_args(argv)
    if args.check:  # before the single-instance test so a check works while the app runs
        return check(app_dir(args.home))
    restarted = wait_previous()  # after a restart, the old copy still holds the lock and the port until it exits
    got = acquire()
    for _ in range(int(restart.WAIT_SECONDS * 4) if restarted else 0):  # the old copy outlived the wait: keep trying, never start two
        if got:
            break
        sleep(0.25)
        got = acquire()
    if not got:
        open_running(read_port(app_dir(args.home)))
        return 0
    start(args.home)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
