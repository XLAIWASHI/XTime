"""Resource paths, bundled font loading and SVG icon rendering."""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontInfo,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

from .constants import BUNDLED_FONTS, FONT_FAMILY_FALLBACKS

log = logging.getLogger(__name__)


def app_root() -> Path:
    """Root that holds the ``app`` package, also in a PyInstaller bundle."""

    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "app"
    return Path(__file__).resolve().parent


def asset_path(*parts: str) -> Path:
    return app_root().joinpath("assets", *parts)


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
_loaded_families: list[str] = []


def load_bundled_fonts() -> list[str]:
    """Register the packaged fonts and return the loaded family names."""

    global _loaded_families
    if _loaded_families:
        return list(_loaded_families)

    families: list[str] = []
    font_dir = asset_path("fonts")
    for filename in BUNDLED_FONTS:
        path = font_dir / filename
        if not path.exists():
            log.warning("Bundled font missing: %s", path)
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            log.warning("Could not load font: %s", path)
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
                log.info("Loaded bundled font: %s (%s)", family, filename)

    _loaded_families = families
    return list(families)


def available_families() -> list[str]:
    return sorted(QFontDatabase.families(), key=str.casefold)


def choose_font_family(requested: str | None) -> str:
    """Resolve *requested* against installed families and the fallback chain."""

    installed = {name.casefold(): name for name in QFontDatabase.families()}

    if requested:
        match = installed.get(str(requested).casefold())
        if match:
            return match

    for candidate in FONT_FAMILY_FALLBACKS:
        match = installed.get(candidate.casefold())
        if match:
            return match

    for candidate in load_bundled_fonts():
        match = installed.get(candidate.casefold())
        if match:
            return match

    default_family = QGuiApplication.font().family()
    return installed.get(default_family.casefold(), default_family)


def make_timer_font(family: str, pixel_size: int) -> QFont:
    """Create the timer font, always at weight 700 (F28)."""

    font = QFont(family)
    font.setPixelSize(max(8, int(pixel_size)))
    font.setWeight(QFont.Weight.Bold)
    font.setBold(True)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


@lru_cache(maxsize=512)
def is_monospace(family: str) -> bool:
    try:
        return bool(QFontInfo(QFont(family)).fixedPitch())
    except Exception:
        return False


def has_bold_face(family: str) -> bool:
    try:
        styles = {style.casefold() for style in QFontDatabase.styles(family)}
    except Exception:
        return False
    return any("bold" in style or "black" in style or "heavy" in style for style in styles)


def system_accent_color() -> QColor:
    palette = QGuiApplication.palette()
    color = palette.highlight().color()
    if not color.isValid():
        color = QColor("#6FD3E8")
    return color


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------
def _svg_path(name: str) -> Path:
    if not name.endswith(".svg"):
        name = f"{name}.svg"
    return asset_path("icons", name)


@lru_cache(maxsize=128)
def render_svg_pixmap(
    name: str, size: int, color: str, device_pixel_ratio: float = 1.0
) -> QPixmap:
    """Render an SVG to a pixmap tinted with *color*.

    The source icons are white; tinting with SourceIn keeps their alpha shape.
    """

    path = _svg_path(name)
    if not path.exists():
        log.warning("Icon missing: %s", path)
        return QPixmap()

    ratio = max(1.0, float(device_pixel_ratio))
    pixels = max(1, int(round(size * ratio)))
    renderer = QSvgRenderer(str(path))
    image = QImage(pixels, pixels, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()

    if color:
        tint = QColor(color)
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(image.rect(), tint)
        painter.end()

    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon_pixmap(name: str, size: int, color: str, dpr: float = 1.0) -> QPixmap:
    return render_svg_pixmap(name, int(size), color, float(dpr))


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    ico = asset_path("icons", "app.ico")
    if ico.exists():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon

    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = render_svg_pixmap("app", size, "", 1.0)
        if not pixmap.isNull():
            icon.addPixmap(pixmap)
    return icon
