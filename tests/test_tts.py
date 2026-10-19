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
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v: fake)
    data = tts.synth("oi", "pt")
    tts.synth("hi", "en")
    with wave.open(io.BytesIO(data)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 2400
    assert fake.calls == [("oi", "pf_dora", "pt-br"), ("hi", "af_heart", "en-us")]


def test_unknown_voice_is_skipped_with_warning(tmp_path):
    _files(tmp_path)
    warnings = []
    tts = KokoroTTS(tmp_path, Config(voice_pt="zz_nope"), warnings.append, loader=lambda m, v: FakeKokoro())
    assert any("zz_nope" in w for w in warnings)
    with pytest.raises(RuntimeError):
        tts.synth("oi", "pt")
    assert tts.synth("hi", "en").startswith(b"RIFF")


def test_missing_files_then_reload_after_download(tmp_path):
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v: FakeKokoro())
    with pytest.raises(RuntimeError):
        tts.synth("oi", "pt")
    _files(tmp_path)
    tts.reload(Config())
    assert tts.synth("oi", "pt").startswith(b"RIFF")


def test_loader_failure_warns(tmp_path):
    _files(tmp_path)
    warnings = []

    def boom(m, v):
        raise RuntimeError("corrupt")

    KokoroTTS(tmp_path, Config(), warnings.append, loader=boom)
    assert any("corrupt" in w for w in warnings)


@pytest.mark.slow
def test_real_kokoro_returns_wav():
    voices = Path("voices")
    if not (voices / MODEL_FILE).exists():
        pytest.skip("model files not downloaded")
    data = KokoroTTS(voices, Config(), print).synth("Olá, tudo bem?", "pt")
    assert data.startswith(b"RIFF") and len(data) > 5000
