"""Encode the shared artwork in native application-icon containers."""

from pathlib import Path
from PIL import Image


def main():
    assets = Path(__file__).resolve().parents[1] / "assets"
    with Image.open(assets / "icon-master.webp") as source:
        icon = source.convert("RGBA")
        if icon.size != (1024, 1024):
            raise ValueError("Icon master must be 1024 x 1024")
        icon.save(assets / "app-icon.png", optimize=True)
        icon.save(
            assets / "app-icon.ico",
            sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)],
        )
        icon.save(
            assets / "app-icon.icns",
            sizes=[(size, size) for size in (16, 32, 64, 128, 256, 512, 1024)],
        )
    print("Generated PNG, Windows ICO and macOS ICNS icons")


if __name__ == "__main__":
    main()
