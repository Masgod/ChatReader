import logging
import sys
import threading
import webbrowser
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path

from chatreader import startup, tray
from chatreader.config import Config, load_config, save_config
from chatreader.controller import Controller
from chatreader.events import EventLog, LogMirror
from chatreader.paths import app_dir, ensure_streams, stdio_stream
from chatreader.player import Player
from chatreader.server import Hub, ViewHub, create_app, run_server
from chatreader.sources.twitch import run_twitch
from chatreader.sources.youtube import run_youtube
from chatreader.tts import KokoroTTS, ensure_models


def _setup_logging(app: Path, debug: bool) -> None:
    handler = RotatingFileHandler(app / "chatreader.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if debug else logging.WARNING)


def make_apply(controller, path: Path, set_startup, save=save_config, on_saved=None):
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
            logging.getLogger().setLevel(logging.DEBUG if new.debug else logging.WARNING)
            if on_saved is not None:
                try:
                    on_saved()
                except Exception:
                    logging.getLogger("chatreader").exception("after-save hook failed")

    return apply_config


def make_toggle(controller, apply_config=None):
    """Build the POST /api/toggle callback (only 'debug'): saves through the normal apply path."""
    apply = apply_config or controller.apply_config

    def toggle(name: str, value: bool) -> None:
        apply(replace(controller.cfg, **{name: value}))

    return toggle


def _install_excepthooks() -> None:
    log = logging.getLogger("chatreader")
    sys.excepthook = lambda *exc: log.error("uncaught exception", exc_info=exc)
    threading.excepthook = lambda a: log.error(
        "uncaught exception in thread", exc_info=(a.exc_type, a.exc_value, a.exc_traceback)
    )


def main(home: str | None = None) -> None:
    app = app_dir(home)
    app.mkdir(parents=True, exist_ok=True)
    ensure_streams(stdio_stream(app))
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
    events = EventLog()
    logging.getLogger().addHandler(LogMirror(events))
    controller = Controller(cfg, None, tts, {"twitch": run_twitch, "youtube": run_youtube}, events)
    view = ViewHub()

    def on_item_event(item, outcome: str) -> None:
        controller.record_item_event(item, outcome)
        try:
            view.on_event(item, outcome)  # the console record above must happen even if the overlay fails
        except Exception:
            log.exception("chat overlay event failed")

    player = Player(tts.synth, hub, cfg.queue_size, on_event=on_item_event, on_start=view.on_start)
    controller._player = player  # the player's callback needs the controller, so wire it after both exist
    apply_config = make_apply(
        controller, cfg_path, lambda on: startup.set_start_with_windows(on, app),
        on_saved=lambda: view.broadcast({"t": "config"}),
    )

    base = f"http://127.0.0.1:{cfg.port}"
    stop_server = lambda: None  # noqa: E731
    icon = tray.build_icon(controller, f"{base}/settings", f"{base}/overlay", lambda: icon.stop())
    icon_ref.append(icon)

    def boot(icon) -> None:
        nonlocal stop_server
        icon.visible = True
        try:
            app_obj = create_app(
                lambda: controller.cfg, apply_config, hub, controller.speak_test,
                controller.snapshot, lambda a: icon.stop() if a == "quit" else getattr(controller, a)(),
                queue=player, events=events, toggle=make_toggle(controller, apply_config), voices=tts.voices,
                view=view, themes_dir=app / "themes",
            )
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
