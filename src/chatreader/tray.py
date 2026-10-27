import subprocess
import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw

REFRESH_SECONDS = 3


def _image() -> Image.Image:
    """Voice bubble: white chat bubble with sound bars on a purple tile (drawn at 4x, 64-unit grid)."""
    k = 4
    img = Image.new("RGBA", (64 * k, 64 * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    purple, white = (145, 70, 255, 255), (255, 255, 255, 255)
    box = lambda *c: tuple(v * k for v in c)  # noqa: E731
    d.rounded_rectangle(box(0, 0, 63.9, 63.9), 14 * k, fill=purple)
    d.rounded_rectangle(box(10, 12, 54, 44), 8 * k, fill=white)
    d.polygon([(20 * k, 43 * k), (34 * k, 43 * k), (20 * k, 55 * k)], fill=white)
    for x, top, bottom in ((22, 23, 33), (29.5, 18, 38), (37, 21, 35)):
        d.rounded_rectangle(box(x, top, x + 5, bottom), 2.5 * k, fill=purple)
    return img


def _tooltip(controller) -> str:
    s = controller.status()
    return "ChatReader | " + " | ".join(f"{k}: {v}" for k, v in s.items())[:110]


def build_icon(controller, settings_url: str, overlay_url: str, quit_cb, restart_cb=None) -> pystray.Icon:
    toggle = lambda icon, item: controller.resume() if controller.paused else controller.pause()  # noqa: E731
    copy = lambda icon, item: subprocess.run(["clip"], input=overlay_url, text=True, check=False, creationflags=0x08000000)  # noqa: E731
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: "Resume" if controller.paused else "Pause", toggle),
        pystray.MenuItem("Skip current", lambda icon, item: controller.skip()),
        pystray.MenuItem("Settings...", lambda icon, item: webbrowser.open(settings_url)),
        pystray.MenuItem("Copy overlay URL", copy),
        *([pystray.MenuItem("Restart", lambda icon, item: restart_cb())] if restart_cb else []),
        pystray.MenuItem("Quit", lambda icon, item: quit_cb()),
    )
    icon = pystray.Icon("chatreader", _image(), _tooltip(controller), menu)

    def refresh() -> None:
        while True:
            try:
                icon.title = _tooltip(controller)
            except Exception:
                pass
            threading.Event().wait(REFRESH_SECONDS)

    threading.Thread(target=refresh, daemon=True).start()
    return icon
