"""Small always-on-top toast shown when a countdown reaches zero."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from .theme import ui_font


class FinishToast(QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(248, 78)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_for(self, anchor: QRect) -> None:
        screen = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
        target = QRect(0, 0, self.width(), self.height())
        target.moveCenter(anchor.center())
        target.moveTop(anchor.top() - self.height() - 10)
        if screen is not None:
            available = screen.availableGeometry()
            if target.top() < available.top() + 4:
                target.moveTop(anchor.bottom() + 10)
            target.moveLeft(
                max(available.left() + 8, min(target.left(), available.right() - target.width() - 8))
            )

        self.setGeometry(target)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._hide_timer.start(3400)

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._on_faded)
        self._fade.start()

    def _on_faded(self) -> None:
        try:
            self._fade.finished.disconnect(self._on_faded)
        except (RuntimeError, TypeError):
            pass
        self.hide()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hide_timer.stop()
        self._fade_out()
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QColor(255, 255, 255, 24))
        painter.setBrush(QColor(28, 30, 34, 244))
        painter.drawRoundedRect(rect, 14, 14)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#6FD3E8"))
        painter.drawRoundedRect(QRect(rect.left(), rect.top(), 4, rect.height()), 2, 2)

        painter.setPen(QColor("#F2F3F5"))
        title_font = ui_font(15, weight=QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(
            rect.adjusted(18, 12, -12, -34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "倒计时结束",
        )

        painter.setPen(QColor("#9CA0A6"))
        painter.setFont(ui_font(11))
        painter.drawText(
            rect.adjusted(18, 40, -12, -10),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "时间到了 · 点击关闭",
        )
        painter.end()
