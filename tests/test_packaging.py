import hashlib
import importlib.util
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build():
    spec = importlib.util.spec_from_file_location("build", ROOT / "packaging" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_version_from_pyproject():
    assert _build().version(ROOT / "pyproject.toml") == tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]


def test_zip_name():
    assert _build().zip_name("1.2.3") == "ChatReader-1.2.3-win64.zip"


def test_checksum_file_matches_sha256(tmp_path):
    z = tmp_path / "a.zip"
    z.write_bytes(b"hello")
    out = _build().write_checksum(z)
    assert out == tmp_path / "a.zip.sha256"
    assert out.read_text("utf-8").strip() == f"{hashlib.sha256(b'hello').hexdigest()}  a.zip"


def test_notices_list_all_runtime_dependencies():
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["dependencies"]
    notices = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text("utf-8").lower()
    for dep in deps:
        assert re.split(r"[<>=\[ ]", dep)[0].lower() in notices, dep
    assert "kokoro-82m" in notices and "apache-2.0" in notices


def test_spec_collects_data_packages():
    spec = (ROOT / "packaging" / "chatreader.spec").read_text("utf-8")
    for needle in ("kokoro_onnx", "espeakng_loader", "fasttext", "chatreader/data", "pytchat", "web", "console=False", "pystray"):
        assert needle in spec, needle


def test_runtime_closure_includes_transitive_dependencies():
    closure = _build().runtime_closure(["fastapi"])
    assert {"fastapi", "starlette", "pydantic"} <= closure


def test_copy_licenses_writes_files(tmp_path):
    n = _build().copy_licenses({"fastapi", "pytchat", "not-installed-xyz"}, tmp_path)
    assert n >= 1 and any(tmp_path.rglob("*"))


def _fake_fetch(url):
    return b"data:" + url.encode()


def test_gpl_sources_plan_pins_the_locked_versions():
    plan = {e["name"]: e for e in _build().gpl_sources(ROOT / "uv.lock")}
    assert set(plan) == {"phonemizer", "espeakng-loader", "espeak-ng"}
    lock = tomllib.loads((ROOT / "uv.lock").read_text("utf-8"))["package"]
    for name in ("phonemizer", "espeakng-loader"):
        assert plan[name]["version"] == next(p["version"] for p in lock if p["name"] == name)
    assert plan["phonemizer"]["sha256"]  # the sdist hash from uv.lock is checked after the download
    assert plan["espeak-ng"]["version"] == "1.52.0" and re.fullmatch(r"[0-9a-f]{40}", plan["espeak-ng"]["commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", plan["espeakng-loader"]["commit"])


def test_gpl_sources_zip_holds_all_components_and_a_readme(tmp_path):
    b = _build()
    plan = b.gpl_sources(ROOT / "uv.lock")
    z = tmp_path / "s.zip"
    b.build_gpl_sources_zip(z, "0.3.0", plan, fetch=_fake_fetch, verify=False)
    import zipfile
    names = zipfile.ZipFile(z).namelist()
    assert "README.txt" in names and len([n for n in names if n.startswith("sources/")]) == 3
    readme = zipfile.ZipFile(z).read("README.txt").decode()
    for e in plan:
        assert e["name"] in readme and e["url"] in readme


def test_download_rejects_a_wrong_hash():
    import pytest
    with pytest.raises(ValueError):
        _build().fetch_checked("http://x", "0" * 64, fetch=_fake_fetch)


def test_espeakng_loader_licence_is_declared_for_the_main_zip():
    b = _build()
    assert b.LOADER_LICENSE_URL.startswith("https://raw.githubusercontent.com/thewh1teagle/espeakng-loader/")
    assert b.LOADER_LICENSE_SHA256 and (ROOT / "THIRD_PARTY_NOTICES.txt").read_text("utf-8").count("gpl-sources.zip") >= 1


def test_notices_offer_the_source_in_writing():
    notices = (ROOT / "THIRD_PARTY_NOTICES.txt").read_text("utf-8")
    assert "gpl-sources.zip" in notices and "three years" in notices and "Masgod/ChatReader" in notices
