import logging
import os
import socket
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from chatreader import startup, tray
from chatreader.config import Config, load_config, save_config
from chatreader.controller import Controller
from chatreader.player import Player
from chatreader.server import Hub, create_app, run_server
from chatreader.sources.twitch import run_twitch
from chatreader.sources.youtube import run_youtube
from chatreader.tts import PiperTTS, ensure_voices


def _setup_logging(app: Path, debug: bool) -> None:
    handler = RotatingFileHandler(app / "chatreader.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if debug else logging.ERROR)


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def main() -> None:
    app = Path(os.environ.get("CHATREADER_HOME") or os.getcwd())
    app.mkdir(parents=True, exist_ok=True)
    cfg_path = app / "config.toml"
    first_run = not cfg_path.exists()
    cfg = load_config(cfg_path)
    _setup_logging(app, cfg.debug)
    log = logging.getLogger("chatreader")

    icon_ref: list = []
    notify = lambda msg: icon_ref and icon_ref[0].notify(msg, "ChatReader")  # noqa: E731

    hub = Hub()
    voices = app / "voices"
    tts = PiperTTS(voices, cfg, on_warning=lambda m: (log.warning(m), notify(m)))
    player = Player(tts.synth, hub, cfg.queue_size)
    controller = Controller(cfg, player, tts, {"twitch": run_twitch, "youtube": run_youtube})

    def apply_config(new: Config) -> None:
        old = controller.cfg
        controller.apply_config(new)
        save_config(cfg_path, new)
        logging.getLogger().setLevel(logging.DEBUG if new.debug else logging.ERROR)
        if new.start_with_windows != old.start_with_windows:
            startup.set_start_with_windows(new.start_with_windows, app)

    base = f"http://127.0.0.1:{cfg.port}"
    stop_server = lambda: None  # noqa: E731

    def quit_cb() -> None:
        icon.stop()

    icon = tray.build_icon(controller, f"{base}/settings", f"{base}/overlay", quit_cb)
    icon_ref.append(icon)

    def boot(icon) -> None:
        nonlocal stop_server
        icon.visible = True
        if not _port_free(cfg.port):
            icon.notify(f"Port {cfg.port} is already in use. ChatReader will exit.", "ChatReader")
            threading.Event().wait(5)  # let the toast show before the icon disappears
            icon.stop()
            return
        failed = ensure_voices(voices, [cfg.voice_pt, cfg.voice_en])
        if failed:
            icon.notify("Could not download voices: " + ", ".join(failed), "ChatReader")
        tts.reload(cfg)
        player.start()
        controller.start()
        app_obj = create_app(lambda: controller.cfg, apply_config, hub, controller.speak_test)
        stop_server = run_server(app_obj, cfg.port)
        if first_run:
            webbrowser.open(f"{base}/settings")

    # voice download can take a while, so boot runs off the main thread once the icon is up
    icon.run(setup=lambda i: threading.Thread(target=boot, args=(i,), daemon=True).start())
    stop_server()
    controller.shutdown()
    sys.exit(0)
