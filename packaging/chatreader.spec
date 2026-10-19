# PyInstaller spec: a windowless folder build named ChatReader.
# Build with:  uv run --group build python packaging/build.py
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = [(str(root / "src" / "chatreader" / "web"), "chatreader/web")], [], [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on", "pystray._win32",
]
for pkg in ("kokoro_onnx", "espeakng_loader", "lingua", "pytchat"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(root / "src" / "chatreader" / "__main__.py")],
    pathex=[str(root / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ChatReader", console=False,
          icon=str(root / "packaging" / "icon.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="ChatReader")
