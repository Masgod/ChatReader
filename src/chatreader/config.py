import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

TWITCH_RE = re.compile(r"[a-z0-9_]{3,25}")
VOICE_NAME_RE = re.compile(r"[a-z]{2}_[a-z0-9]+")
YOUTUBE_RE = re.compile(r"[A-Za-z0-9_-]{11}")
CHANNEL_RE = re.compile(r"@[A-Za-z0-9_.-]+|UC[A-Za-z0-9_-]{22}")
CHANNEL_URL_RE = re.compile(r"youtube\.com/(?:(@[A-Za-z0-9_.-]+)|channel/(UC[A-Za-z0-9_-]{22}))")
YOUTUBE_URL_RE = re.compile(r"(?:v=|youtu\.be/|/live/|/embed/)([A-Za-z0-9_-]{11})")


@dataclass
class Config:
    twitch_channel: str = ""
    youtube_video_id: str = ""
    voice_pt: str = "pf_dora"
    voice_en: str = "af_heart"
    default_lang: str = "pt"
    queue_size: int = 20
    max_chars: int = 200
    announce_user: bool = True
    port: int = 8765
    start_with_windows: bool = False
    ignored_users: list[str] = field(
        default_factory=lambda: ["nightbot", "streamelements", "streamlabs", "moobot"]
    )
    repeat_window: int = 5
    debug: bool = False
    speed: float = 1.0
    cpu_threads: int = 2
    youtube_channel: str = ""


def load_config(path: Path) -> Config:
    if not path.exists():
        cfg = Config()
        save_config(path, cfg)
        return cfg
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        path.replace(path.with_name(path.name + ".bad"))
        return Config()
    defaults = Config()
    known = {f.name: getattr(defaults, f.name) for f in fields(Config)}
    kept = {k: v for k, v in data.items() if k in known and same_type(v, known[k])}
    cfg = Config(**kept)
    if validate(cfg):  # parseable but unusable values: treat like a corrupt file
        path.replace(path.with_name(path.name + ".bad"))
        return defaults
    return cfg


def same_type(v, default) -> bool:
    if isinstance(default, list):
        return isinstance(v, list) and all(isinstance(x, str) for x in v)
    if isinstance(default, float):
        return type(v) in (int, float)  # JSON and TOML write 1.0 as 1; bool is still rejected
    return type(v) is type(default)  # exact type: bool is not int


def save_config(path: Path, cfg: Config) -> None:
    path.write_text(tomli_w.dumps(asdict(cfg)), encoding="utf-8")


def normalize(cfg: Config) -> Config:
    channel = cfg.twitch_channel.strip().lstrip("#").lower()
    video = cfg.youtube_video_id.strip()
    match = YOUTUBE_URL_RE.search(video)
    if match:
        video = match.group(1)
    chan = cfg.youtube_channel.strip()
    m = CHANNEL_URL_RE.search(chan)
    if m:
        chan = m.group(1) or m.group(2)
    return Config(**{**asdict(cfg), "twitch_channel": channel, "youtube_video_id": video, "youtube_channel": chan})


def validate(cfg: Config) -> list[str]:
    errors = []
    if cfg.twitch_channel and not TWITCH_RE.fullmatch(cfg.twitch_channel):
        errors.append("twitch_channel must be 3-25 chars of a-z, 0-9 or _")
    if cfg.youtube_video_id and not YOUTUBE_RE.fullmatch(cfg.youtube_video_id):
        errors.append("youtube_video_id must be an 11-char YouTube ID")
    if cfg.queue_size < 1:
        errors.append("queue_size must be >= 1")
    if not 0.8 <= cfg.speed <= 1.4:
        errors.append("speed must be between 0.8 and 1.4")
    if not 1 <= cfg.cpu_threads <= 8:
        errors.append("cpu_threads must be between 1 and 8")
    if cfg.youtube_channel and not CHANNEL_RE.fullmatch(cfg.youtube_channel):
        errors.append("youtube_channel must be an @handle or a UC... channel ID")
    if cfg.max_chars < 1:
        errors.append("max_chars must be >= 1")
    if cfg.repeat_window < 0:
        errors.append("repeat_window must be >= 0")
    for attr in ("voice_pt", "voice_en"):
        if not VOICE_NAME_RE.fullmatch(getattr(cfg, attr)):
            errors.append(f"{attr} must look like pf_dora")
    if not 1 <= cfg.port <= 65535:
        errors.append("port must be between 1 and 65535")
    if cfg.default_lang not in ("pt", "en"):
        errors.append("default_lang must be 'pt' or 'en'")
    return errors
