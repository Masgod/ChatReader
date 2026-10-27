import contextlib
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from chatreader.config import Config
from chatreader.server import Hub, ViewHub, create_app


def connect(client):
    return client.websocket_connect("/ws/view", headers={"host": "127.0.0.1"})  # LocalOnly checks the Host header


def wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out waiting for condition"
        time.sleep(0.005)


@pytest.fixture
def env():
    view = ViewHub()
    app = create_app(lambda: Config(), lambda c: None, Hub(), lambda t, lang="": None, lambda: {}, lambda a: None, view=view)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, view


def item(id_=7, view=None):
    return SimpleNamespace(id=id_, view=view)


def test_hello_frame_on_connect(env):
    client, view = env
    with connect(client) as ws:
        assert ws.receive_json() == {"t": "hello", "v": 1}


def test_broadcast_reaches_every_client(env):
    client, view = env
    with connect(client) as a, connect(client) as b:
        a.receive_json(), b.receive_json()
        wait_for(lambda: view.client_count == 2)
        view.broadcast({"t": "config"})
        assert a.receive_json() == {"t": "config"} and b.receive_json() == {"t": "config"}


def test_broadcast_with_no_clients_is_a_noop(env):
    _, view = env
    view.broadcast({"t": "config"})
    assert view.client_count == 0


def test_ninth_client_is_refused(env):
    client, view = env
    with contextlib.ExitStack() as stack:
        for _ in range(ViewHub.MAX_CLIENTS):
            stack.enter_context(connect(client)).receive_json()
        wait_for(lambda: view.client_count == ViewHub.MAX_CLIENTS)
        with pytest.raises(WebSocketDisconnect):
            with connect(client):
                pass


def test_dead_client_is_dropped_and_the_other_still_receives(env):
    client, view = env
    with connect(client) as keep:
        keep.receive_json()
        with connect(client) as gone:
            gone.receive_json()
            wait_for(lambda: view.client_count == 2)
        wait_for(lambda: view.client_count == 1)
        view.broadcast({"t": "config"})
        assert keep.receive_json() == {"t": "config"}


def test_client_messages_are_ignored(env):
    client, view = env
    with connect(client) as ws:
        ws.receive_json()
        ws.send_text("hello?")
        wait_for(lambda: view.client_count == 1)
        view.broadcast({"t": "config"})
        assert ws.receive_json() == {"t": "config"}


def test_on_start_then_played_sends_start_and_end(env):
    client, view = env
    with connect(client) as ws:
        ws.receive_json()
        wait_for(lambda: view.client_count == 1)
        view.on_start(item(7, {"user": "a", "text": "oi", "kind": "chat"}))
        assert ws.receive_json() == {"t": "start", "id": 7, "user": "a", "text": "oi", "kind": "chat"}
        view.on_event(item(7), "played")
        assert ws.receive_json() == {"t": "end", "id": 7, "outcome": "played"}


def test_skipped_started_item_sends_end_skipped(env):
    client, view = env
    with connect(client) as ws:
        ws.receive_json()
        wait_for(lambda: view.client_count == 1)
        view.on_start(item(3, {"user": "a"}))
        ws.receive_json()
        view.on_event(item(3), "skipped")
        assert ws.receive_json() == {"t": "end", "id": 3, "outcome": "skipped"}


def test_item_without_view_sends_nothing(env):
    client, view = env
    with connect(client) as ws:
        ws.receive_json()
        wait_for(lambda: view.client_count == 1)
        view.on_start(item(1, None))
        view.on_event(item(1), "played")
        view.broadcast({"t": "config"})
        assert ws.receive_json() == {"t": "config"}  # nothing came before it


@pytest.mark.parametrize("outcome", ["removed", "dropped"])
def test_removed_or_dropped_item_never_sends_end(env, outcome):
    client, view = env
    with connect(client) as ws:
        ws.receive_json()
        wait_for(lambda: view.client_count == 1)
        view.on_start(item(2, {"user": "a"}))
        ws.receive_json()
        view.on_event(item(2), outcome)
        view.broadcast({"t": "config"})
        assert ws.receive_json() == {"t": "config"}


def test_end_without_start_is_ignored(env):
    client, view = env
    with connect(client) as ws:
        ws.receive_json()
        wait_for(lambda: view.client_count == 1)
        view.on_event(item(9), "played")
        view.broadcast({"t": "config"})
        assert ws.receive_json() == {"t": "config"}
