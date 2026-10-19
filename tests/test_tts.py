import io
import wave
from pathlib import Path

import pytest

from chatreader.config import Config
from chatreader.tts import PiperTTS, ensure_voices, voice_urls

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium"


def test_voice_urls():
    assert voice_urls("pt_BR-faber-medium") == (BASE + ".onnx", BASE + ".onnx.json")


def test_ensure_voices_skips_existing_and_reports_failures(tmp_path):
    for ext in (".onnx", ".onnx.json"):
        (tmp_path / f"en_US-have-medium{ext}").write_bytes(b"x")
    calls = []

    def download(url, dest):
        calls.append(dest.name)
        if "bad" in url:
            raise OSError("boom")
        dest.write_bytes(b"x")

    failed = ensure_voices(tmp_path, ["en_US-have-medium", "xx_YY-bad-medium"], download)
    assert failed == ["xx_YY-bad-medium"]
    assert not any(c.startswith("en_US-have") for c in calls)


class FakeVoice:
    def __init__(self, tag):
        self.tag = tag

    def synthesize_wav(self, text, wav):
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(self.tag.encode()[:2] * 2)


def test_synth_falls_back_to_other_voice(tmp_path):
    _fake(tmp_path, ["en_US-lessac-medium"], ["en_US-lessac-medium"])
    warnings = []
    tts = PiperTTS(tmp_path, Config(), warnings.append, loader=lambda p: FakeVoice(Path(p).stem))
    data = tts.synth("oi", "pt")
    assert data.startswith(b"RIFF")
    with wave.open(io.BytesIO(data)) as w:
        assert w.readframes(10).startswith(b"en")
    assert len(warnings) == 1


@pytest.mark.slow
def test_real_piper_returns_wav():
    voices = Path("voices")
    cfg = Config()
    if not (voices / f"{cfg.voice_en}.onnx").exists():
        pytest.skip("voices not downloaded")
    data = PiperTTS(voices, cfg, lambda m: None).synth("hello there", "en")
    assert data.startswith(b"RIFF") and len(data) > 1000


def _fake(tmp_path, names, with_json=()):
    for n in names:
        (tmp_path / f"{n}.onnx").write_bytes(b"x")
    for n in with_json:
        (tmp_path / f"{n}.onnx.json").write_bytes(b"x")


def test_missing_json_is_skipped_with_warning(tmp_path):
    _fake(tmp_path, ["pt_BR-faber-medium", "en_US-lessac-medium"], ["en_US-lessac-medium"])
    warnings = []
    tts = PiperTTS(tmp_path, Config(), warnings.append, loader=lambda p: FakeVoice(Path(p).stem))
    assert len(warnings) == 1
    with wave.open(io.BytesIO(tts.synth("oi", "pt"))) as w:
        assert w.readframes(10).startswith(b"en")
    assert len(warnings) == 2  # fallback warning


def test_loader_failure_is_skipped_with_warning(tmp_path):
    names = ["pt_BR-faber-medium", "en_US-lessac-medium"]
    _fake(tmp_path, names, names)

    def loader(p):
        if "faber" in str(p):
            raise RuntimeError("corrupt")
        return FakeVoice(Path(p).stem)

    warnings = []
    tts = PiperTTS(tmp_path, Config(), warnings.append, loader=loader)
    assert len(warnings) == 1
    assert tts.synth("oi", "pt").startswith(b"RIFF")


def test_invalid_voice_names_rejected(tmp_path):
    for bad in ["../x", "a\b-c-d", "pt_BR-faber-medium/../../x", ""]:
        with pytest.raises(ValueError):
            voice_urls(bad)
    warnings = []
    PiperTTS(tmp_path, Config(voice_pt="../x"), warnings.append, loader=lambda p: None)
    assert any("invalid" in w for w in warnings)
