"""Only one ChatReader at a time; a second launch just opens the running one's page."""
import webbrowser

_ERROR_ALREADY_EXISTS = 183
_held = []  # the mutex handle must outlive the call or Windows frees it


def _create_mutex(name: str):
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, name)
    return handle, kernel32.GetLastError() == _ERROR_ALREADY_EXISTS


def acquire(name: str = r"Local\ChatReader", create_mutex=_create_mutex) -> bool:
    """True when this process is the first instance."""
    handle, exists = create_mutex(name)
    _held.append(handle)
    return not exists


def open_running(port: int, open_url=webbrowser.open) -> None:
    open_url(f"http://127.0.0.1:{port}/")
