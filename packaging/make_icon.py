"""Write packaging/icon.ico from the same drawing the tray uses."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chatreader.tray import _image  # noqa: E402


def main() -> Path:
    out = Path(__file__).resolve().parent / "icon.ico"
    _image().save(out, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    return out


if __name__ == "__main__":
    print(main())
