import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)


def run_with_backoff(
    fn: Callable[[], object],
    stop: threading.Event,
    on_status: Callable[[str], None],
    sleep: Callable[[float], object] | None = None,
    max_failures: int | None = None,
) -> None:
    """Call fn until stop is set, retrying with exponential backoff (1..30 s).

    fn returns a truthy value when it delivered at least one message; that
    resets the delay. Raising or returning falsy counts as a failure.
    """
    wait = sleep or stop.wait
    delay = 1
    failures = 0
    while not stop.is_set():
        try:
            ok = bool(fn())
        except Exception:
            log.warning("source call failed; retrying", exc_info=True)
            ok = False
        if stop.is_set():
            return
        if ok:
            delay, failures = 1, 0
        else:
            failures += 1
            if max_failures is not None and failures >= max_failures:
                on_status("failed")
                return
        on_status("reconnecting")
        wait(delay)
        delay = min(delay * 2, 30)
