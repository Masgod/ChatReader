import re
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

from chatreader.languages import DEFAULT_LANGUAGES, LANGUAGES

ROLE_CHOICES = {"sub", "vip", "mod"}
EVENT_CHOICES = ["bits", "subs", "gifts", "raids", "superchat", "members"]
OVERLAY_POSITIONS = ["top-left", "top-right", "middle-left", "middle-right", "bottom-left", "bottom-right"]
THEME_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")
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
    voice_es: str = "ef_dora"
    voice_fr: str = "ff_siwis"
    voice_it: str = "if_sara"
    languages: list[str] = field(default_factory=lambda: list(DEFAULT_LANGUAGES))  # languages that are read aloud
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
    twitch_roles: list[str] = field(default_factory=list)  # empty = read everyone
    youtube_roles: list[str] = field(default_factory=list)
    repeat_seconds: int = 30  # skip the same text from anyone within this many seconds; 0 = off
    per_user_voices: bool = True
    speak_emotes: bool = True  # laughs like LUL/kkkk are spoken as a laugh, other emotes are left out
    read_events: bool = False  # master switch: events are only read when this is on
    event_kinds: list[str] = field(default_factory=lambda: list(EVENT_CHOICES))  # which events are read aloud
    min_bits: int = 0  # ignore cheers smaller than this
    overlay_theme: str = "default"  # folder name under themes/, or the built-in default
    overlay_position: str = "bottom-left"
    overlay_max_bubbles: int = 4  # bubbles on screen at once
    overlay_hold_seconds: int = 4  # how long a bubble stays after its voice ends
    overlay_scale: int = 100  # size of everything in the chat overlay, in percent

    def voices(self) -> dict[str, str]:
        """The voice chosen for each enabled language."""
        return {code: getattr(self, f"voice_{code}") for code in self.languages}


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
    for code in LANGUAGES:
        if not VOICE_NAME_RE.fullmatch(getattr(cfg, f"voice_{code}")):
            errors.append(f"voice_{code} must look like pf_dora")
    for attr in ("twitch_roles", "youtube_roles"):
        if not set(getattr(cfg, attr)) <= ROLE_CHOICES:
            errors.append(f"{attr} must only contain sub, vip or mod")
    if not 0 <= cfg.repeat_seconds <= 600:
        errors.append("repeat_seconds must be between 0 and 600")
    if not set(cfg.event_kinds) <= set(EVENT_CHOICES):
        errors.append("event_kinds must only contain " + ", ".join(EVENT_CHOICES))
    if not 0 <= cfg.min_bits <= 100000:
        errors.append("min_bits must be between 0 and 100000")
    if not THEME_NAME_RE.fullmatch(cfg.overlay_theme):
        errors.append("overlay_theme must be 1-40 letters, digits, - or _")
    if cfg.overlay_position not in OVERLAY_POSITIONS:
        errors.append("overlay_position must be one of " + ", ".join(OVERLAY_POSITIONS))
    if not 1 <= cfg.overlay_max_bubbles <= 10:
        errors.append("overlay_max_bubbles must be between 1 and 10")
    if not 0 <= cfg.overlay_hold_seconds <= 30:
        errors.append("overlay_hold_seconds must be between 0 and 30")
    if not 50 <= cfg.overlay_scale <= 200:
        errors.append("overlay_scale must be between 50 and 200")
    if not 1 <= cfg.port <= 65535:
        errors.append("port must be between 1 and 65535")
    if not cfg.languages or len(set(cfg.languages)) != len(cfg.languages) or not set(cfg.languages) <= set(LANGUAGES):
        errors.append("languages must be a non-empty list of unique codes from " + ", ".join(LANGUAGES))
    elif cfg.default_lang not in cfg.languages:
        errors.append("default_lang must be one of the enabled languages")
    return errors
