import io
import wave
from pathlib import Path

import numpy as np
import pytest

from chatreader.config import Config
from chatreader.tts import MODEL_FILE, VOICES_FILE, KokoroTTS, ensure_models, normalize_loudness


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
        "es": [], "fr": [], "it": [],
    }


def test_voices_empty_when_model_missing(tmp_path):
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: FakeKokoro())
    assert tts.voices() == {"pt": [], "en": [], "es": [], "fr": [], "it": []}


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


def test_invalid_default_voice_still_means_language_not_spoken(tmp_path):
    import pytest

    (tmp_path / "kokoro-v1.0.int8.onnx").write_bytes(b"x")
    (tmp_path / "voices-v1.0.bin").write_bytes(b"x")
    tts = KokoroTTS(tmp_path, Config(voice_pt="zz_nope"), lambda m: None, loader=lambda m, v, t: FakeKokoro())
    with pytest.raises(RuntimeError):
        tts.synth("oi", "pt", "pf_dora")  # a per-viewer voice must not bypass the broken default


def test_synth_uses_language_code(tmp_path):
    _files(tmp_path)
    fake = FakeKokoro()
    fake.get_voices = lambda: ["ef_dora", "af_heart"]
    tts = KokoroTTS(tmp_path, Config(languages=["es", "en"], default_lang="es"), lambda m: None, loader=lambda m, v, t: fake)
    tts.synth("hola", "es")
    assert fake.calls == [("hola", "ef_dora", "es")]


def test_disabled_language_voice_is_not_validated(tmp_path):
    _files(tmp_path)
    warnings = []
    cfg = Config(languages=["en"], default_lang="en", voice_pt="zz_nope")
    tts = KokoroTTS(tmp_path, cfg, warnings.append, loader=lambda m, v, t: FakeKokoro())
    assert warnings == [] and tts.voices_ok == {"en": True}


def test_voices_grouped_by_language_prefix(tmp_path):
    _files(tmp_path)
    fake = FakeKokoro()
    fake.get_voices = lambda: ["pf_dora", "ef_dora", "ff_siwis", "if_sara", "bm_george"]
    tts = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: fake)
    got = {code: [v["id"] for v in voices] for code, voices in tts.voices().items()}
    assert got == {"pt": ["pf_dora"], "en": ["bm_george"], "es": ["ef_dora"], "fr": ["ff_siwis"], "it": ["if_sara"]}


def _sine(amp, n=24000):
    return (amp * np.sin(np.linspace(0, 200 * np.pi, n))).astype(np.float32)


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def test_quiet_clip_rises_toward_target_by_at_most_max_gain():
    out = normalize_loudness(_sine(0.1))  # rms 0.07
    assert 0.07 < _rms(out) <= 0.1 + 1e-4
    quiet = _sine(0.02)  # rms 0.014: target would need x7, the cap allows x2.5
    assert _rms(normalize_loudness(quiet)) == pytest.approx(_rms(quiet) * 2.5, rel=1e-3)


def test_loud_clip_is_lowered_to_target():
    assert _rms(normalize_loudness(_sine(0.42))) == pytest.approx(0.1, rel=1e-3)


def test_silence_and_one_sample_clips_come_back_unchanged():
    for clip in (np.zeros(2400, dtype=np.float32), np.zeros(0, dtype=np.float32), np.array([0.5], dtype=np.float32), np.array([1e-9] * 5, dtype=np.float32)):
        out = normalize_loudness(clip)
        assert np.array_equal(out, clip) and out.dtype == np.float32


def test_non_finite_samples_are_left_alone_without_error():
    clip = np.array([0.1, np.nan, 0.2], dtype=np.float32)
    assert np.array_equal(normalize_loudness(clip), clip, equal_nan=True)


def test_peak_never_exceeds_the_limit():
    clip = np.zeros(24000, dtype=np.float32)
    clip[100] = 1.0  # one loud click on near silence
    clip += _sine(0.05)
    out = normalize_loudness(clip)
    assert float(np.max(np.abs(out))) <= 0.97 + 1e-6 and out.dtype == np.float32


def test_two_sentences_of_one_message_do_not_jump_in_level():
    a, b = normalize_loudness(_sine(0.06)), normalize_loudness(_sine(0.3))
    assert _rms(a) == pytest.approx(_rms(b), rel=0.05)


def test_does_not_modify_its_input():
    clip = _sine(0.3)
    before = clip.copy()
    normalize_loudness(clip)
    assert np.array_equal(clip, before)


class LoudFake(FakeKokoro):
    def create(self, text, voice, speed, lang):
        super().create(text, voice, speed, lang)
        return _sine(0.42), 24000


def _wav_rms(data):
    with wave.open(io.BytesIO(data)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32767
    return _rms(x)


def test_synth_normalizes_only_when_the_setting_is_on(tmp_path):
    _files(tmp_path)
    on = KokoroTTS(tmp_path, Config(), lambda m: None, loader=lambda m, v, t: LoudFake())
    off = KokoroTTS(tmp_path, Config(normalize_volume=False), lambda m: None, loader=lambda m, v, t: LoudFake())
    assert _wav_rms(on.synth("hi", "en")) == pytest.approx(0.1, rel=0.01)
    assert _wav_rms(off.synth("hi", "en")) == pytest.approx(_rms(_sine(0.42)), rel=0.01)


def test_reload_applies_the_setting_live(tmp_path):
    _files(tmp_path)
    tts = KokoroTTS(tmp_path, Config(normalize_volume=False), lambda m: None, loader=lambda m, v, t: LoudFake())
    tts.reload(Config(normalize_volume=True))
    assert _wav_rms(tts.synth("hi", "en")) == pytest.approx(0.1, rel=0.01)
