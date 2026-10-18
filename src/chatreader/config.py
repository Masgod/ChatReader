import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

TWITCH_RE = re.compile(r"[a-z0-9_]{3,25}")
YOUTUBE_RE = re.compile(r"[A-Za-z0-9_-]{11}")
YOUTUBE_URL_RE = re.compile(r"(?:v=|youtu\.be/|/live/|/embed/)([A-Za-z0-9_-]{11})")


@dataclass
class Config:
    twitch_channel: str = ""
    youtube_video_id: str = ""
    voice_pt: str = "pt_BR-faber-medium"
    voice_en: str = "en_US-lessac-medium"
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
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})


def save_config(path: Path, cfg: Config) -> None:
    path.write_text(tomli_w.dumps(asdict(cfg)), encoding="utf-8")


def normalize(cfg: Config) -> Config:
    channel = cfg.twitch_channel.strip().lstrip("#").lower()
    video = cfg.youtube_video_id.strip()
    match = YOUTUBE_URL_RE.search(video)
    if match:
        video = match.group(1)
    return Config(**{**asdict(cfg), "twitch_channel": channel, "youtube_video_id": video})


def validate(cfg: Config) -> list[str]:
    errors = []
    if cfg.twitch_channel and not TWITCH_RE.fullmatch(cfg.twitch_channel):
        errors.append("twitch_channel must be 3-25 chars of a-z, 0-9 or _")
    if cfg.youtube_video_id and not YOUTUBE_RE.fullmatch(cfg.youtube_video_id):
        errors.append("youtube_video_id must be an 11-char YouTube ID")
    if cfg.queue_size < 1:
        errors.append("queue_size must be >= 1")
    if not 1 <= cfg.port <= 65535:
        errors.append("port must be between 1 and 65535")
    if cfg.default_lang not in ("pt", "en"):
        errors.append("default_lang must be 'pt' or 'en'")
    return errors
