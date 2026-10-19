import threading
import time

from chatreader.config import Config, load_config, validate
from chatreader.player import Player


class GatedOutput:
    def __init__(self):
        self.ready = threading.Event()
        self.played = []

    def wait_connected(self, timeout):
        return self.ready.wait(timeout)

    def play(self, wav):
        self.played.append(wav)

    def stop(self):
        pass


def test_player_keeps_queue_until_overlay_connects():
    out, synthed = GatedOutput(), []
    p = Player(lambda t, l: synthed.append(t) or b"w", out, 5)
    p.start()
    p.submit("hi", "pt")
    time.sleep(0.3)
    assert synthed == [] and p.pending == 1
    out.ready.set()
    deadline = time.time() + 3
    while not out.played and time.time() < deadline:
        time.sleep(0.02)
    p.shutdown()
    assert out.played == [b"w"]


def test_validate_rejects_bad_numbers_and_voice_names():
    errs = validate(Config(max_chars=0, repeat_window=-1, voice_pt="../x"))
    assert len(errs) == 3


def test_load_config_drops_wrong_types_and_rejects_bad_values(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('queue_size = "x"\nmax_chars = 50\n', encoding="utf-8")
    cfg = load_config(path)
    assert cfg.queue_size == 20 and cfg.max_chars == 50
    path.write_text("repeat_window = -1\n", encoding="utf-8")
    assert load_config(path).repeat_window == 5 and (tmp_path / "config.toml.bad").exists()
