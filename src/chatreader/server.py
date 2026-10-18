import asyncio
import io
import struct
import threading
import time
import wave
from dataclasses import asdict, fields
from importlib import resources
from typing import Callable

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from chatreader.config import Config, normalize, validate

READY_TIMEOUT = 5.0  # seconds run_server waits for uvicorn to start listening
EXTRA_WAIT = 2.0  # seconds added to the WAV duration before play() gives up


def _wav_seconds(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


class Hub:
    """Bridges worker-thread playback to the overlay WebSocket (structurally an Output)."""

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._done = threading.Event()
        self._seq = 0
        self._current = 0  # id of the in-flight clip; "done" for any other id is stale

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def _send(self, coro_fn) -> bool:
        ws, loop = self._ws, self._loop
        if ws is None or loop is None:
            return False
        try:
            asyncio.run_coroutine_threadsafe(coro_fn(ws), loop).result(5)
            return True
        except Exception:
            return False

    def play(self, wav: bytes) -> None:
        self._seq += 1
        clip = self._current = self._seq
        self._done.clear()
        # wire format: 4-byte big-endian clip id, then the WAV; overlay replies "done:<id>"
        if self._send(lambda ws: ws.send_bytes(struct.pack(">I", clip) + wav)):
            self._done.wait(_wav_seconds(wav) + EXTRA_WAIT)

    def stop(self) -> None:
        self._send(lambda ws: ws.send_text("stop"))
        self._done.set()

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        self._ws, self._loop = ws, asyncio.get_running_loop()
        try:
            while True:
                msg = await ws.receive_text()
                if msg == f"done:{self._current}":
                    self._done.set()
        except WebSocketDisconnect:
            pass
        finally:
            if self._ws is ws:
                self._ws = None
                self._done.set()


def _page(name: str) -> HTMLResponse:
    return HTMLResponse((resources.files("chatreader") / "web" / name).read_text("utf-8"))


def _type_errors(body) -> list[str]:
    if not isinstance(body, dict):
        return ["body must be a JSON object"]
    errors = []
    for f in fields(Config):
        default = getattr(Config(), f.name)
        v = body.get(f.name)
        if f.name not in body:
            errors.append(f"{f.name} is required")
        elif isinstance(default, list):
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errors.append(f"{f.name} must be a list of strings")
        elif type(v) is not type(default):  # exact type: bool is not int
            errors.append(f"{f.name} must be {type(default).__name__}")
    return errors


def create_app(
    get_config: Callable[[], Config],
    apply_config: Callable[[Config], None],
    hub: Hub,
    speak_test: Callable[[str], None],
) -> FastAPI:
    app = FastAPI()

    @app.get("/overlay")
    def overlay():
        return _page("overlay.html")

    @app.get("/settings")
    def settings():
        return _page("settings.html")

    @app.get("/api/config")
    def read_config():
        return asdict(get_config())

    @app.put("/api/config")
    async def write_config(request: Request):
        try:
            body = await request.json()
        except ValueError:
            body = None
        errors = _type_errors(body)
        if not errors:
            cfg = normalize(Config(**{f.name: body[f.name] for f in fields(Config)}))
            errors = validate(cfg)
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        try:
            apply_config(cfg)
        except Exception as e:
            return JSONResponse({"errors": [f"could not apply settings: {e}"]}, status_code=500)
        return {"ok": True}

    @app.post("/api/test")
    async def test_voice(request: Request):
        body = await request.json()
        speak_test(str(body.get("text", "")))
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await hub.serve(ws)

    return app


def run_server(app: FastAPI, port: int) -> Callable[[], None]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + READY_TIMEOUT
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            server.should_exit = True
            raise RuntimeError(f"could not start server on port {port} (port in use?)")
        time.sleep(0.02)

    def shutdown() -> None:
        server.should_exit = True
        thread.join(5)

    return shutdown
