import subprocess
import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw

REFRESH_SECONDS = 3


def _image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((4, 4, 60, 60), fill=(145, 70, 255, 255))
    return img


def _tooltip(controller) -> str:
    s = controller.status()
    return "ChatReader | " + " | ".join(f"{k}: {v}" for k, v in s.items())[:110]


def build_icon(controller, settings_url: str, overlay_url: str, quit_cb) -> pystray.Icon:
    toggle = lambda icon, item: controller.resume() if controller._player.paused else controller.pause()  # noqa: E731
    copy = lambda icon, item: subprocess.run(["clip"], input=overlay_url, text=True, check=False)  # noqa: E731
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: "Resume" if controller._player.paused else "Pause", toggle),
        pystray.MenuItem("Skip current", lambda icon, item: controller.skip()),
        pystray.MenuItem("Settings...", lambda icon, item: webbrowser.open(settings_url)),
        pystray.MenuItem("Copy overlay URL", copy),
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
