import io
import urllib.request
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

from chatreader.config import VOICE_NAME_RE, Config

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_FILE = "kokoro-v1.0.int8.onnx"  # int8: ~92 MB, noticeably lighter on CPU than the fp32 model
VOICES_FILE = "voices-v1.0.bin"
LANG_CODE = {"pt": "pt-br", "en": "en-us"}
THREADS = 2  # keep TTS from competing with the game for cores


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def ensure_models(
    models_dir: Path, download: Callable[[str, Path], None] = _download
) -> list[str]:
    """Download missing model files; return the file names that could not be obtained."""
    models_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    for name in (MODEL_FILE, VOICES_FILE):
        dest = models_dir / name
        if dest.exists():
            continue
        try:
            download(f"{RELEASE}/{name}", dest)
        except Exception:
            failed.append(name)
    return failed


def _kokoro_load(model: Path, voices: Path):
    import onnxruntime as rt
    from kokoro_onnx import Kokoro

    opts = rt.SessionOptions()
    opts.intra_op_num_threads = THREADS
    session = rt.InferenceSession(str(model), sess_options=opts, providers=["CPUExecutionProvider"])
    return Kokoro.from_session(session, str(voices))


class KokoroTTS:
    def __init__(
        self,
        models_dir: Path,
        cfg: Config,
        on_warning: Callable[[str], None],
        loader: Callable = _kokoro_load,
    ):
        self._dir = models_dir
        self._warn = on_warning
        self._loader = loader
        self._kokoro = None
        self._voice = {}
        self.reload(cfg)

    def reload(self, cfg: Config) -> None:
        if self._kokoro is None:
            model, voices = self._dir / MODEL_FILE, self._dir / VOICES_FILE
            if not (model.exists() and voices.exists()):
                return  # still downloading; boot calls reload again afterwards
            try:
                self._kokoro = self._loader(model, voices)
            except Exception as e:
                self._warn(f"could not load Kokoro model: {e}")
                return
        known = set(self._kokoro.get_voices())
        chosen = {}
        for lang, name in (("pt", cfg.voice_pt), ("en", cfg.voice_en)):
            if not VOICE_NAME_RE.fullmatch(name) or name not in known:
                self._warn(f"unknown voice {name!r}, skipped")
            else:
                chosen[lang] = name
        self._voice = chosen

    def synth(self, text: str, lang: str) -> bytes:
        kokoro, voice = self._kokoro, self._voice
        if kokoro is None:
            raise RuntimeError("Kokoro model not loaded")
        name = voice.get(lang)
        if name is None:
            raise RuntimeError(f"no voice configured for {lang!r}")
        samples, rate = kokoro.create(text, voice=name, speed=1.0, lang=LANG_CODE[lang])
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        return buf.getvalue()
