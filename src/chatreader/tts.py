import io
import urllib.request
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

from chatreader.config import VOICE_NAME_RE, Config
from chatreader.languages import LANGUAGES

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_FILE = "kokoro-v1.0.int8.onnx"  # int8: ~92 MB, noticeably lighter on CPU than the fp32 model
VOICES_FILE = "voices-v1.0.bin"


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


def _kokoro_load(model: Path, voices: Path, threads: int):
    import onnxruntime as rt
    from kokoro_onnx import Kokoro

    opts = rt.SessionOptions()
    opts.intra_op_num_threads = threads  # fewer threads keeps TTS from competing with the game
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
        self._threads = cfg.cpu_threads  # read once: changing it needs a restart
        self._speed = cfg.speed
        self._voices_ok = {code: False for code in cfg.languages}
        self._known: set[str] = set()
        self.model_state = "missing"  # missing | loading | ready | error
        self.reload(cfg)

    @property
    def voices_ok(self) -> dict[str, bool]:
        return dict(self._voices_ok)

    def voices(self) -> dict[str, list[dict]]:
        """Voices the loaded model offers for every supported language; empty until the model is loaded."""
        out: dict[str, list[dict]] = {code: [] for code in LANGUAGES}
        if self._kokoro is None:
            return out
        for name in sorted(self._kokoro.get_voices()):
            if not VOICE_NAME_RE.fullmatch(name) or len(name) < 4 or name[2] != "_":
                continue
            lang = next((c for c, language in LANGUAGES.items() if name[0] in language.voice_prefixes), None)
            gender = {"f": "female", "m": "male"}.get(name[1])
            if lang and gender:
                out[lang].append({"id": name, "label": f"{name[3:].title()} ({gender})"})
        return out

    def reload(self, cfg: Config) -> None:
        if self._kokoro is None:
            model, voices = self._dir / MODEL_FILE, self._dir / VOICES_FILE
            if not (model.exists() and voices.exists()):
                self.model_state = "missing"
                return  # still downloading; boot calls reload again afterwards
            self.model_state = "loading"
            try:
                self._kokoro = self._loader(model, voices, self._threads)
            except Exception as e:
                self.model_state = "error"
                self._warn(f"could not load Kokoro model: {e}")
                return
            self.model_state = "ready"
        self._speed = cfg.speed
        known = self._known = set(self._kokoro.get_voices())
        chosen = {}
        self._voices_ok = {code: False for code in cfg.languages}
        for lang, name in cfg.voices().items():
            if not VOICE_NAME_RE.fullmatch(name) or name not in known:
                self._warn(f"unknown voice {name!r}, skipped")
            else:
                chosen[lang] = name
                self._voices_ok[lang] = True
        self._voice = chosen

    def synth(self, text: str, lang: str, voice: str = "") -> bytes:
        kokoro, voice, requested = self._kokoro, self._voice, voice
        if kokoro is None:
            raise RuntimeError("Kokoro model not loaded")
        name = voice.get(lang)
        if name is None:
            raise RuntimeError(f"no voice configured for {lang!r}")
        if requested and VOICE_NAME_RE.fullmatch(requested) and requested in self._known:
            name = requested  # per-viewer voice; anything unknown falls back to the configured one
        samples, rate = kokoro.create(text, voice=name, speed=self._speed, lang=LANGUAGES[lang].kokoro)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        return buf.getvalue()
