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
    (tmp_path / "en_US-lessac-medium.onnx").write_bytes(b"x")
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
