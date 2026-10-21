"""Frameless translucent main window for XTime."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..constants import (
    APP_NAME,
    BASE_HEIGHT,
    BASE_RADIUS,
    BASE_WIDTH,
    MAX_SCALE,
    MIN_SCALE,
    SCALE_STEP,
)
from ..platform import apply_background_blur
from ..resources import app_icon
from ..storage import DataLocation, DataStore, format_hms
from ..timer_core import TimerCore, TimerMode, TimerState
from .button_bar import ButtonBar
from .color_picker import ColorPickerDialog
from .countdown_dialog import CountdownDialog
from .finish_toast import FinishToast
from .flip_clock import FlipClock
from .font_dialog import FontDialog
from .stats_dialog import StatsDialog
from .theme import style_menu, ui_font

log = logging.getLogger(__name__)


class MainWindow(QWidget):
    """The always-at-hand timer strip."""

    def __init__(
        self,
        store: DataStore,
        core: TimerCore,
        location: DataLocation,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.core = core
        self.location = location
        settings = store.settings

        self._scale = float(settings["window_scale"])
        self._bg_style = str(settings["background_style"])
        self._bg_alpha = float(settings["background_alpha"])
        self._blur_enabled = bool(settings["blur_enabled"])
        self._blur_active = False
        self._digit_color = str(settings["font_color"])
        self._colon_color = str(settings["colon_color"])
        self._colon_follow = bool(settings["colon_follow_digit"])
        self._font_family = str(settings["font_family"])
        self._sound_enabled = bool(settings["sound_enabled"])
        self._confirm_on_exit = bool(settings["confirm_on_exit"])
        # ``last_countdown`` is updated only when the user explicitly sets a
        # duration, never when a running countdown exits.  Sessions store
        # elapsed seconds exclusively; remaining time is not persisted.
        self._radius = BASE_RADIUS
        self._save_error_shown = False
        self._fallback_notified = False
        self._hovered = False
        self._stats_dialog: StatsDialog | None = None
        self._context_menu: QMenu | None = None

        self._background_press: QPoint | None = None
        self._background_start: QPoint | None = None
        self._background_dragging = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if bool(settings["always_on_top"]):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)

        # ---- widgets --------------------------------------------------
        self.clock = FlipClock(self)
        self.buttons = ButtonBar(self)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(4)
        self._layout.addWidget(self.clock, 1)
        self._layout.addWidget(self.buttons, 0)

        # ---- timers ---------------------------------------------------
        self._tick_timer = QTimer(self)
        self._tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick_timer.setInterval(50)
        self._tick_timer.timeout.connect(self._on_tick)

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(30_000)
        self._flush_timer.timeout.connect(self._flush_live_session)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._persist_now)

        self._toast = FinishToast()

        # ---- clock fade ----------------------------------------------
        self._clock_effect = QGraphicsOpacityEffect(self.clock)
        self._clock_effect.setOpacity(1.0)
        self.clock.setGraphicsEffect(self._clock_effect)
        self._clock_fade = QPropertyAnimation(self._clock_effect, b"opacity", self)
        self._clock_fade.setDuration(180)
        self._clock_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        # ---- wiring ---------------------------------------------------
        self.clock.clicked.connect(self._on_clock_clicked)
        self.clock.drag_finished.connect(self._on_drag_finished)
        self.clock.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clock.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.clock.mapToGlobal(pos))
        )

        self.buttons.start_pause_clicked.connect(self._toggle_running)
        self.buttons.reset_clicked.connect(self._reset)
        self.buttons.mode_clicked.connect(self._toggle_mode)
        self.buttons.pin_toggled.connect(self._set_always_on_top)
        self.buttons.stats_clicked.connect(self._show_stats)
        self.buttons.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.buttons.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.buttons.mapToGlobal(pos))
        )

        self._apply_scale_layout(initial=True)
        self._apply_colors()
        self.buttons.set_pinned(bool(settings["always_on_top"]))
        self.buttons.set_mode(self.core.mode.value)
        self.buttons.set_window_hover(False)
        self._sync_after_command(animate=False)
        self._restore_position()

        self._create_shortcuts()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._filter_installed = app is not None

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    def _create_shortcuts(self) -> None:
        bindings = (
            ("Space", self._toggle_running),
            ("R", self._reset),
            ("T", self._toggle_pin),
            ("M", self._toggle_mode),
            ("C", self._open_color_dialog),
            ("Ctrl+Up", lambda: self._nudge_scale(1)),
            ("Ctrl+Down", lambda: self._nudge_scale(-1)),
        )
        self._shortcuts: list[QShortcut] = []
        for sequence, callback in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _restore_position(self) -> None:
        position = self.store.settings.get("window_pos", [200, 300])
        try:
            x, y = int(position[0]), int(position[1])
        except (TypeError, ValueError, IndexError):
            x, y = 200, 300
        self.move(x, y)
        self._ensure_visible()

    def _apply_scale_layout(self, initial: bool = False) -> None:
        width = max(1, int(round(BASE_WIDTH * self._scale)))
        height = max(1, int(round(BASE_HEIGHT * self._scale)))
        self._radius = max(8, int(round(BASE_RADIUS * self._scale)))

        margin = max(6, int(round(10 * self._scale)))
        spacing = max(2, int(round(4 * self._scale)))
        bar_height = max(24, int(round(26 * self._scale)))

        self._layout.setContentsMargins(margin, margin, margin, margin)
        self._layout.setSpacing(spacing)
        self.buttons.set_scale(self._scale)
        self.buttons.setFixedHeight(bar_height)
        self.setFixedSize(width, height)
        self.update()
        if not initial and self.isVisible():
            QTimer.singleShot(0, self._apply_blur)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        if self._bg_style == "faint_gray":
            color = QColor(30, 30, 30)
            alpha = self._bg_alpha * (0.60 if self._blur_active else 1.0)
            color.setAlphaF(alpha)
            painter.fillPath(path, color)
            painter.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
            painter.drawPath(path)
        # pure_transparent paints no background at all
        painter.end()

    # ------------------------------------------------------------------
    # Core commands
    # ------------------------------------------------------------------
    def _on_tick(self) -> None:
        snapshot = self.core.tick()
        self.clock.set_time(snapshot.display_seconds, animate=True)
        if snapshot.just_finished:
            self._handle_countdown_finished()
            return
        if snapshot.state is not TimerState.RUNNING:
            self._tick_timer.stop()
        self._drain_sessions()

    def _toggle_running(self) -> None:
        if self.core.is_running:
            self.core.pause()
            self._sync_after_command(animate=False)
            self._drain_sessions()
        else:
            self.core.start()
            self._sync_after_command(animate=False)
            self._tick_timer.start()
            self._flush_timer.start()
            self._on_tick()
            self._schedule_save()

    def _reset(self) -> None:
        self.core.reset()
        self._sync_after_command(animate=False)
        self._drain_sessions()
        self._schedule_save()

    def _set_mode(self, mode: TimerMode, *, ask: bool = True) -> None:
        if mode is self.core.mode:
            return
        if ask and self.core.state is not TimerState.IDLE:
            reply = QMessageBox.question(
                self,
                "切换模式",
                "当前计时尚未结束，切换模式会停止并保存这次计时。\n继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.core.set_mode(mode)
        self._drain_sessions()
        self._sync_after_command(animate=False)
        self.store.settings["last_mode"] = mode.value
        self._fade_clock()
        self._schedule_save()

    def _toggle_mode(self) -> None:
        target = (
            TimerMode.STOPWATCH
            if self.core.mode is TimerMode.COUNTDOWN
            else TimerMode.COUNTDOWN
        )
        self._set_mode(target)

    def _sync_after_command(self, animate: bool = False) -> None:
        snapshot = self.core.snapshot()
        self.clock.set_time(snapshot.display_seconds, animate=animate)
        running = snapshot.state is TimerState.RUNNING
        self.clock.set_running(running)
        self.buttons.set_running(running)
        self.buttons.set_mode(snapshot.mode.value)
        self.buttons.set_pinned(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        self._update_clock_tooltip()
        if running:
            if not self._tick_timer.isActive():
                self._tick_timer.start()
            if not self._flush_timer.isActive():
                self._flush_timer.start()
        else:
            self._tick_timer.stop()
            self._flush_timer.stop()

    def _handle_countdown_finished(self) -> None:
        self._tick_timer.stop()
        self._flush_timer.stop()
        self.clock.set_running(False)
        self.clock.set_time(0, animate=True)
        self.buttons.set_running(False)
        self._drain_sessions()
        self._persist_now(show_error=False)
        if self._sound_enabled:
            QApplication.beep()
        QApplication.alert(self, 0)
        self._toast.show_for(self.frameGeometry())

    def _flush_live_session(self) -> None:
        live = self.core.live_session()
        if not live:
            return
        self.store.upsert_session(live)
        self._persist_now(show_error=False)

    def _drain_sessions(self) -> None:
        sessions = self.core.drain_sessions()
        if not sessions:
            return
        for session in sessions:
            self.store.upsert_session(session)
        self._persist_now(show_error=False)

    # ------------------------------------------------------------------
    # Countdown
    # ------------------------------------------------------------------
    def _on_clock_clicked(self) -> None:
        if self.core.mode is TimerMode.COUNTDOWN:
            self._open_countdown_dialog()

    def _open_countdown_dialog(self) -> None:
        if self.core.mode is not TimerMode.COUNTDOWN:
            return
        seconds = CountdownDialog.ask(self, self.core.initial_seconds)
        if seconds is None:
            return
        self.core.set_countdown_seconds(seconds)
        self._sync_after_command(animate=False)
        self._drain_sessions()
        self.store.settings["last_countdown"] = format_hms(seconds)
        self._schedule_save()

    # ------------------------------------------------------------------
    # Colors / fonts / background
    # ------------------------------------------------------------------
    def _apply_colors(self) -> None:
        self.clock.set_colors(self._digit_color, self._colon_color, self._colon_follow)
        self.clock.set_shadow_strength(1.0 if self._bg_style == "pure_transparent" else 0.8)
        self.update()

    def _preview_colors(self, digit: str, colon: str, follow: bool) -> None:
        self._digit_color = digit
        self._colon_color = colon
        self._colon_follow = follow
        self._apply_colors()

    def _open_color_dialog(self) -> None:
        original = (self._digit_color, self._colon_color, self._colon_follow)
        dialog = ColorPickerDialog(
            digit_color=self._digit_color,
            colon_color=self._colon_color,
            colon_follow=self._colon_follow,
            background_style=self._bg_style,
            font_family=self._font_family,
            parent=self,
        )
        dialog.preview_changed.connect(self._preview_colors)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self._digit_color, self._colon_color, self._colon_follow = dialog.colors()
            self._apply_colors()
            self._schedule_save()
        else:
            self._digit_color, self._colon_color, self._colon_follow = original
            self._apply_colors()

    def _open_font_dialog(self) -> None:
        family = FontDialog.ask(
            self,
            self._font_family,
            digit_color=self._digit_color,
            colon_color=self._colon_color,
            colon_follow=self._colon_follow,
        )
        if family:
            self._font_family = family
            self.clock.set_font_family(family)
            self._schedule_save()

    def _set_background_style(self, style: str) -> None:
        if style not in ("faint_gray", "pure_transparent"):
            return
        self._bg_style = style
        self.clock.set_shadow_strength(1.0 if style == "pure_transparent" else 0.8)
        self._apply_blur()
        self.update()
        self._schedule_save()

    def _set_background_alpha(self, alpha: float) -> None:
        self._bg_alpha = max(0.10, min(0.30, float(alpha)))
        if self._blur_active:
            self._apply_blur()
        self.update()
        self._schedule_save()

    def _set_blur_enabled(self, enabled: bool) -> None:
        self._blur_enabled = bool(enabled)
        self._apply_blur()
        self._schedule_save()

    def _set_sound_enabled(self, enabled: bool) -> None:
        self._sound_enabled = bool(enabled)
        self.store.settings["sound_enabled"] = self._sound_enabled
        self._schedule_save()

    def _apply_blur(self) -> None:
        if not self.isVisible():
            return
        enabled = self._bg_style == "faint_gray" and self._blur_enabled
        active = False
        if enabled:
            active = apply_background_blur(
                self,
                enabled=True,
                alpha=self._bg_alpha,
                radius=self._radius,
            )
        else:
            apply_background_blur(self, enabled=False, alpha=self._bg_alpha, radius=self._radius)
        self._blur_active = bool(active)
        self.update()

    # ------------------------------------------------------------------
    # Scale / pin / position
    # ------------------------------------------------------------------
    def _set_scale(self, scale: float) -> None:
        new_scale = max(MIN_SCALE, min(MAX_SCALE, float(scale)))
        if abs(new_scale - self._scale) < 0.001:
            return
        center = self.geometry().center()
        self._scale = new_scale
        self._apply_scale_layout()
        width = int(round(BASE_WIDTH * self._scale))
        height = int(round(BASE_HEIGHT * self._scale))
        rect = QRect(0, 0, width, height)
        rect.moveCenter(center)
        self.setGeometry(rect)
        self._ensure_visible()
        self._schedule_save()

    def _nudge_scale(self, direction: int) -> None:
        factor = SCALE_STEP if direction > 0 else 1.0 / SCALE_STEP
        self._set_scale(self._scale * factor)

    def _set_always_on_top(self, enabled: bool) -> None:
        enabled = bool(enabled)
        is_on_top = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if enabled == is_on_top:
            self.buttons.set_pinned(enabled)
            return
        geometry = self.geometry()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        self.setGeometry(geometry)
        self.buttons.set_pinned(enabled)
        self.store.settings["always_on_top"] = enabled
        self._schedule_save()
        QTimer.singleShot(0, self._apply_blur)

    def _toggle_pin(self) -> None:
        self._set_always_on_top(
            not bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        )

    def _on_drag_finished(self) -> None:
        self.store.settings["window_pos"] = [self.x(), self.y()]
        self._schedule_save()

    def _ensure_visible(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        rect = self.frameGeometry()
        for screen in screens:
            available = screen.availableGeometry()
            if available.intersected(rect).width() >= 80 and available.intersected(rect).height() >= 40:
                target = available
                break
        else:
            screen = QGuiApplication.primaryScreen()
            target = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
            rect.moveCenter(target.center())
            self.move(rect.topLeft())
            return

        x = min(max(rect.left(), target.left() + 4), target.right() - rect.width() - 4)
        y = min(max(rect.top(), target.top() + 4), target.bottom() - rect.height() - 4)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _capture_settings(self) -> None:
        snapshot = self.core.snapshot()
        self.store.settings.update(
            {
                "last_mode": snapshot.mode.value,
                "always_on_top": bool(
                    self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
                ),
                "window_pos": [self.x(), self.y()],
                "window_scale": round(self._scale, 4),
                "background_style": self._bg_style,
                "background_alpha": round(self._bg_alpha, 3),
                "font_family": self._font_family,
                "font_weight": 700,
                "font_color": self._digit_color,
                "colon_color": self._colon_color,
                "colon_follow_digit": self._colon_follow,
                "blur_enabled": self._blur_enabled,
                "sound_enabled": self._sound_enabled,
            }
        )

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _persist_now(self, *, show_error: bool = True) -> None:
        self._save_timer.stop()
        self._capture_settings()
        try:
            self.store.save()
            self._save_error_shown = False
        except OSError as exc:
            log.error("Could not save %s: %s", self.store.path, exc)
            if show_error and not self._save_error_shown:
                self._save_error_shown = True
                QMessageBox.warning(
                    self,
                    "无法保存数据",
                    f"数据文件写入失败：\n{self.store.path}\n\n{exc}",
                )

    # ------------------------------------------------------------------
    # Windows / dialogs
    # ------------------------------------------------------------------
    def _open_data_folder(self) -> None:
        url = QUrl.fromLocalFile(str(self.store.path.parent))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "打开失败", f"无法打开文件夹：\n{self.store.path.parent}")

    def _show_stats(self) -> None:
        if self._stats_dialog is None:
            self._stats_dialog = StatsDialog(self._stats_data, self)
            self._stats_dialog.open_data_folder.connect(self._open_data_folder)
        self._stats_dialog.set_data_path(self.store.path)
        self._stats_dialog.show()
        self._stats_dialog.raise_()
        self._stats_dialog.activateWindow()

    def _stats_data(self) -> tuple[list[dict], dict | None, Path]:
        return list(self.store.sessions), self.core.live_session(), self.store.path

    def _maybe_notify_fallback(self) -> None:
        if self._fallback_notified:
            return
        self._fallback_notified = True
        if not self.location.is_fallback:
            return
        if bool(self.store.settings.get("fallback_notice_shown", False)):
            return
        QMessageBox.information(
            self,
            "数据保存位置",
            "程序所在目录不可写，数据将保存到用户目录：\n\n"
            f"{self.store.path}\n\n"
            "右键菜单中的“打开数据文件夹”可以直接定位。",
        )
        self.store.settings["fallback_notice_shown"] = True
        self._persist_now(show_error=False)

    def _fade_clock(self) -> None:
        self._clock_fade.stop()
        self._clock_fade.setStartValue(0.05)
        self._clock_fade.setEndValue(1.0)
        self._clock_fade.start()

    def _update_clock_tooltip(self) -> None:
        if self.core.mode is TimerMode.COUNTDOWN:
            text = "倒计时 · 点击时间设置时长 · 拖动移动 · 滚轮缩放"
        else:
            text = "正计时 · 拖动移动 · 滚轮缩放"
        self.clock.setToolTip(text)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = self._build_context_menu()
        self._context_menu = menu
        menu.exec(global_pos)
        menu.deleteLater()
        self._context_menu = None

    def _build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        style_menu(menu)

        running = self.core.is_running
        start_action = menu.addAction("暂停" if running else "开始")
        start_action.triggered.connect(self._toggle_running)
        reset_action = menu.addAction("重置")
        reset_action.triggered.connect(self._reset)

        menu.addSeparator()
        mode_text = (
            "切换到正计时"
            if self.core.mode is TimerMode.COUNTDOWN
            else "切换到倒计时"
        )
        mode_action = menu.addAction(mode_text)
        mode_action.triggered.connect(self._toggle_mode)

        pin_action = menu.addAction("始终置顶")
        pin_action.setCheckable(True)
        pin_action.setChecked(
            bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        )
        pin_action.toggled.connect(
            lambda checked: QTimer.singleShot(0, lambda: self._set_always_on_top(checked))
        )

        menu.addSeparator()
        background = menu.addMenu("背景")
        group = QActionGroup(background)
        group.setExclusive(True)
        faint = background.addAction("淡灰透明")
        faint.setCheckable(True)
        faint.setChecked(self._bg_style == "faint_gray")
        pure = background.addAction("纯透明")
        pure.setCheckable(True)
        pure.setChecked(self._bg_style == "pure_transparent")
        group.addAction(faint)
        group.addAction(pure)
        faint.triggered.connect(lambda: self._set_background_style("faint_gray"))
        pure.triggered.connect(lambda: self._set_background_style("pure_transparent"))

        background.addSeparator()
        blur_action = background.addAction("轻量磨砂（实验）")
        blur_action.setCheckable(True)
        blur_action.setChecked(self._blur_enabled)
        blur_action.setEnabled(self._bg_style == "faint_gray")
        blur_action.toggled.connect(self._set_blur_enabled)

        slider_row = QWidget(background)
        slider_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        slider_layout = QHBoxLayout(slider_row)
        slider_layout.setContentsMargins(14, 6, 14, 6)
        slider_layout.setSpacing(8)
        slider_label = QLabel("透明度")
        slider_label.setStyleSheet("color: #9CA0A6;")
        slider_label.setFont(ui_font(11))
        slider = QSlider(Qt.Orientation.Horizontal, slider_row)
        slider.setRange(10, 30)
        slider.setValue(int(round(self._bg_alpha * 100)))
        slider.setFixedWidth(100)
        slider.setEnabled(self._bg_style == "faint_gray")
        value_label = QLabel(f"{int(round(self._bg_alpha * 100))}%")
        value_label.setStyleSheet("color: #EDEEF0;")
        value_label.setFont(ui_font(11))
        value_label.setFixedWidth(34)
        slider_layout.addWidget(slider_label)
        slider_layout.addWidget(slider)
        slider_layout.addWidget(value_label)
        slider_action = QWidgetAction(background)
        slider_action.setDefaultWidget(slider_row)
        background.addAction(slider_action)

        def on_alpha_changed(value: int) -> None:
            value_label.setText(f"{value}%")
            self._set_background_alpha(value / 100.0)

        slider.valueChanged.connect(on_alpha_changed)

        menu.addSeparator()
        color_action = menu.addAction("时间颜色…")
        color_action.triggered.connect(self._open_color_dialog)
        font_action = menu.addAction("字体设置…")
        font_action.triggered.connect(self._open_font_dialog)

        zoom_menu = menu.addMenu("缩放")
        zoom_group = QActionGroup(zoom_menu)
        zoom_group.setExclusive(True)
        for percent in (60, 80, 100, 125, 150, 200):
            action = zoom_menu.addAction(f"{percent}%")
            action.setCheckable(True)
            action.setChecked(abs(self._scale - percent / 100.0) < 0.005)
            zoom_group.addAction(action)
            action.triggered.connect(
                lambda checked=False, value=percent / 100.0: QTimer.singleShot(
                    0, lambda: self._set_scale(value)
                )
            )
        zoom_menu.addSeparator()
        current_zoom = zoom_menu.addAction(f"当前 {int(round(self._scale * 100))}%")
        current_zoom.setEnabled(False)

        menu.addSeparator()
        open_folder_action = menu.addAction("打开数据文件夹")
        open_folder_action.triggered.connect(self._open_data_folder)
        stats_action = menu.addAction("统计…")
        stats_action.triggered.connect(self._show_stats)
        sound_action = menu.addAction("归零提示音")
        sound_action.setCheckable(True)
        sound_action.setChecked(self._sound_enabled)
        sound_action.toggled.connect(self._set_sound_enabled)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.close)
        return menu

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._show_context_menu(event.globalPos())
        event.accept()

    # ------------------------------------------------------------------
    # Mouse / wheel / hover
    # ------------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._refresh_hover()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._refresh_hover()
        super().leaveEvent(event)

    def _refresh_hover(self) -> None:
        if not self.isVisible():
            inside = False
        else:
            inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if inside != self._hovered:
            self._hovered = inside
            self.buttons.set_window_hover(inside)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt naming
        event_type = event.type()
        if event_type in (
            QEvent.Type.MouseMove,
            QEvent.Type.Enter,
            QEvent.Type.Leave,
        ):
            self._refresh_hover()
        elif event_type == QEvent.Type.Wheel and self.isVisible():
            if (
                QApplication.activeModalWidget() is None
                and hasattr(watched, "window")
                and watched.window() is self
            ):
                delta = event.angleDelta().y()
                if delta:
                    factor = SCALE_STEP if delta > 0 else 1.0 / SCALE_STEP
                    self._set_scale(self._scale * factor)
                    return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = SCALE_STEP if delta > 0 else 1.0 / SCALE_STEP
        self._set_scale(self._scale * factor)
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._background_press = event.globalPosition().toPoint()
            self._background_start = self.pos()
            self._background_dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if (
            self._background_press is not None
            and self._background_start is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._background_press
            if not self._background_dragging and abs(delta.x()) + abs(delta.y()) >= 4:
                self._background_dragging = True
            if self._background_dragging:
                self.move(self._background_start + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton and self._background_press is not None:
            dragged = self._background_dragging
            self._background_press = None
            self._background_start = None
            self._background_dragging = False
            if dragged:
                self._on_drag_finished()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_blur)
        QTimer.singleShot(350, self._maybe_notify_fallback)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.core.is_running and self._confirm_on_exit:
            reply = QMessageBox.question(
                self,
                "退出 XTime",
                "正在计时，确定退出吗？\n退出前会自动保存这次计时。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        if getattr(self, "_filter_installed", False):
            app = QApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            self._filter_installed = False
        self._tick_timer.stop()
        self._flush_timer.stop()
        self._save_timer.stop()
        if self.core.is_running:
            self.core.stop()
        self._drain_sessions()
        if self._stats_dialog is not None:
            self._stats_dialog.close()
        self._toast.close()
        self._persist_now(show_error=False)
        event.accept()
