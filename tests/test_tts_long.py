import io
import wave
from pathlib import Path

import pytest

from chatreader.config import Config
from chatreader.tts import MODEL_FILE, VOICES_FILE, KokoroTTS

# ~900 characters, no punctuation: kokoro-onnx must split the phonemes itself.
LONG_TEXT = " ".join(["palavra"] * 113)


@pytest.mark.slow
def test_long_text_synthesizes_without_error():
    assert len(LONG_TEXT) >= 900
    voices = Path("voices")
    if not ((voices / MODEL_FILE).exists() and (voices / VOICES_FILE).exists()):
        pytest.skip("model files not downloaded")
    data = KokoroTTS(voices, Config(max_chars=2000), print).synth(LONG_TEXT, "pt")
    assert data.startswith(b"RIFF")
    with wave.open(io.BytesIO(data)) as w:
        seconds = w.getnframes() / w.getframerate()
    assert seconds > 20
