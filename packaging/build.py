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
import urllib.request
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


# GPL-3.0 section 6: the zip ships phonemizer and espeak-ng, so the exact source goes out with each release.
# espeakng-loader 0.2.4 has no sdist and no git tag; its commit "bump version to 0.2.4" is the source of the wheel.
# That commit's CI (.github/workflows/build.yml) clones espeak-ng tag 1.52.0, and the repo's espeak-ng gitlink
# at the same commit is the same hash, which is the proof for the revision below.
LOADER_REPO = "https://github.com/thewh1teagle/espeakng-loader"
LOADER_COMMIT = "146599e29be31bf17d99f0bcb7dbb2f92aef3d95"
ESPEAK_REPO = "https://github.com/espeak-ng/espeak-ng"
ESPEAK_TAG, ESPEAK_COMMIT = "1.52.0", "4870adfa25b1a32b4361592f1be8a40337c58d6c"
# The loader's MIT LICENSE was added to its repo (2025-11-01) after 0.2.4 and is not in the wheel; the text is unchanged since.
LOADER_LICENSE_URL = "https://raw.githubusercontent.com/thewh1teagle/espeakng-loader/0ddc87adf77e5850d7eeb542ac8a87d421b64daa/LICENSE"
LOADER_LICENSE_SHA256 = "b05c73bb1335b4320ec97edff106b3991c12d0acdc6e899c96f061a15039119f"
GPL_README = """ChatReader {ver}: corresponding source for the GPL-3.0 components
=================================================================
This archive is the complete corresponding source for the GPL components inside ChatReader-{ver}-win64.zip
(GNU GPL version 3 section 6). Each file under sources/ is the unmodified upstream source.

{items}
How the shipped binaries were made: ChatReader-{ver}-win64.zip is built by packaging/build.py in
https://github.com/Masgod/ChatReader with PyInstaller. It bundles the unmodified phonemizer package and the
espeakng-loader wheel from PyPI; the wheel's espeak-ng library and data are built from the espeak-ng revision
above by the espeakng-loader CI (cmake, -DBUILD_SHARED_LIBS=ON -DCOMPILE_INTONATIONS=OFF for the library;
espeak-ng-data with -DCOMPILE_INTONATIONS=ON), see build.sh and .github/workflows/build.yml in the loader source.
Licence text: https://www.gnu.org/licenses/gpl-3.0.txt
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


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def fetch_checked(url: str, sha256: str | None, fetch=download) -> bytes:
    data = fetch(url)
    if sha256 and hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"checksum mismatch for {url}")
    return data


def gpl_sources(lock_path: Path) -> list[dict]:
    """What must ship as source: versions come from uv.lock, so they cannot drift from what is bundled."""
    pkgs = {p["name"]: p for p in tomllib.loads(lock_path.read_text("utf-8"))["package"]}
    ph = pkgs["phonemizer"]
    sdist = ph["sdist"]
    return [
        {"name": "phonemizer", "version": ph["version"], "url": sdist["url"], "sha256": sdist["hash"].removeprefix("sha256:"),
         "file": f"phonemizer-{ph['version']}.tar.gz", "note": "sdist from PyPI, hash checked against uv.lock"},
        {"name": "espeakng-loader", "version": pkgs["espeakng-loader"]["version"], "commit": LOADER_COMMIT,
         "url": f"{LOADER_REPO}/archive/{LOADER_COMMIT}.zip", "sha256": None,
         "file": f"espeakng-loader-{pkgs['espeakng-loader']['version']}-{LOADER_COMMIT[:7]}.zip",
         "note": f"git commit {LOADER_COMMIT} ('bump version to 0.2.4'); PyPI has no sdist for this version"},
        {"name": "espeak-ng", "version": ESPEAK_TAG, "commit": ESPEAK_COMMIT, "url": f"{ESPEAK_REPO}/archive/{ESPEAK_COMMIT}.zip",
         "sha256": None, "file": f"espeak-ng-{ESPEAK_TAG}.zip",
         "note": f"tag {ESPEAK_TAG} = commit {ESPEAK_COMMIT}; the revision espeakng-loader's CI clones"},
    ]


def build_gpl_sources_zip(zip_path: Path, ver: str, entries: list[dict], fetch=download, verify: bool = True) -> None:
    items = "".join(f"- {e['name']} {e['version']}: sources/{e['file']}\n    from {e['url']}\n    {e['note']}\n" for e in entries)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", GPL_README.format(ver=ver, items=items))
        for e in entries:
            z.writestr(f"sources/{e['file']}", fetch_checked(e["url"], e["sha256"] if verify else None, fetch))


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
    ver = version(ROOT / "pyproject.toml")
    loader_lic = out / "licenses" / "espeakng-loader"  # the wheel carries no licence file
    loader_lic.mkdir(parents=True, exist_ok=True)
    (loader_lic / "LICENSE").write_bytes(fetch_checked(LOADER_LICENSE_URL, LOADER_LICENSE_SHA256))
    zip_path = ROOT / "dist" / zip_name(ver)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path("ChatReader") / f.relative_to(out))
    print(zip_path, write_checksum(zip_path).read_text(encoding="utf-8").strip())
    src_zip = ROOT / "dist" / f"ChatReader-{ver}-gpl-sources.zip"
    build_gpl_sources_zip(src_zip, ver, gpl_sources(ROOT / "uv.lock"))
    print(src_zip, write_checksum(src_zip).read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    main()
