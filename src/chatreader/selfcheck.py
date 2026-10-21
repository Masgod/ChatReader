"""`--check`: prove a build works headless. Prints one JSON line and returns an exit code."""
import importlib
import json
import os
import socket
import urllib.request
from pathlib import Path

from chatreader.paths import ensure_streams

MODULES = [
    "chatreader.main", "chatreader.server", "chatreader.controller", "chatreader.player", "chatreader.tts",
    "chatreader.lang", "chatreader.filters", "chatreader.events", "chatreader.startup", "chatreader.tray",
    "chatreader.sources.twitch", "chatreader.sources.youtube", "uvicorn", "pystray", "PIL", "kokoro_onnx",
]


def imports_step(app: Path) -> str:
    for name in MODULES:
        importlib.import_module(name)
    return f"{len(MODULES)} modules"


def language_step(app: Path) -> str:
    from chatreader.lang import detect_lang

    got = detect_lang("this is a simple english sentence about the weather", ["pt", "en"], "pt")
    if got != "en":
        raise RuntimeError(f"detected {got!r}, expected 'en'")
    return "detector works"


def server_step(app: Path) -> str:
    from chatreader.config import Config
    from chatreader.server import Hub, create_app, run_server

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    stop = run_server(create_app(lambda: Config(), lambda c: None, Hub(), lambda t: None, lambda: {"ok": True}, lambda a: None), port)
    try:
        for path in ("/", "/static/app.js", "/api/status"):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
                if r.status != 200:
                    raise RuntimeError(f"{path} returned {r.status}")
    finally:
        stop()
    return "pages and api answer"


def synth_step(app: Path) -> str:
    from chatreader.config import Config
    from chatreader.tts import MODEL_FILE, VOICES_FILE, KokoroTTS

    voices = app / "voices"
    if not ((voices / MODEL_FILE).exists() and (voices / VOICES_FILE).exists()):
        return "skipped, no model downloaded yet"
    tts = KokoroTTS(voices, Config(), lambda m: None)
    if not tts.synth("hello", "en").startswith(b"RIFF"):
        raise RuntimeError("synthesis did not return a WAV")
    return "synthesized a phrase"


DEFAULT_STEPS = {"imports": imports_step, "language": language_step, "server": server_step, "synth": synth_step}


def run_check(app: Path, steps=None) -> tuple[int, dict]:
    ensure_streams(open(os.devnull, "w"))  # windowless exe: uvicorn and print need real streams
    results, ok = {}, True
    for name, fn in (steps or DEFAULT_STEPS).items():
        try:
            results[name] = f"ok: {fn(app)}"
        except Exception as e:
            ok = False
            results[name] = f"failed: {type(e).__name__}: {e}"
    return (0 if ok else 1), {"ok": ok, "steps": results}


def main_check(app: Path, steps=None) -> int:
    code, result = run_check(app, steps)
    line = json.dumps(result)
    print(line)
    try:  # a windowless exe has no console to show the line on, so keep a copy to read
        app.mkdir(parents=True, exist_ok=True)
        (app / "check-result.json").write_text(line + "\n", encoding="utf-8")
    except OSError:
        pass
    return code
