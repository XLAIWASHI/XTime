"""Reusable large timer preview used by the color and font dialogs."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..resources import make_timer_font


class TimerPreview(QWidget):
    """Draws ``12:34:56`` over a split dark/light strip.

    Showing both halves makes it obvious whether the selected color stays
    readable on dark and light wallpapers.  The colon color is painted
    separately so the colon settings can be judged as well.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._family = "JetBrains Mono"
        self._digit_color = QColor("#E8E8E8")
        self._colon_color = QColor("#888888")
        self._follow = False
        self._font_pixels = 40
        self.setMinimumHeight(74)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_font_family(self, family: str) -> None:
        if family and family != self._family:
            self._family = family
            self.update()

    def set_colors(
        self,
        digit_color: QColor | str,
        colon_color: QColor | str | None = None,
        follow: bool = False,
    ) -> None:
        self._digit_color = QColor(digit_color)
        self._colon_color = QColor(colon_color) if colon_color else QColor("#888888")
        self._follow = bool(follow)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(340, 78)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 12.0
        mid = rect.center().x()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2C2E33"))
        painter.save()
        painter.setClipRect(QRectF(rect.left(), rect.top(), rect.width() / 2.0, rect.height()))
        painter.drawRoundedRect(rect, radius, radius)
        painter.restore()

        painter.setBrush(QColor("#D9D9D6"))
        painter.save()
        painter.setClipRect(QRectF(mid, rect.top(), rect.width() / 2.0, rect.height()))
        painter.drawRoundedRect(rect, radius, radius)
        painter.restore()

        painter.setPen(QColor(255, 255, 255, 26))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        font = make_timer_font(self._family, self._font_pixels)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 101)
        painter.setFont(font)

        for clip_rect in (
            QRectF(rect.left(), rect.top(), rect.width() / 2.0, rect.height()),
            QRectF(mid, rect.top(), rect.width() / 2.0, rect.height()),
        ):
            painter.save()
            painter.setClipRect(clip_rect)
            self._draw_time(painter, rect, font)
            painter.restore()

        painter.end()

    def _draw_time(self, painter: QPainter, rect: QRectF, font: QFont) -> None:
        metrics = QFontMetricsF(font)
        digit_width = metrics.horizontalAdvance("0")
        colon_width = max(metrics.horizontalAdvance(":"), self._font_pixels * 0.28)
        total_width = digit_width * 6.0 + colon_width * 2.0
        start_x = rect.center().x() - total_width / 2.0
        top = rect.top()
        height = rect.height()

        digit_color = QColor(self._digit_color)
        colon_color = QColor(self._digit_color if self._follow else self._colon_color)

        x = start_x
        groups = ("12", ":", "34", ":", "56")
        for text in groups:
            width = colon_width if text == ":" else digit_width * 2.0
            painter.setPen(colon_color if text == ":" else digit_color)
            painter.drawText(
                QRectF(x, top, width, height),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )
            x += width
