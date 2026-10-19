import io
import wave
from pathlib import Path

import numpy as np
import pytest

from chatreader.config import Config
from chatreader.tts import MODEL_FILE, VOICES_FILE, KokoroTTS, ensure_models


class FakeKokoro:
    def __init__(self):
        self.calls = []

    def get_voices(self):
        return ["pf_dora", "af_heart", "af_bella"]

    def create(self, text, voice, speed, lang):
        self.calls.append((text, voice, lang))
        self.speeds = getattr(self, "speeds", []) + [speed]
        return np.zeros(2400, dtype=np.float32), 24000


def _files(tmp_path):
    (tmp_path / MODEL_FILE).write_bytes(b"x")
    (tmp_path / VOICES_FILE).write_bytes(b"x")


def test_ensure_models_skips_existing_and_reports_failures(tmp_path):
    (tmp_path / MODEL_FILE).write_bytes(b"x")
    calls = []

    def download(url, dest):
        calls.append(dest.name)
        raise OSError("boom")

    assert ensure_models(tmp_path, download) == [VOICES_FILE]
    assert calls == [VOICES_FILE]


def test_synth_returns_wav_with_voice_and_language(tmp_path):
    _files(tmp_path)
    fake = FakeKokoro()
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: fake)
    data = tts.synth("oi", "pt")
    tts.synth("hi", "en")
    with wave.open(io.BytesIO(data)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 2400
    assert fake.calls == [("oi", "pf_dora", "pt-br"), ("hi", "af_heart", "en-us")]


def test_unknown_voice_is_skipped_with_warning(tmp_path):
    _files(tmp_path)
    warnings = []
    tts = KokoroTTS(tmp_path, Config(voice_pt="zz_nope"), warnings.append, loader=lambda m, v, t: FakeKokoro())
    assert any("zz_nope" in w for w in warnings)
    with pytest.raises(RuntimeError):
        tts.synth("oi", "pt")
    assert tts.synth("hi", "en").startswith(b"RIFF")


def test_missing_files_then_reload_after_download(tmp_path):
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: FakeKokoro())
    with pytest.raises(RuntimeError):
        tts.synth("oi", "pt")
    _files(tmp_path)
    tts.reload(Config())
    assert tts.synth("oi", "pt").startswith(b"RIFF")


def test_loader_failure_warns(tmp_path):
    _files(tmp_path)
    warnings = []

    def boom(m, v, t):
        raise RuntimeError("corrupt")

    KokoroTTS(tmp_path, Config(), warnings.append, loader=boom)
    assert any("corrupt" in w for w in warnings)


def test_model_state_transitions(tmp_path):
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: FakeKokoro())
    assert tts.model_state == "missing"
    _files(tmp_path)

    def boom(m, v, t):
        raise RuntimeError("corrupt")

    bad = KokoroTTS(tmp_path, Config(), lambda m: None, loader=boom)
    assert bad.model_state == "error"
    tts.reload(Config())
    assert tts.model_state == "ready"


def test_voices_ok_reflects_known_voices(tmp_path):
    _files(tmp_path)
    tts = KokoroTTS(tmp_path, Config(voice_pt="zz_nope"), lambda m: None, loader=lambda m, v, t: FakeKokoro())
    assert tts.voices_ok == {"pt": False, "en": True}


def test_speed_passed_to_create(tmp_path):
    _files(tmp_path)
    fake = FakeKokoro()
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: fake)
    tts.synth("oi", "pt")
    tts.reload(Config(speed=1.2))
    tts.synth("oi", "pt")
    assert fake.speeds == [1.0, 1.2]


def test_loader_gets_threads_once(tmp_path):
    _files(tmp_path)
    seen = []

    def loader(m, v, t):
        seen.append(t)
        return FakeKokoro()

    tts = KokoroTTS(tmp_path, Config(cpu_threads=4), lambda m: None, loader=loader)
    tts.reload(Config(cpu_threads=6))
    assert seen == [4]


@pytest.mark.slow
def test_real_kokoro_returns_wav():
    voices = Path("voices")
    if not (voices / MODEL_FILE).exists():
        pytest.skip("model files not downloaded")
    data = KokoroTTS(voices, Config(), print).synth("Olá, tudo bem?", "pt")
    assert data.startswith(b"RIFF") and len(data) > 5000


def test_voices_grouped_and_labelled(tmp_path):
    (tmp_path / "kokoro-v1.0.int8.onnx").write_bytes(b"x")
    (tmp_path / "voices-v1.0.bin").write_bytes(b"x")
    fake = FakeKokoro()
    fake.get_voices = lambda: ["pm_alex", "pf_dora", "af_heart", "bm_george", "zz_other", "bad name"]
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: fake)
    assert tts.voices() == {
        "pt": [{"id": "pf_dora", "label": "Dora (female)"}, {"id": "pm_alex", "label": "Alex (male)"}],
        "en": [{"id": "af_heart", "label": "Heart (female)"}, {"id": "bm_george", "label": "George (male)"}],
    }


def test_voices_empty_when_model_missing(tmp_path):
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: FakeKokoro())
    assert tts.voices() == {"pt": [], "en": []}


def _ready(tmp_path, fake):
    (tmp_path / "kokoro-v1.0.int8.onnx").write_bytes(b"x")
    (tmp_path / "voices-v1.0.bin").write_bytes(b"x")
    return KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: fake)


def test_tts_synth_uses_given_voice(tmp_path):
    fake = FakeKokoro()
    tts = _ready(tmp_path, fake)
    tts.synth("hi", "en", "af_bella")
    assert fake.calls[-1][1] == "af_bella"


def test_tts_synth_falls_back_on_unknown_voice(tmp_path):
    fake = FakeKokoro()
    tts = _ready(tmp_path, fake)
    for bad in ("zz_nope", "", "BAD NAME"):
        assert tts.synth("hi", "en", bad).startswith(b"RIFF")
        assert fake.calls[-1][1] == "af_heart"
