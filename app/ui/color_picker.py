"""Time / colon color picker with presets, live preview and contrast hint."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..constants import COLOR_PRESETS, DEFAULT_COLON_COLOR, DEFAULT_FONT_COLOR
from ..resources import system_accent_color
from .preview import TimerPreview
from .theme import apply_dialog_theme, ui_font


def _relative_luminance(color: QColor) -> float:
    def channel(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


class ColorSwatch(QAbstractButton):
    def __init__(self, color: QColor, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._selected = False
        self._hovered = False
        self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(30, 30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(3, 3, -3, -3)
        if self._selected:
            painter.setPen(QColor("#FFFFFF"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(1, 1, -1, -1))
        elif self._hovered:
            painter.setPen(QColor(255, 255, 255, 150))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(1, 1, -1, -1))

        painter.setPen(QColor(255, 255, 255, 40))
        painter.setBrush(self._color)
        painter.drawEllipse(rect)
        painter.end()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(30, 30)


class ColorPickerDialog(QDialog):
    preview_changed = Signal(str, str, bool)

    def __init__(
        self,
        *,
        digit_color: str,
        colon_color: str,
        colon_follow: bool,
        background_style: str,
        font_family: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("时间颜色")
        self.setModal(True)
        self.setMinimumWidth(470)
        self._digit_color = QColor(digit_color)
        self._colon_color = QColor(colon_color)
        self._follow = bool(colon_follow)
        self._background_style = background_style
        self._font_family = font_family
        self._digit_swatches: list[ColorSwatch] = []
        self._colon_swatches: list[ColorSwatch] = []

        heading = QLabel("时间颜色")
        heading.setProperty("heading", True)
        subtitle = QLabel("选择后立即预览，点击“应用”保存")
        subtitle.setProperty("muted", True)
        subtitle.setFont(ui_font(12))

        # ---- digits ---------------------------------------------------
        digit_section = QLabel("数字颜色")
        digit_section.setProperty("section", True)

        presets = list(COLOR_PRESETS) + [("跟随系统", system_accent_color().name().upper())]
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        for index, (label, color_value) in enumerate(presets):
            swatch = ColorSwatch(QColor(color_value), label)
            swatch.clicked.connect(
                lambda checked=False, c=color_value: self._set_digit_color(QColor(c))
            )
            name_label = QLabel(label)
            name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            name_label.setProperty("muted", True)
            name_label.setFont(ui_font(10))
            column = index % 4
            row = (index // 4) * 2
            grid.addWidget(swatch, row, column, Qt.AlignmentFlag.AlignHCenter)
            grid.addWidget(name_label, row + 1, column)
            self._digit_swatches.append(swatch)

        custom_button = QPushButton("自定义颜色…")
        custom_button.clicked.connect(self._pick_digit_color)
        reset_button = QPushButton("恢复默认")
        reset_button.setProperty("flat", True)
        reset_button.clicked.connect(self._reset_defaults)
        digit_actions = QHBoxLayout()
        digit_actions.addWidget(custom_button)
        digit_actions.addStretch(1)
        digit_actions.addWidget(reset_button)

        # ---- colon ----------------------------------------------------
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: rgba(255,255,255,0.08);")

        colon_section = QLabel("冒号颜色")
        colon_section.setProperty("section", True)

        self._follow_box = QCheckBox("跟随数字颜色")
        self._follow_box.setChecked(self._follow)
        self._follow_box.toggled.connect(self._on_follow_toggled)

        colon_row = QHBoxLayout()
        colon_row.setSpacing(8)
        for label, color_value in presets:
            swatch = ColorSwatch(QColor(color_value), label)
            swatch.setFixedSize(24, 24)
            swatch.clicked.connect(
                lambda checked=False, c=color_value: self._set_colon_color(QColor(c))
            )
            colon_row.addWidget(swatch)
            self._colon_swatches.append(swatch)
        colon_row.addStretch(1)

        self._custom_colon = QPushButton("自定义…")
        self._custom_colon.setProperty("flat", True)
        self._custom_colon.clicked.connect(self._pick_colon_color)
        colon_row.addWidget(self._custom_colon)

        # ---- preview --------------------------------------------------
        preview_section = QLabel("预览")
        preview_section.setProperty("section", True)
        self._preview = TimerPreview()
        self._preview.set_font_family(font_family)

        self._warning = QLabel("")
        self._warning.setWordWrap(True)
        self._warning.setFont(ui_font(11))
        self._warning.setStyleSheet("color: #F2B36B;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("应用")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(digit_section)
        layout.addLayout(grid)
        layout.addLayout(digit_actions)
        layout.addWidget(divider)
        layout.addWidget(colon_section)
        layout.addWidget(self._follow_box)
        layout.addLayout(colon_row)
        layout.addSpacing(4)
        layout.addWidget(preview_section)
        layout.addWidget(self._preview)
        layout.addWidget(self._warning)
        layout.addSpacing(4)
        layout.addWidget(buttons)

        self._sync_swatches()
        self._update_preview()
        self._on_follow_toggled(self._follow)
        apply_dialog_theme(self)

    # ------------------------------------------------------------------
    def _set_digit_color(self, color: QColor) -> None:
        if color.isValid():
            self._digit_color = color
            self._sync_swatches()
            self._update_preview()

    def _set_colon_color(self, color: QColor) -> None:
        if color.isValid():
            self._colon_color = color
            self._follow_box.setChecked(False)
            self._sync_swatches()
            self._update_preview()

    def _pick_digit_color(self) -> None:
        color = QColorDialog.getColor(self._digit_color, self, "选择时间数字颜色")
        if color.isValid():
            self._set_digit_color(color)

    def _pick_colon_color(self) -> None:
        color = QColorDialog.getColor(self._colon_color, self, "选择冒号颜色")
        if color.isValid():
            self._set_colon_color(color)

    def _reset_defaults(self) -> None:
        self._digit_color = QColor(DEFAULT_FONT_COLOR)
        self._colon_color = QColor(DEFAULT_COLON_COLOR)
        self._follow_box.setChecked(False)
        self._sync_swatches()
        self._update_preview()

    def _on_follow_toggled(self, checked: bool) -> None:
        self._follow = bool(checked)
        for swatch in self._colon_swatches:
            swatch.setEnabled(not checked)
        self._custom_colon.setEnabled(not checked)
        self._update_preview()

    def _sync_swatches(self) -> None:
        digit_hex = self._digit_color.name().upper()
        colon_hex = self._colon_color.name().upper()
        for swatch in self._digit_swatches:
            swatch.set_selected(swatch.color().name().upper() == digit_hex)
        for swatch in self._colon_swatches:
            swatch.set_selected(swatch.color().name().upper() == colon_hex)
        self._update_preview()

    def _update_preview(self) -> None:
        self._preview.set_colors(self._digit_color, self._colon_color, self._follow)
        self.preview_changed.emit(
            self._digit_color.name().upper(),
            self._colon_color.name().upper(),
            self._follow,
        )

        luminance = _relative_luminance(self._digit_color)
        warning = ""
        if self._background_style == "pure_transparent":
            if luminance > 0.55:
                warning = "⚠ 当前背景为纯透明，浅色字体在浅色壁纸上可能看不清"
            elif luminance < 0.16:
                warning = "⚠ 当前背景为纯透明，深色字体在深色壁纸上可能看不清"
        elif luminance < 0.10:
            warning = "提示：深色字体在当前淡灰背景下对比度可能偏低"
        self._warning.setText(warning)
        self._warning.setVisible(bool(warning))

    # ------------------------------------------------------------------
    def colors(self) -> tuple[str, str, bool]:
        return (
            self._digit_color.name().upper(),
            self._colon_color.name().upper(),
            self._follow,
        )

    @classmethod
    def ask(
        cls,
        parent: QWidget,
        *,
        digit_color: str,
        colon_color: str,
        colon_follow: bool,
        background_style: str,
        font_family: str,
        preview_callback=None,
    ) -> tuple[str, str, bool] | None:
        dialog = cls(
            digit_color=digit_color,
            colon_color=colon_color,
            colon_follow=colon_follow,
            background_style=background_style,
            font_family=font_family,
            parent=parent,
        )
        if preview_callback is not None:
            dialog.preview_changed.connect(preview_callback)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.colors()
        return None
