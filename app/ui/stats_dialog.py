"""Statistics dialog: today / week / month / year / all-time totals."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..resources import make_timer_font
from ..storage import (
    PERIOD_KEYS,
    PERIOD_LABELS,
    aggregate,
    format_duration,
    merge_live_session,
)
from ..timer_core import format_hms
from .theme import ACCENT, apply_dialog_theme, ui_font

log = logging.getLogger(__name__)

DataProvider = Callable[[], tuple[list[dict], dict | None, Path]]


class StatsDialog(QDialog):
    open_data_folder = Signal()

    def __init__(self, provider: DataProvider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("XTime 统计")
        self.setModal(False)
        self.setMinimumSize(500, 470)
        self._provider = provider
        self._path: Path | None = None

        heading = QLabel("累计专注时长")
        heading.setProperty("heading", True)
        subtitle = QLabel("倒计时与正计时分开统计，可按周期对比")
        subtitle.setProperty("muted", True)
        subtitle.setFont(ui_font(12))

        self._hero = QLabel("00:00:00")
        self._hero.setFont(make_timer_font("JetBrains Mono", 38))
        self._hero.setStyleSheet(f"color: {ACCENT};")
        self._hero_sub = QLabel("今日累计 · 倒计时 0 秒 / 正计时 0 秒")
        self._hero_sub.setProperty("muted", True)
        self._hero_sub.setFont(ui_font(12))

        hero_card = QWidget()
        hero_card.setObjectName("heroCard")
        hero_card.setStyleSheet(
            "QWidget#heroCard { background: #212328; border: 1px solid rgba(255,255,255,0.06);"
            " border-radius: 12px; }"
        )
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(18, 12, 18, 12)
        hero_layout.setSpacing(2)
        hero_layout.addWidget(self._hero)
        hero_layout.addWidget(self._hero_sub)

        table_label = QLabel("各周期对比")
        table_label.setProperty("section", True)

        self._table = QTableWidget(5, 4)
        self._table.setHorizontalHeaderLabels(["周期", "倒计时", "正计时", "总计"])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setAlternatingRowColors(False)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setMinimumHeight(250)
        self._table.verticalHeader().setDefaultSectionSize(40)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.horizontalHeaderItem(0).setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._table.setFont(ui_font(12))

        self._summary = QLabel("共 0 次计时")
        self._summary.setProperty("muted", True)
        self._summary.setFont(ui_font(11))

        self._path_label = QLabel("")
        self._path_label.setProperty("muted", True)
        self._path_label.setFont(ui_font(10))
        self._path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        open_button = QPushButton("打开数据文件夹")
        open_button.setProperty("flat", True)
        open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        open_button.clicked.connect(lambda: self.open_data_folder.emit())
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)

        footer = QHBoxLayout()
        footer.addWidget(self._path_label, 1)
        footer.addWidget(open_button)
        footer.addWidget(close_button)

        note = QLabel("会话按开始时间归入对应周期 · 数据可直接编辑")
        note.setProperty("muted", True)
        note.setFont(ui_font(10))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(hero_card)
        layout.addSpacing(2)
        layout.addWidget(table_label)
        layout.addWidget(self._table)
        layout.addWidget(note)
        layout.addWidget(self._summary)
        layout.addSpacing(2)
        layout.addLayout(footer)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self.refresh)

        apply_dialog_theme(self)

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        self.refresh()
        self._refresh_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._refresh_timer.stop()
        super().hideEvent(event)

    def set_data_path(self, path: Path) -> None:
        self._path = Path(path)
        metrics = QFontMetrics(self._path_label.font())
        elided = metrics.elidedText(str(self._path), Qt.TextElideMode.ElideMiddle, 330)
        self._path_label.setText(elided)
        self._path_label.setToolTip(str(self._path))

    def refresh(self) -> None:
        try:
            sessions, live, path = self._provider()
        except Exception:
            log.exception("Statistics provider failed")
            return
        self.set_data_path(path)
        combined = merge_live_session(sessions, live)
        rows = aggregate(combined)

        today = rows["today"]
        self._hero.setText(format_hms(today.total_seconds))
        self._hero_sub.setText(
            f"今日累计 · 倒计时 {format_duration(today.countdown_seconds)}"
            f" / 正计时 {format_duration(today.stopwatch_seconds)}"
        )

        for row_index, key in enumerate(PERIOD_KEYS):
            data = rows[key]
            values = (
                PERIOD_LABELS[key],
                format_duration(data.countdown_seconds),
                format_duration(data.stopwatch_seconds),
                format_duration(data.total_seconds),
            )
            for column, text in enumerate(values):
                item = self._table.item(row_index, column)
                if item is None:
                    item = QTableWidgetItem()
                    self._table.setItem(row_index, column, item)
                item.setText(text)
                item.setTextAlignment(
                    (
                        Qt.AlignmentFlag.AlignLeft
                        if column == 0
                        else Qt.AlignmentFlag.AlignRight
                    )
                    | Qt.AlignmentFlag.AlignVCenter
                )
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                font = QFont(self._table.font())
                if key == "all":
                    font.setWeight(QFont.Weight.Bold)
                else:
                    font.setWeight(QFont.Weight.Normal)
                item.setFont(font)
                color = QColor("#EDEEF0")
                if key == "today" and column == 3:
                    color = QColor(ACCENT)
                elif key == "all":
                    color = QColor("#CFD2D6")
                item.setForeground(color)
            self._table.setRowHeight(row_index, 40)

        total = rows["all"]
        self._summary.setText(
            f"共 {total.total_sessions} 次计时 · 倒计时 {total.countdown_sessions} 次"
            f" / 正计时 {total.stopwatch_sessions} 次"
        )
