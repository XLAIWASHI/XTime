"""The row of small icon buttons underneath the clock."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QWidget

from ..resources import icon_pixmap, system_accent_color


class IconButton(QAbstractButton):
    """Small, mostly transparent icon button with a hover highlight."""

    def __init__(self, icon_name: str, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = 14
        self._hovered = False
        self._window_hover = 0.0
        self._accent = False
        self._accent_color = system_accent_color()

        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFixedSize(26, 26)

    def set_icon_name(self, name: str) -> None:
        if name != self._icon_name:
            self._icon_name = name
            self.update()

    def icon_name(self) -> str:
        return self._icon_name

    def set_icon_size(self, size: int) -> None:
        size = max(8, int(size))
        if size != self._icon_size:
            self._icon_size = size
            self.update()

    def set_accent(self, enabled: bool) -> None:
        if enabled != self._accent:
            self._accent = enabled
            self.update()

    def set_window_hover(self, progress: float) -> None:
        progress = max(0.0, min(1.0, float(progress)))
        if abs(progress - self._window_hover) > 0.01:
            self._window_hover = progress
            self.update()

    def _opacity(self) -> float:
        if self._hovered or self.isChecked():
            return 1.0
        return 0.40 + 0.52 * self._window_hover

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return self.size()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        opacity = self._opacity()
        if self.isEnabled():
            if self.isChecked():
                fill = QColor(self._accent_color)
                fill.setAlphaF(0.16)
                painter.setBrush(fill)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 7, 7)
            elif self._hovered:
                painter.setBrush(QColor(255, 255, 255, 20))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 7, 7)

        color = self._accent_color.name() if self.isChecked() else "#F2F2F2"
        x = (self.width() - self._icon_size) / 2.0
        y = (self.height() - self._icon_size) / 2.0
        shadow = icon_pixmap(
            self._icon_name,
            self._icon_size,
            "#000000",
            self.devicePixelRatioF(),
        )
        if not shadow.isNull():
            painter.setOpacity(0.80 * opacity)
            painter.drawPixmap(int(x) + 1, int(y) + 1, shadow)
        pixmap = icon_pixmap(
            self._icon_name,
            self._icon_size,
            color,
            self.devicePixelRatioF(),
        )
        if not pixmap.isNull():
            painter.setOpacity(1.0 if self.isChecked() else opacity)
            painter.drawPixmap(int(x), int(y), pixmap)
        painter.end()


class ButtonBar(QWidget):
    """Centered row of the five main controls."""

    start_pause_clicked = Signal()
    reset_clicked = Signal()
    mode_clicked = Signal()
    pin_toggled = Signal(bool)
    stats_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.start_pause = IconButton("play", "开始 / 暂停 (空格)")
        self.reset = IconButton("reset", "重置 (R)")
        self.mode = IconButton("swap", "切换到正计时 (M)")
        self.pin = IconButton("pin", "始终置顶 (T)")
        self.stats = IconButton("chart", "统计")

        self.pin.setCheckable(True)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)
        self._layout.addStretch(1)
        for button in (self.start_pause, self.reset, self.mode, self.pin, self.stats):
            self._layout.addWidget(button)
        self._layout.addStretch(1)

        self.start_pause.clicked.connect(self.start_pause_clicked)
        self.reset.clicked.connect(self.reset_clicked)
        self.mode.clicked.connect(self.mode_clicked)
        self.pin.toggled.connect(self.pin_toggled)
        self.stats.clicked.connect(self.stats_clicked)

        self._hover_animation = QVariantAnimation(self)
        self._hover_animation.setDuration(140)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation.setStartValue(0.0)
        self._hover_animation.setEndValue(1.0)
        self._hover_animation.valueChanged.connect(self._on_hover_value)

    # ------------------------------------------------------------------
    def set_scale(self, scale: float) -> None:
        button_size = max(24, int(round(26 * scale)))
        icon_size = max(12, int(round(14 * scale)))
        spacing = max(8, int(round(12 * scale)))
        for button in (
            self.start_pause,
            self.reset,
            self.mode,
            self.pin,
            self.stats,
        ):
            button.setFixedSize(button_size, button_size)
            button.set_icon_size(icon_size)
        self._layout.setSpacing(spacing)

    def set_running(self, running: bool) -> None:
        self.start_pause.set_icon_name("pause" if running else "play")
        self.start_pause.setToolTip(
            "暂停 (空格)" if running else "开始 (空格)"
        )

    def set_mode(self, mode: str) -> None:
        target = "正计时" if str(mode) == "countdown" else "倒计时"
        self.mode.setToolTip(f"切换到{target} (M)")

    def set_pinned(self, pinned: bool) -> None:
        if self.pin.isChecked() != bool(pinned):
            self.pin.blockSignals(True)
            self.pin.setChecked(bool(pinned))
            self.pin.blockSignals(False)

    def set_window_hover(self, hovered: bool) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self.start_pause._window_hover)
        self._hover_animation.setEndValue(1.0 if hovered else 0.0)
        self._hover_animation.start()

    def _on_hover_value(self, value: object) -> None:
        progress = float(value)
        for button in (
            self.start_pause,
            self.reset,
            self.mode,
            self.pin,
            self.stats,
        ):
            button.set_window_hover(progress)
