"""Generate visual snapshots for review (development helper).

Run from the project root with the virtual environment::

    python build/screenshots.py

The PNG files are written to ``.testwork/shots`` and are not part of the
shipped application.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPalette,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.resources import app_icon, load_bundled_fonts  # noqa: E402
from app.storage import DataStore, DataLocation, format_hms  # noqa: E402
from app.timer_core import TimerCore, TimerMode  # noqa: E402
from app.ui.color_picker import ColorPickerDialog  # noqa: E402
from app.ui.countdown_dialog import CountdownDialog  # noqa: E402
from app.ui.font_dialog import FontDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.stats_dialog import StatsDialog  # noqa: E402
from app.ui.theme import DIALOG_QSS, ui_font  # noqa: E402

OUT = ROOT / ".testwork" / "shots"
OUT.mkdir(parents=True, exist_ok=True)


def make_app() -> QApplication:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(ui_font(13))
    app.setWindowIcon(app_icon())
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1B1C1F"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#EDEEF0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#24262A"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#EDEEF0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2A2D33"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#EDEEF0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#6FD3E8"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#10171A"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#26282C"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#EDEEF0"))
    app.setPalette(palette)
    app.setStyleSheet(DIALOG_QSS)
    load_bundled_fonts()
    return app


def wallpaper(width: int, height: int, *, dark: bool) -> "QImage":
    from PySide6.QtGui import QImage

    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    gradient = QLinearGradient(0, 0, width, height)
    if dark:
        gradient.setColorAt(0.0, QColor("#1B2431"))
        gradient.setColorAt(0.55, QColor("#11151C"))
        gradient.setColorAt(1.0, QColor("#232A22"))
    else:
        gradient.setColorAt(0.0, QColor("#F5F1E8"))
        gradient.setColorAt(0.55, QColor("#E8EEF2"))
        gradient.setColorAt(1.0, QColor("#DDE7DA"))
    painter.fillRect(image.rect(), gradient)

    blobs = (
        (0.15, 0.25, 260, QColor(90, 180, 220, 95 if dark else 70)),
        (0.82, 0.18, 300, QColor(240, 170, 80, 65 if dark else 55)),
        (0.65, 0.85, 340, QColor(80, 200, 160, 55 if dark else 45)),
    )
    for fx, fy, radius, color in blobs:
        radial = QRadialGradient(QPointF(width * fx, height * fy), radius)
        radial.setColorAt(0.0, color)
        transparent = QColor(color)
        transparent.setAlpha(0)
        radial.setColorAt(1.0, transparent)
        painter.setBrush(radial)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(width * fx, height * fy), radius, radius)

    # A few faux desktop items so transparency is easy to judge.
    painter.setPen(QColor(255, 255, 255, 28 if dark else 80))
    for index in range(6):
        y = 90 + index * 70
        painter.drawLine(80, y, 420, y)
    painter.setBrush(QColor(255, 255, 255, 35 if dark else 70))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(width - 330, 120, 230, 150), 18, 18)
    painter.drawRoundedRect(QRectF(width - 300, 330, 200, 90), 14, 14)
    painter.end()
    return image


def composite(window, background) -> "QImage":
    from PySide6.QtGui import QImage

    pixmap = window.grab()
    image = QImage(background)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    target_w = pixmap.width()
    target_h = pixmap.height()
    x = (image.width() - target_w) // 2
    y = (image.height() - target_h) // 2
    painter.drawPixmap(x, y, pixmap)
    painter.end()
    return image


def main() -> int:
    app = make_app()
    data_dir = ROOT / ".testwork" / "shots-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_path = data_dir / "data.json"
    if data_path.exists():
        data_path.unlink()

    store = DataStore(DataLocation(data_path))
    store.load()
    store.settings["confirm_on_exit"] = False
    store.settings["window_pos"] = [0, 0]
    core = TimerCore(TimerMode.COUNTDOWN, 25 * 60)
    window = MainWindow(store, core, DataLocation(data_path))
    window.move(0, 0)
    window.show()
    app.processEvents()
    window.clock.set_time(25 * 60 + 13, animate=False)
    window.clock.set_running(False)
    for button in (
        window.buttons.start_pause,
        window.buttons.reset,
        window.buttons.mode,
        window.buttons.pin,
        window.buttons.stats,
    ):
        button.set_window_hover(0.0)

    dark = wallpaper(1280, 640, dark=True)
    light = wallpaper(1280, 640, dark=False)

    for style in ("faint_gray", "pure_transparent"):
        window._set_background_style(style)
        app.processEvents()
        composite(window, dark).save(str(OUT / f"main-{style}-dark.png"))
        composite(window, light).save(str(OUT / f"main-{style}-light.png"))

    # Hover state.
    window._set_background_style("faint_gray")
    for button in (
        window.buttons.start_pause,
        window.buttons.reset,
        window.buttons.mode,
        window.buttons.pin,
        window.buttons.stats,
    ):
        button.set_window_hover(1.0)
    window.clock.set_time(13 * 60 + 5, animate=False)
    window.buttons.pin.setChecked(True)
    app.processEvents()
    composite(window, dark).save(str(OUT / "main-hover-dark.png"))
    window.buttons.pin.setChecked(False)

    # Dialogs.
    now = datetime.now().astimezone()
    sessions = [
        {
            "id": "a1",
            "mode": "countdown",
            "start": (now - timedelta(hours=2)).isoformat(timespec="seconds"),
            "end": (now - timedelta(hours=1, minutes=35)).isoformat(timespec="seconds"),
            "duration_seconds": 1500,
        },
        {
            "id": "a2",
            "mode": "stopwatch",
            "start": (now - timedelta(hours=5)).isoformat(timespec="seconds"),
            "end": (now - timedelta(hours=3, minutes=48)).isoformat(timespec="seconds"),
            "duration_seconds": 4320,
        },
        {
            "id": "a3",
            "mode": "countdown",
            "start": (now - timedelta(days=3)).isoformat(timespec="seconds"),
            "end": (now - timedelta(days=3) + timedelta(minutes=45)).isoformat(timespec="seconds"),
            "duration_seconds": 2700,
        },
        {
            "id": "a4",
            "mode": "stopwatch",
            "start": (now - timedelta(days=40)).isoformat(timespec="seconds"),
            "end": (now - timedelta(days=40) + timedelta(hours=2)).isoformat(timespec="seconds"),
            "duration_seconds": 7200,
        },
    ]

    stats = StatsDialog(lambda: (sessions, None, data_path))
    stats.show()
    app.processEvents()
    stats.grab().save(str(OUT / "dialog-stats.png"))
    stats.close()

    colors = ColorPickerDialog(
        digit_color="#E8E8E8",
        colon_color="#888888",
        colon_follow=False,
        background_style="pure_transparent",
        font_family="JetBrains Mono",
    )
    colors.show()
    app.processEvents()
    colors.grab().save(str(OUT / "dialog-colors.png"))
    colors.close()

    fonts = FontDialog(
        "JetBrains Mono",
        digit_color="#E8E8E8",
        colon_color="#888888",
        colon_follow=False,
    )
    fonts.show()
    app.processEvents()
    fonts.grab().save(str(OUT / "dialog-fonts.png"))
    fonts.close()

    countdown = CountdownDialog(25 * 60)
    countdown.show()
    app.processEvents()
    countdown.grab().save(str(OUT / "dialog-countdown.png"))
    countdown.close()

    window.core.stop()
    window.store.settings["confirm_on_exit"] = False
    window.close()
    app.processEvents()
    print("saved to", OUT)
    print("data path", data_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
