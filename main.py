"""XTime entry point: desktop flip-page countdown / stopwatch."""

from __future__ import annotations

import ctypes
import logging
import logging.handlers
import sys
import traceback

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from app.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION, LOG_FILENAME
from app.resources import app_icon, load_bundled_fonts
from app.storage import DataStore, application_dir, resolve_data_path
from app.timer_core import TimerCore, TimerMode, parse_hms
from app.ui.main_window import MainWindow
from app.ui.theme import DIALOG_QSS, ui_font

log = logging.getLogger(__name__)


def _configure_logging(log_path) -> None:
    handlers: list[logging.Handler] = []
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=256 * 1024,
            backupCount=1,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        handlers.append(file_handler)
    except OSError:
        pass

    if sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
        handlers.append(stream)

    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)


def _apply_dark_palette(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1B1C1F"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#EDEEF0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#24262A"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#202226"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#EDEEF0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2A2D33"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#EDEEF0"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FF7A7A"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#6FD3E8"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#10171A"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#26282C"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#EDEEF0"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#767A81"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#666A71"))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#666A71")
    )
    app.setPalette(palette)


def _set_windows_app_id() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XTime.Timer.1")
    except Exception:
        pass


def _install_excepthook() -> None:
    def handle(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger(__name__).critical("Unhandled exception:\n%s", text)
        try:
            QMessageBox.critical(
                None,
                "XTime 遇到错误",
                "程序遇到未处理的错误，详细信息已写入日志。\n\n"
                f"{exc_type.__name__}: {exc_value}",
            )
        except Exception:
            pass

    sys.excepthook = handle


def main() -> int:
    location = resolve_data_path(application_dir())
    store = DataStore(location)
    _configure_logging(store.path.with_name(LOG_FILENAME))
    log.info("XTime %s starting", APP_VERSION)
    log.info("Data file: %s (fallback=%s)", store.path, location.is_fallback)
    if location.reason:
        log.info("Fallback reason: %s", location.reason)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setFont(ui_font(13))
    app.setWindowIcon(app_icon())
    _apply_dark_palette(app)
    app.setStyleSheet(DIALOG_QSS)

    load_bundled_fonts()

    lock = QLockFile(str(store.path.with_name("xtime.lock")))
    lock.setStaleLockTime(15_000)
    if not lock.tryLock(120):
        QMessageBox.information(
            None,
            APP_NAME,
            "XTime 已经在运行了。\n请使用任务栏或系统托盘中的窗口。",
        )
        return 0

    try:
        store.load()
        settings = store.settings
        mode = TimerMode.from_value(settings.get("last_mode"))
        countdown = parse_hms(str(settings.get("last_countdown", "00:25:00")))
        core = TimerCore(mode=mode, countdown_seconds=countdown)
        _install_excepthook()

        window = MainWindow(store, core, location)
        window.show()
        exit_code = app.exec()
    finally:
        lock.unlock()

    log.info("XTime exited with code %s", exit_code)
    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
