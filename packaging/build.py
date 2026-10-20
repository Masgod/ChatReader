"""Build dist/ChatReader/ and a release zip with its checksum.

    uv run --group build python packaging/build.py
"""
import hashlib
import re
from importlib import metadata
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README_TXT = """ChatReader
==========
1. Run ChatReader.exe. A purple icon appears in the taskbar tray; the control center opens
   in your browser on first run (the voice model, about 120 MB, downloads then).
2. In OBS add a Browser Source with the URL http://127.0.0.1:8765/overlay and tick
   "Control audio via OBS".
3. Windows may warn about an unknown app: choose "More info", then "Run anyway".
   Compare the zip's SHA-256 with the .sha256 file if you want to verify it.
Your settings and the voice model live in %APPDATA%\\ChatReader.
See THIRD_PARTY_NOTICES.txt for the licences of the bundled components.
"""


def version(pyproject: Path) -> str:
    return tomllib.loads(pyproject.read_text("utf-8"))["project"]["version"]


def zip_name(ver: str) -> str:
    return f"ChatReader-{ver}-win64.zip"


def write_checksum(zip_path: Path) -> Path:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    out = zip_path.with_name(zip_path.name + ".sha256")
    out.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return out


def _name(requirement: str) -> str:
    return re.split(r"[\s;<>=!~\[(]", requirement, maxsplit=1)[0].lower().replace("_", "-")


def runtime_closure(roots) -> set[str]:
    """Installed distributions the roots need, following Requires-Dist (extras skipped)."""
    seen, todo = set(), [_name(r) for r in roots]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # a dependency not installed here (platform marker): nothing to ship
        seen.add(name)
        todo += [_name(r) for r in (dist.requires or []) if "extra ==" not in r]
    return seen


def copy_licenses(names, out_dir: Path) -> int:
    """Copy each distribution's licence and notice files into out_dir/<name>/. Returns files copied."""
    count = 0
    for name in sorted(names):
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        for f in dist.files or []:
            if re.search(r"(licen[cs]e|copying|notice)", f.name, re.IGNORECASE):
                src = Path(dist.locate_file(f))
                if src.is_file():
                    dest = out_dir / name / f.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src, dest)
                    count += 1
    return count


def main() -> None:
    sys.path.insert(0, str(ROOT / "packaging"))
    import make_icon

    make_icon.main()
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
                    str(ROOT / "packaging" / "chatreader.spec")], check=True)
    out = ROOT / "dist" / "ChatReader"
    shutil.copy(ROOT / "THIRD_PARTY_NOTICES.txt", out)
    (out / "README.txt").write_text(README_TXT, encoding="utf-8")
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["dependencies"]
    print("licence files copied:", copy_licenses(runtime_closure(deps), out / "licenses"))
    zip_path = ROOT / "dist" / zip_name(version(ROOT / "pyproject.toml"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path("ChatReader") / f.relative_to(out))
    print(zip_path, write_checksum(zip_path).read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    main()
