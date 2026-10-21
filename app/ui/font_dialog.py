"""Font-family picker for the timer digits."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..resources import available_families, has_bold_face, is_monospace
from .preview import TimerPreview
from .theme import apply_dialog_theme, ui_font


class FontDialog(QDialog):
    def __init__(
        self,
        family: str,
        *,
        digit_color: str,
        colon_color: str,
        colon_follow: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("字体设置")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._current_family = family
        self._all_families = available_families()

        heading = QLabel("字体")
        heading.setProperty("heading", True)
        subtitle = QLabel("时间数字始终使用粗体（700），不可更改")
        subtitle.setProperty("muted", True)
        subtitle.setFont(ui_font(12))

        family_label = QLabel("字体族")
        family_label.setProperty("section", True)
        self._combo = QComboBox()
        self._combo.setMaxVisibleItems(16)
        self._combo.currentTextChanged.connect(self._on_family_changed)

        self._mono_only = QCheckBox("只显示等宽字体（推荐）")
        self._mono_only.setChecked(True)
        self._mono_only.toggled.connect(self._rebuild_combo)

        weight_row = QHBoxLayout()
        weight_label = QLabel("粗细")
        weight_label.setProperty("muted", True)
        weight_value = QLabel("粗体 700（固定）")
        weight_value.setStyleSheet("color: #EDEEF0; font-weight: 700;")
        weight_row.addWidget(weight_label)
        weight_row.addStretch(1)
        weight_row.addWidget(weight_value)

        self._meta = QLabel("")
        self._meta.setProperty("muted", True)
        self._meta.setFont(ui_font(11))
        self._meta.setWordWrap(True)

        preview_label = QLabel("预览")
        preview_label.setProperty("section", True)
        self._preview = TimerPreview()
        self._preview.set_colors(digit_color, colon_color, colon_follow)

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
        layout.addWidget(family_label)
        layout.addWidget(self._combo)
        layout.addWidget(self._mono_only)
        layout.addLayout(weight_row)
        layout.addWidget(self._meta)
        layout.addSpacing(4)
        layout.addWidget(preview_label)
        layout.addWidget(self._preview)
        layout.addSpacing(4)
        layout.addWidget(buttons)

        self._rebuild_combo()
        apply_dialog_theme(self)

    # ------------------------------------------------------------------
    def _rebuild_combo(self) -> None:
        self._combo.blockSignals(True)
        current = self._combo.currentText() or self._current_family
        self._combo.clear()
        families = self._all_families
        if self._mono_only.isChecked():
            families = [name for name in families if is_monospace(name)]
        if current not in families:
            families.insert(0, current)
        self._combo.addItems(families)
        index = self._combo.findText(current)
        self._combo.setCurrentIndex(max(0, index))
        self._combo.blockSignals(False)
        self._on_family_changed(self._combo.currentText())

    def _on_family_changed(self, family: str) -> None:
        if not family:
            return
        self._current_family = family
        self._preview.set_font_family(family)
        notes = []
        notes.append("等宽字体" if is_monospace(family) else "非等宽字体，切换时数字宽度可能轻微变化")
        if not has_bold_face(family):
            notes.append("该字体没有独立粗体字形，将使用合成粗体")
        self._meta.setText(" · ".join(notes))

    def selected_family(self) -> str:
        return self._combo.currentText() or self._current_family

    @classmethod
    def ask(cls, parent: QWidget, family: str, **preview_kwargs) -> str | None:
        dialog = cls(family, parent=parent, **preview_kwargs)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_family()
        return None
