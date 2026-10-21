"""The HH:MM:SS clock display widget."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from ..resources import make_timer_font
from .flip_digit import FlipDigit


class ColonWidget(QWidget):
    """Two bold dots between the digit groups."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("#888888")
        self._alpha = 1.0
        self._font_pixels = 64
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def set_color(self, color: QColor | str) -> None:
        new_color = QColor(color)
        if new_color.isValid() and new_color != self._color:
            self._color = new_color
            self.update()

    def set_alpha(self, alpha: float) -> None:
        alpha = max(0.0, min(1.0, float(alpha)))
        if abs(alpha - self._alpha) > 0.01:
            self._alpha = alpha
            self.update()

    def set_font_pixels(self, pixels: int) -> None:
        self._font_pixels = max(8, int(pixels))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self._color)
        color.setAlphaF(color.alphaF() * self._alpha)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)

        width = self.width()
        height = self.height()
        radius = max(1.4, self._font_pixels * 0.047)
        gap = self._font_pixels * 0.115
        center_y = height / 2.0
        for offset in (-gap, gap):
            painter.drawEllipse(
                width / 2.0 - radius,
                center_y + offset - radius,
                radius * 2.0,
                radius * 2.0,
            )
        painter.end()


class FlipClock(QWidget):
    """Six (or seven) digits plus blinking colons."""

    clicked = Signal()
    drag_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._family = "JetBrains Mono"
        self._color = QColor("#E8E8E8")
        self._colon_color = QColor("#888888")
        self._colon_follow = False
        self._running = False
        self._blink_started = time.monotonic()
        self._last_seconds_value = -1
        self._font_pixels = 64
        self._updating_metrics = False

        self._hundreds = FlipDigit(self)
        self._hours_tens = FlipDigit(self)
        self._hours_ones = FlipDigit(self)
        self._colon1 = ColonWidget(self)
        self._minutes_tens = FlipDigit(self)
        self._minutes_ones = FlipDigit(self)
        self._colon2 = ColonWidget(self)
        self._seconds_tens = FlipDigit(self)
        self._seconds_ones = FlipDigit(self)
        self._digits = [
            self._hundreds,
            self._hours_tens,
            self._hours_ones,
            self._minutes_tens,
            self._minutes_ones,
            self._seconds_tens,
            self._seconds_ones,
        ]
        self._colons = [self._colon1, self._colon2]

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self._layout.addWidget(self._hundreds)
        self._layout.addWidget(self._hours_tens)
        self._layout.addWidget(self._hours_ones)
        self._layout.addWidget(self._colon1)
        self._layout.addWidget(self._minutes_tens)
        self._layout.addWidget(self._minutes_ones)
        self._layout.addWidget(self._colon2)
        self._layout.addWidget(self._seconds_tens)
        self._layout.addWidget(self._seconds_ones)
        self._layout.addStretch(1)

        self._hundreds.hide()
        for widget in self._digits + self._colons:
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)

        self._press_global: QPoint | None = None
        self._window_start: QPoint | None = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._apply_fonts()
        self.set_time(0, animate=False)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_font_family(self, family: str) -> None:
        if family and family != self._family:
            self._family = family
            self._update_metrics(force=True)
            for digit in self._digits:
                digit.update()

    def font_family(self) -> str:
        return self._family

    def font_pixels(self) -> int:
        return self._font_pixels

    def set_colors(
        self, digit_color: QColor | str, colon_color: QColor | str, follow: bool
    ) -> None:
        self._color = QColor(digit_color)
        self._colon_color = QColor(colon_color)
        self._colon_follow = bool(follow)
        for digit in self._digits:
            digit.set_color(self._color)
        active_colon = self._color if self._colon_follow else self._colon_color
        for colon in self._colons:
            colon.set_color(active_colon)

    def set_shadow_strength(self, strength: float) -> None:
        for digit in self._digits:
            digit.set_shadow_strength(strength)

    def set_running(self, running: bool) -> None:
        self._running = bool(running)
        if not self._running:
            self._set_colon_alpha(1.0)
        else:
            self._blink_started = time.monotonic()
            self.refresh_blink()

    def set_time(self, seconds: int, animate: bool = True) -> None:
        seconds = max(0, int(seconds))
        if seconds == self._last_seconds_value:
            self.refresh_blink()
            return

        previous_second = self._last_seconds_value % 60 if self._last_seconds_value >= 0 else None
        hours = min(999, seconds // 3600)
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if previous_second is None or secs != previous_second:
            self._blink_started = time.monotonic()

        show_hundreds = hours >= 100
        if self._hundreds.isVisible() != show_hundreds:
            self._hundreds.setVisible(show_hundreds)
            self._update_metrics(force=True)

        values = {
            self._hundreds: str((hours // 100) % 10) if show_hundreds else "0",
            self._hours_tens: str((hours // 10) % 10),
            self._hours_ones: str(hours % 10),
            self._minutes_tens: str(minutes // 10),
            self._minutes_ones: str(minutes % 10),
            self._seconds_tens: str(secs // 10),
            self._seconds_ones: str(secs % 10),
        }
        for digit, value in values.items():
            digit.set_value(value, animate=animate and digit.isVisible())

        self._last_seconds_value = seconds
        self.refresh_blink()

    def current_text(self) -> str:
        hours = (int(self._hundreds.value()) * 100 if self._hundreds.isVisible() else 0) + int(
            self._hours_tens.value()
        ) * 10 + int(self._hours_ones.value())
        minutes = int(self._minutes_tens.value()) * 10 + int(self._minutes_ones.value())
        secs = int(self._seconds_tens.value()) * 10 + int(self._seconds_ones.value())
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # ------------------------------------------------------------------
    # Blink
    # ------------------------------------------------------------------
    def refresh_blink(self, now: float | None = None) -> None:
        if not self._running:
            self._set_colon_alpha(1.0)
            return
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self._blink_started)
        if elapsed < 0.52:
            alpha = 1.0
        elif elapsed < 0.74:
            t = (elapsed - 0.52) / 0.22
            smooth = t * t * (3.0 - 2.0 * t)
            alpha = 1.0 - 0.68 * smooth
        else:
            alpha = 0.32
        self._set_colon_alpha(alpha)

    def _set_colon_alpha(self, alpha: float) -> None:
        for colon in self._colons:
            colon.set_alpha(alpha)

    # ------------------------------------------------------------------
    # Metrics / layout
    # ------------------------------------------------------------------
    def _apply_fonts(self) -> None:
        self._update_metrics(force=True)

    def _update_metrics(self, force: bool = False) -> None:
        if self._updating_metrics:
            return
        width = max(1, self.width())
        height = max(1, self.height())
        if not force and width < 20:
            return

        self._updating_metrics = True
        try:
            digit_count = 7 if self._hundreds.isVisible() else 6
            width_units = digit_count * 0.60 + 0.44 + 0.10
            pixels = int(min(height * 0.64, width / width_units))
            pixels = max(10, min(pixels, 260))
            if pixels != self._font_pixels or force:
                self._font_pixels = pixels
                font = make_timer_font(self._family, pixels)
                metrics = QFontMetricsF(font)
                digit_width = max(6, int(math.ceil(metrics.horizontalAdvance("0"))))
                colon_width = max(6, int(math.ceil(pixels * 0.22)))
                for digit in self._digits:
                    digit.set_font(font)
                    digit.setFixedSize(QSize(digit_width, height))
                for colon in self._colons:
                    colon.set_font_pixels(pixels)
                    colon.setFixedSize(QSize(colon_width, height))

        finally:
            self._updating_metrics = False

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._update_metrics(force=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(280, 96)

    # ------------------------------------------------------------------
    # Dragging / click
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._window_start = self.window().pos()
            self._dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if (
            self._press_global is not None
            and self._window_start is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._press_global
            if not self._dragging and abs(delta.x()) + abs(delta.y()) >= 4:
                self._dragging = True
            if self._dragging:
                self.window().move(self._window_start + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton and self._press_global is not None:
            was_dragging = self._dragging
            self._press_global = None
            self._window_start = None
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if was_dragging:
                self.drag_finished.emit()
            else:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
