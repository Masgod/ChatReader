"""Chat overlay themes: a folder with theme.toml, heroes/<hero>/<expression>.png and fonts/.

Theme folders are untrusted input (people share them), so every read is validated and every served path is
contained inside the theme folder.
"""
import re
import tomllib
from importlib import resources
from pathlib import Path
from urllib.parse import quote

from chatreader.config import THEME_NAME_RE

DEFAULT = "default"
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "svg"}
FONT_EXTS = {"woff2", "otf", "ttf"}
SERVED_EXTS = IMAGE_EXTS | FONT_EXTS  # theme.toml is never served
ANIMATIONS = ("fade", "slide", "snap", "none")
LAYOUTS = ("side", "top")  # portrait beside the text, or above it
MAX_IMAGES = 200
MAX_FILE_BYTES = 5_000_000
MAX_MANIFEST_BYTES = 64_000
COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


class ThemeError(Exception):
    pass


def _builtin_dir() -> Path:
    return Path(str(resources.files("chatreader") / "web" / "themes" / DEFAULT))


def _folder(user_dir: Path | None, name: str) -> Path | None:
    if not THEME_NAME_RE.fullmatch(name):
        return None
    if name == DEFAULT:
        return _builtin_dir()
    if user_dir is None:
        return None
    folder = user_dir / name
    return folder if folder.is_dir() else None


def _url(name: str, *parts: str) -> str:
    return "/themes/" + quote(name) + "/" + "/".join(quote(p) for p in parts)


def _color(table: dict, key: str, default: str, where: str) -> str:
    v = table.get(key, default)
    if not isinstance(v, str) or not COLOR_RE.fullmatch(v):
        raise ThemeError(f"{where}.{key} must be a color like #1f1b2e or #fff")
    return v


def _size(table: dict, key: str, default: int) -> int:
    v = table.get(key, default)
    if type(v) is not int or not 16 <= v <= 320:
        raise ThemeError(f"bubble.{key} must be a whole number of pixels from 16 to 320")
    return v


def _table(data: dict, key: str) -> dict:
    v = data.get(key, {})
    if not isinstance(v, dict):
        raise ThemeError(f"[{key}] must be a table")
    return v


def _check_file(folder: Path, root: Path, path: Path) -> None:
    rel = path.relative_to(folder).as_posix()
    if not path.resolve().is_relative_to(root):
        raise ThemeError(f"{rel} points outside the theme folder")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ThemeError(f"{rel} is larger than 5 MB")


def _heroes(folder: Path, root: Path, name: str) -> list[dict]:
    base = folder / "heroes"
    if not base.is_dir():
        return []
    heroes, count = [], 0
    for hero in sorted(p for p in base.iterdir() if p.is_dir()):
        images = {}
        for f in sorted(hero.iterdir()):
            ext = f.suffix.lstrip(".").lower()
            if not f.is_file() or ext not in IMAGE_EXTS:
                continue
            count += 1
            if count > MAX_IMAGES:
                raise ThemeError(f"more than {MAX_IMAGES} images")
            _check_file(folder, root, f)
            images[f.stem] = _url(name, "heroes", hero.name, f.name)
        if images:
            heroes.append({"name": hero.name, "images": images})
    return heroes


def _font(folder: Path, root: Path, name: str, rel) -> str | None:
    if rel is None:
        return None
    if not isinstance(rel, str):
        raise ThemeError("font must be a path like fonts/name.woff2")
    path = folder / rel
    parts = Path(rel).parts
    if Path(rel).is_absolute() or ".." in parts or not parts or parts[0] != "fonts":
        raise ThemeError("font must point inside the fonts folder")
    if path.suffix.lstrip(".").lower() not in FONT_EXTS:
        raise ThemeError("font must be .woff2, .otf or .ttf")
    if not path.is_file():
        raise ThemeError(f"font file {rel} does not exist")
    _check_file(folder, root, path)
    return _url(name, *parts)


def load_theme(folder: Path, name: str) -> dict:
    """Read and validate one theme folder; raises ThemeError with a message a person can act on."""
    manifest = folder / "theme.toml"
    try:
        if manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ThemeError("theme.toml is too large")
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ThemeError("theme.toml is missing") from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, RecursionError) as e:
        raise ThemeError(f"theme.toml is not valid: {type(e).__name__}") from None
    except OSError:
        raise ThemeError("theme.toml can't be read") from None
    root = folder.resolve()
    bubble, events = _table(data, "bubble"), _table(data, "events")
    animation = bubble.get("animation", "slide")
    if animation not in ANIMATIONS:
        raise ThemeError("bubble.animation must be one of " + ", ".join(ANIMATIONS))
    layout = bubble.get("layout", "side")
    if layout not in LAYOUTS:
        raise ThemeError("bubble.layout must be one of " + ", ".join(LAYOUTS))
    side = 96 if layout == "top" else 56
    portrait = {"width": _size(bubble, "portrait_width", side), "height": _size(bubble, "portrait_height", side)}
    radius = bubble.get("radius", 12)
    if type(radius) is not int or not 0 <= radius <= 40:
        raise ThemeError("bubble.radius must be a whole number from 0 to 40")
    expressions = data.get("expressions", [])
    if not isinstance(expressions, list) or not all(isinstance(e, dict) for e in expressions):
        raise ThemeError("expressions must be a list of [[expressions]] tables")
    exprs = []
    for e in expressions:
        n, chance = e.get("name"), e.get("chance", 0)
        if not isinstance(n, str) or not n:
            raise ThemeError("every expression needs a name")
        if type(chance) not in (int, float) or not 0 <= chance <= 1:
            raise ThemeError(f"expression {n}: chance must be between 0 and 1")
        exprs.append({"name": n, "chance": chance})
    if sum(e["chance"] for e in exprs) > 1 + 1e-9:
        raise ThemeError("expression chances must add up to at most 1")
    fallback = data.get("fallback", "")
    if not isinstance(fallback, str):
        raise ThemeError("fallback must be an expression name")
    if fallback and fallback not in {e["name"] for e in exprs}:
        raise ThemeError("fallback must name one of the listed expressions")
    return {
        "name": str(data.get("name", name))[:60],
        "author": str(data.get("author", ""))[:60],
        "font": _font(folder, root, name, data.get("font")),
        "bubble": {
            "background": _color(bubble, "background", "#1f1b2e", "bubble"),
            "color": _color(bubble, "color", "#f4f1ff", "bubble"),
            "radius": radius,
            "animation": animation,
            "layout": layout,
            "portrait": portrait,
        },
        "events": {
            "background": _color(events, "background", "#4b2a86", "events"),
            "color": _color(events, "color", "#ffffff", "events"),
        },
        "heroes": _heroes(folder, root, name),
        "expressions": exprs,
        "fallback": fallback or None,
    }


def load_named(user_dir: Path | None, name: str) -> dict:
    folder = _folder(user_dir, name)
    if folder is None:
        raise ThemeError(f"theme '{name}' was not found")
    return load_theme(folder, name)


def list_themes(user_dir: Path | None) -> list[dict]:
    out = [{"name": DEFAULT, "title": load_named(None, DEFAULT)["name"], "valid": True, "error": None}]
    if user_dir is None or not user_dir.is_dir():
        return out
    for p in sorted(x for x in user_dir.iterdir() if x.is_dir()):
        try:
            if p.name.lower() == DEFAULT:
                raise ThemeError("'default' is the built-in theme; rename this folder")
            if not THEME_NAME_RE.fullmatch(p.name):
                raise ThemeError("folder name must be 1-40 letters, digits, - or _")
            title = load_theme(p, p.name)["name"]
            out.append({"name": p.name, "title": title, "valid": True, "error": None})
        except ThemeError as e:
            out.append({"name": p.name, "title": p.name, "valid": False, "error": str(e)})
    return out


def resolve_file(user_dir: Path | None, name: str, rel: str) -> Path | None:
    """The file to serve for /themes/<name>/<rel>, or None for anything outside the allowed set."""
    folder = _folder(user_dir, name)
    if folder is None or not rel or "\\" in rel:
        return None
    parts = Path(rel).parts
    if Path(rel).is_absolute() or rel.startswith("/") or ".." in parts or ":" in rel:
        return None
    if Path(rel).suffix.lstrip(".").lower() not in SERVED_EXTS:
        return None
    target = (folder / rel).resolve()
    if not target.is_relative_to(folder.resolve()) or not target.is_file():
        return None
    return target if target.stat().st_size <= MAX_FILE_BYTES else None
