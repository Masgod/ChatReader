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
