"""Render app.svg into the Windows .ico used by PyInstaller and the window."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "app" / "assets" / "icons" / "app.svg"
ICO = ROOT / "app" / "assets" / "icons" / "app.ico"
PNG = ROOT / "app" / "assets" / "icons" / "app.png"
WORK = ROOT / ".testwork" / "icon"

SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed by Qt SVG
    WORK.mkdir(parents=True, exist_ok=True)
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise SystemExit(f"Invalid SVG: {SVG}")

    master = QImage(1024, 1024, QImage.Format.Format_ARGB32_Premultiplied)
    master.fill(Qt.GlobalColor.transparent)
    painter = QPainter(master)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, 1024, 1024))
    painter.end()
    master_path = WORK / "app-1024.png"
    master.save(str(master_path))

    image = Image.open(master_path).convert("RGBA")
    image.resize((256, 256), Image.Resampling.LANCZOS).save(PNG)
    image.save(
        ICO,
        format="ICO",
        sizes=[(size, size) for size in SIZES],
    )
    print(f"wrote {ICO} ({ICO.stat().st_size} bytes)")
    print(f"wrote {PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
