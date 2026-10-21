"""A single clock digit.

The value changes directly, Catime style.  There is deliberately no split-flap
or 3D rotation: the digit simply is replaced, while the window background and
the colon blink stay smooth.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class FlipDigit(QWidget):
    """Draws one digit; the historical class name is kept for compatibility."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = "0"
        self._font = QFont()
        self._color = QColor("#E8E8E8")
        self._shadow_strength = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(QSize(8, 16))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def value(self) -> str:
        return self._value

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        metrics = self.fontMetrics()
        return QSize(max(8, metrics.horizontalAdvance("0") + 2), metrics.height() + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(8, 16)

    def set_value(self, value: object, animate: bool = True) -> None:
        # ``animate`` is accepted for call-site compatibility; digits now
        # change directly (Catime style) rather than flipping.
        text = str(value)[:1] if value is not None else ""
        if text == "":
            text = "0"
        if text != self._value:
            self._value = text
            self.update()

    def snap_to(self, value: object) -> None:
        self.set_value(value, animate=False)

    def set_font(self, font: QFont) -> None:
        self._font = QFont(font)
        self.setFont(self._font)
        self.updateGeometry()
        self.update()

    def set_color(self, color: QColor | str) -> None:
        new_color = QColor(color)
        if new_color.isValid() and new_color != self._color:
            self._color = new_color
            self.update()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_shadow_strength(self, strength: float) -> None:
        strength = max(0.0, min(1.0, float(strength)))
        if abs(strength - self._shadow_strength) > 0.01:
            self._shadow_strength = strength
            self.update()

    def is_animating(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        self._draw_glyph(painter, self._value, self._color)
        painter.end()

    def _draw_glyph(self, painter: QPainter, text: str, color: QColor) -> None:
        if not text:
            return
        if self._shadow_strength > 0.01:
            # A crisp, thin outline keeps light glyphs readable on light
            # wallpapers without adding a plate behind the clock.
            path = self._glyph_path(text)
            width = 1.0 + 0.2 * self._shadow_strength
            painter.setPen(QPen(QColor(0, 0, 0, int(150 * self._shadow_strength)), width))
            painter.setBrush(color)
            painter.drawPath(path)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

    def _glyph_path(self, text: str) -> QPainterPath:
        metrics = QFontMetricsF(self._font)
        advance = metrics.horizontalAdvance(text)
        x = (self.width() - advance) / 2.0
        baseline = (self.height() - metrics.height()) / 2.0 + metrics.ascent()
        path = QPainterPath()
        path.addText(QPointF(x, baseline), self._font, text)
        return path
