import logging
import os
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
from chatreader.tts import KokoroTTS, ensure_models


def _setup_logging(app: Path, debug: bool) -> None:
    handler = RotatingFileHandler(app / "chatreader.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if debug else logging.ERROR)


def make_apply(controller, path: Path, set_startup, save=save_config):
    """Build the PUT /api/config callback. The shortcut toggle runs first so a failure applies nothing."""

    lock = threading.Lock()  # saves run in worker threads, so serialize them

    def apply_config(new: Config) -> None:
        with lock:
            if new.start_with_windows != controller.cfg.start_with_windows:
                try:
                    set_startup(new.start_with_windows)
                except Exception:
                    logging.getLogger("chatreader").exception("startup shortcut failed")
                    raise
            controller.apply_config(new)
            save(path, new)
            logging.getLogger().setLevel(logging.DEBUG if new.debug else logging.ERROR)

    return apply_config


def _install_excepthooks() -> None:
    log = logging.getLogger("chatreader")
    sys.excepthook = lambda *exc: log.error("uncaught exception", exc_info=exc)
    threading.excepthook = lambda a: log.error(
        "uncaught exception in thread", exc_info=(a.exc_type, a.exc_value, a.exc_traceback)
    )


def main() -> None:
    app = Path(os.environ.get("CHATREADER_HOME") or os.getcwd())
    app.mkdir(parents=True, exist_ok=True)
    cfg_path = app / "config.toml"
    first_run = not cfg_path.exists()
    cfg = load_config(cfg_path)
    _setup_logging(app, cfg.debug)
    _install_excepthooks()
    log = logging.getLogger("chatreader")

    icon_ref: list = []
    notify = lambda msg: icon_ref and icon_ref[0].notify(msg, "ChatReader")  # noqa: E731

    hub = Hub()
    voices = app / "voices"
    tts = KokoroTTS(voices, cfg, on_warning=lambda m: (log.warning(m), notify(m)))
    player = Player(tts.synth, hub, cfg.queue_size)
    controller = Controller(cfg, player, tts, {"twitch": run_twitch, "youtube": run_youtube})
    apply_config = make_apply(
        controller, cfg_path, lambda on: startup.set_start_with_windows(on, app)
    )

    base = f"http://127.0.0.1:{cfg.port}"
    stop_server = lambda: None  # noqa: E731
    icon = tray.build_icon(controller, f"{base}/settings", f"{base}/overlay", lambda: icon.stop())
    icon_ref.append(icon)

    def boot(icon) -> None:
        nonlocal stop_server
        icon.visible = True
        try:
            app_obj = create_app(lambda: controller.cfg, apply_config, hub, controller.speak_test)
            stop_server = run_server(app_obj, cfg.port)  # raises if the port is taken
            if first_run:
                webbrowser.open(f"{base}/settings")
            failed = ensure_models(voices)
            if failed:
                icon.notify("Could not download model files: " + ", ".join(failed), "ChatReader")
            tts.reload(controller.cfg)
            player.start()
            controller.start()
        except Exception as e:
            log.exception("startup failed")
            icon.notify(f"Failed to start: {e}"[:200], "ChatReader")
            threading.Event().wait(5)  # let the toast show before the icon disappears
            icon.stop()

    # voice download can take a while, so boot runs off the main thread once the icon is up
    icon.run(setup=lambda i: threading.Thread(target=boot, args=(i,), daemon=True).start())
    stop_server()
    controller.shutdown()
    sys.exit(0)
