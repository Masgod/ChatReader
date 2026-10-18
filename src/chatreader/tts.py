import io
import re
import urllib.request
import wave
from collections.abc import Callable
from pathlib import Path

from chatreader.config import Config

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


VOICE_NAME_RE = re.compile(r"[A-Za-z0-9_]+-[A-Za-z0-9_]+-[a-z_]+")


def voice_urls(name: str) -> tuple[str, str]:
    if not VOICE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid voice name: {name!r}")
    locale, speaker, quality = name.split("-", 2)
    base = f"{HF_BASE}/{locale.split('_')[0]}/{locale}/{speaker}/{quality}/{name}.onnx"
    return base, base + ".json"


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def ensure_voices(
    voices_dir: Path, names: list[str], download: Callable[[str, Path], None] = _download
) -> list[str]:
    """Download missing voice files; return the names that could not be obtained."""
    voices_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    for name in names:
        try:
            for url in voice_urls(name):
                dest = voices_dir / url.rsplit("/", 1)[1]
                if not dest.exists():
                    download(url, dest)
        except Exception:
            failed.append(name)
    return failed


def _piper_load(path):
    from piper import PiperVoice

    return PiperVoice.load(path)


class PiperTTS:
    def __init__(
        self,
        voices_dir: Path,
        cfg: Config,
        on_warning: Callable[[str], None],
        loader: Callable = _piper_load,
    ):
        self._dir = voices_dir
        self._warn = on_warning
        self._loader = loader
        self._warned: set[str] = set()
        self.reload(cfg)

    def reload(self, cfg: Config) -> None:
        voices = {}
        for lang, name in (("pt", cfg.voice_pt), ("en", cfg.voice_en)):
            path = self._dir / f"{name}.onnx"
            if not VOICE_NAME_RE.fullmatch(name):
                self._warn(f"invalid voice name {name!r}, skipped")
            elif not path.exists():
                continue
            elif not path.with_suffix(".onnx.json").exists():
                self._warn(f"voice {name} is incomplete (missing .onnx.json), skipped")
            else:
                try:
                    voices[lang] = self._loader(path)
                except Exception as e:
                    self._warn(f"could not load voice {name}: {e}")
        self._voices = voices
        self._warned.clear()

    def synth(self, text: str, lang: str) -> bytes:
        voices = self._voices
        voice = voices.get(lang)
        if voice is None:
            other = "en" if lang == "pt" else "pt"
            voice = voices.get(other)
            if voice is None:
                raise RuntimeError("no Piper voice loaded")
            if lang not in self._warned:
                self._warned.add(lang)
                self._warn(f"voice for '{lang}' missing, using '{other}' voice")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            voice.synthesize_wav(text, w)
        return buf.getvalue()
