"""Countdown duration picker (HH:MM:SS)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..constants import MAX_COUNTDOWN_SECONDS
from ..resources import make_timer_font
from ..timer_core import format_hms
from .theme import apply_dialog_theme, ui_font

PRESETS = (5, 10, 15, 25, 45, 60)


class CountdownDialog(QDialog):
    """Three large spin boxes for hours / minutes / seconds."""

    def __init__(self, seconds: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置倒计时")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._result_seconds = max(1, min(MAX_COUNTDOWN_SECONDS, int(seconds)))

        heading = QLabel("设置倒计时")
        heading.setProperty("heading", True)
        subtitle = QLabel("设定后会重新开始本次倒计时")
        subtitle.setProperty("muted", True)
        subtitle.setFont(ui_font(12))

        hours = (self._result_seconds // 3600) % 24
        minutes = (self._result_seconds % 3600) // 60
        secs = self._result_seconds % 60

        self._hours = self._make_spin(0, 23, hours)
        self._minutes = self._make_spin(0, 59, minutes)
        self._seconds = self._make_spin(0, 59, secs)

        fields = QHBoxLayout()
        fields.setSpacing(6)
        for spin, label_text in (
            (self._hours, "时"),
            (self._minutes, "分"),
            (self._seconds, "秒"),
        ):
            column = QVBoxLayout()
            column.setSpacing(6)
            column.addWidget(spin, 0, Qt.AlignmentFlag.AlignHCenter)
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            label.setProperty("muted", True)
            label.setFont(ui_font(11))
            column.addWidget(label)
            fields.addLayout(column)
            if spin is not self._seconds:
                colon = QLabel(":")
                colon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                colon.setFixedHeight(58)
                colon.setFont(make_timer_font("JetBrains Mono", 30))
                colon.setStyleSheet("color: #6A6E75;")
                fields.addWidget(colon)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for minutes_value in PRESETS:
            button = QPushButton(f"{minutes_value} 分")
            button.setProperty("chip", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, value=minutes_value: self._apply_preset(value)
            )
            preset_row.addWidget(button)
        preset_row.addStretch(1)

        hint = QLabel("范围 00:00:01 — 23:59:59")
        hint.setProperty("muted", True)
        hint.setFont(ui_font(11))
        self._invalid = QLabel("倒计时不能为 0，请至少设置 1 秒")
        self._invalid.setStyleSheet("color: #F2B36B;")
        self._invalid.setFont(ui_font(11))
        self._invalid.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("设定")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("primary", True)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self._buttons = buttons

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addSpacing(2)
        layout.addLayout(fields)
        layout.addWidget(hint)
        layout.addWidget(self._invalid)
        layout.addSpacing(2)
        preset_title = QLabel("常用时长")
        preset_title.setProperty("section", True)
        layout.addWidget(preset_title)
        layout.addLayout(preset_row)
        layout.addSpacing(6)
        layout.addWidget(buttons)

        for spin in (self._hours, self._minutes, self._seconds):
            spin.valueChanged.connect(self._validate)
        self._validate()
        apply_dialog_theme(self)

    def _make_spin(self, minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spin.setFixedSize(88, 58)
        spin.setFont(make_timer_font("JetBrains Mono", 32))
        spin.setStyleSheet(
            "QSpinBox { padding: 2px; background: #24262A; border-radius: 10px; }"
            "QSpinBox:focus { border: 1px solid #6FD3E8; }"
        )
        spin.setKeyboardTracking(False)
        return spin

    def _apply_preset(self, minutes: int) -> None:
        total = min(MAX_COUNTDOWN_SECONDS, minutes * 60)
        self._hours.setValue(total // 3600)
        self._minutes.setValue((total % 3600) // 60)
        self._seconds.setValue(total % 60)

    def _current_total(self) -> int:
        return self._hours.value() * 3600 + self._minutes.value() * 60 + self._seconds.value()

    def _validate(self) -> None:
        valid = 1 <= self._current_total() <= MAX_COUNTDOWN_SECONDS
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)
        self._invalid.setVisible(not valid)

    def _on_accept(self) -> None:
        for spin in (self._hours, self._minutes, self._seconds):
            spin.interpretText()
        total = self._current_total()
        if not 1 <= total <= MAX_COUNTDOWN_SECONDS:
            self._validate()
            return
        self._result_seconds = total
        self.accept()

    def seconds(self) -> int:
        return self._result_seconds

    def selected_text(self) -> str:
        return format_hms(self._result_seconds)

    @classmethod
    def ask(cls, parent: QWidget, seconds: int) -> int | None:
        dialog = cls(seconds, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.seconds()
        return None
