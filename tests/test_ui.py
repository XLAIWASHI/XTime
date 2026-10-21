"""Offscreen UI tests for the main window, clock and dialogs."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.resources import load_bundled_fonts  # noqa: E402
from app.storage import DataLocation, DataStore  # noqa: E402
from app.timer_core import TimerCore, TimerMode, TimerState  # noqa: E402
from app.ui.button_bar import ButtonBar  # noqa: E402
from app.ui.color_picker import ColorPickerDialog  # noqa: E402
from app.ui.countdown_dialog import CountdownDialog  # noqa: E402
from app.ui.flip_clock import FlipClock  # noqa: E402
from app.ui.font_dialog import FontDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.stats_dialog import StatsDialog  # noqa: E402

from .helpers import FakeClock, FakeWallClock, make_case_dir, remove_dir


class UiTestBase(unittest.TestCase):
    app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        if QApplication.instance() is None:
            QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
            cls.app = QApplication([])
            cls.app.setStyle("Fusion")
            load_bundled_fonts()

    def setUp(self) -> None:
        self.dir = make_case_dir("ui")
        self.path = self.dir / "data.json"
        self.clock = FakeClock()
        self.wall = FakeWallClock()
        self.wall.clock = self.clock
        self.blur_patch = mock.patch(
            "app.ui.main_window.apply_background_blur", return_value=False
        )
        self.blur_patch.start()
        self.store = DataStore(DataLocation(self.path))
        self.store.load()
        self.store.settings["confirm_on_exit"] = False
        self.store.settings["window_pos"] = [20, 20]
        self.core = TimerCore(
            mode=TimerMode.COUNTDOWN,
            countdown_seconds=25 * 60,
            monotonic=self.clock,
            wallclock=self.wall,
        )
        self.window = MainWindow(self.store, self.core, DataLocation(self.path))
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        if self.window.core.is_running:
            self.window.core.pause()
        self.window._toast.close()
        self.window.close()
        self.app.processEvents()
        self.blur_patch.stop()
        remove_dir(self.dir)

    def test_initial_state(self) -> None:
        self.assertEqual(self.window.size().width(), 320)
        self.assertEqual(self.window.size().height(), 160)
        self.assertEqual(self.window.clock.current_text(), "00:25:00")
        self.assertEqual(self.core.state, TimerState.IDLE)
        self.assertEqual(self.window.buttons.start_pause.icon_name(), "play")
        self.assertFalse(
            bool(self.window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        )

    def test_scale_bounds_and_layout(self) -> None:
        self.window._set_scale(0.6)
        self.assertEqual(self.window.size().width(), 192)
        self.assertEqual(self.window.size().height(), 96)
        self.assertEqual(self.window._scale, 0.6)

        self.window._set_scale(5.0)
        self.assertEqual(self.window._scale, 2.0)
        self.assertEqual(self.window.size().width(), 640)

        self.window._set_scale(0.1)
        self.assertEqual(self.window._scale, 0.6)

    def test_background_style_and_colors(self) -> None:
        self.window._set_background_style("pure_transparent")
        self.assertEqual(self.window._bg_style, "pure_transparent")
        self.assertEqual(self.window.clock._digits[0]._shadow_strength, 1.0)

        self.window._preview_colors("#FFC46B", "#33CCFF", False)
        color = self.window.clock._digits[0].color().name().upper()
        self.assertEqual(color, "#FFC46B")
        self.assertEqual(self.window.clock._colon_color.name().upper(), "#33CCFF")

        self.window._set_background_style("faint_gray")
        self.assertEqual(self.window.clock._digits[0]._shadow_strength, 0.8)
        self.window._set_background_alpha(0.30)
        self.assertEqual(self.window._bg_alpha, 0.30)
        self.window._set_background_alpha(0.95)
        self.assertEqual(self.window._bg_alpha, 0.30)

    def test_start_pause_persists_session(self) -> None:
        self.window._toggle_running()
        self.assertEqual(self.core.state, TimerState.RUNNING)
        self.assertEqual(self.window.buttons.start_pause.icon_name(), "pause")
        self.clock.advance(2.2)
        self.window._on_tick()
        self.window._toggle_running()
        self.assertEqual(self.core.state, TimerState.PAUSED)
        self.assertEqual(self.window.buttons.start_pause.icon_name(), "play")
        self.assertEqual(len(self.store.sessions), 1)
        self.assertEqual(self.store.sessions[0]["duration_seconds"], 2)

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["settings"]["last_mode"], "countdown")

    def test_countdown_finish_records_session_and_stops(self) -> None:
        self.core.set_countdown_seconds(2)
        self.window._sync_after_command()
        self.window._toggle_running()
        self.clock.advance(2.1)
        self.window._on_tick()
        self.assertEqual(self.core.state, TimerState.IDLE)
        self.assertEqual(self.window.clock.current_text(), "00:00:00")
        self.assertEqual(self.window.buttons.start_pause.icon_name(), "play")
        self.assertGreaterEqual(len(self.store.sessions), 1)
        self.assertEqual(self.store.sessions[-1]["duration_seconds"], 2)
        self.assertFalse(self.window._tick_timer.isActive())

    def test_exit_mid_countdown_saves_elapsed_only(self) -> None:
        self.store.settings["last_countdown"] = "00:01:00"
        self.core.set_countdown_seconds(60)
        self.window._sync_after_command()
        self.window._toggle_running()
        self.clock.advance(10.2)
        self.window._on_tick()
        self.window.close()
        self.app.processEvents()

        reloaded = DataStore(DataLocation(self.path))
        reloaded.load()
        self.assertEqual(len(reloaded.sessions), 1)
        session = reloaded.sessions[0]
        self.assertEqual(session["duration_seconds"], 10)
        self.assertNotIn("remaining_seconds", session)
        # The configured duration is preserved; the remaining 50 seconds are
        # never persisted as timer state.
        self.assertEqual(reloaded.settings["last_countdown"], "00:01:00")

    def test_mode_switch_without_confirmation(self) -> None:
        self.window._set_mode(TimerMode.STOPWATCH, ask=False)
        self.assertEqual(self.core.mode, TimerMode.STOPWATCH)
        self.assertEqual(self.window.clock.current_text(), "00:00:00")
        self.assertEqual(self.window.buttons.mode.toolTip(), "切换到倒计时 (M)")

    def test_three_digit_hours(self) -> None:
        self.window.clock.set_time(100 * 3600, animate=False)
        self.assertEqual(self.window.clock.current_text(), "100:00:00")
        self.assertTrue(self.window.clock._hundreds.isVisible())
        self.window.clock.set_time(99 * 3600 + 59 * 60 + 59, animate=False)
        self.assertEqual(self.window.clock.current_text(), "99:59:59")
        self.assertFalse(self.window.clock._hundreds.isVisible())

    def test_font_is_always_bold(self) -> None:
        font = self.window.clock._digits[0]._font
        self.assertEqual(font.family(), "JetBrains Mono")
        self.assertEqual(font.weight(), QFont.Weight.Bold)

    def test_context_menu_contains_actions(self) -> None:
        menu = self.window._build_context_menu()
        texts = [action.text() for action in menu.actions()]
        self.assertIn("背景", texts)
        self.assertIn("统计…", texts)
        self.assertIn("退出", texts)
        self.assertIn("时间颜色…", texts)
        self.assertIn("字体设置…", texts)
        menu.deleteLater()

    def test_dialog_construction(self) -> None:
        colors = ColorPickerDialog(
            digit_color="#E8E8E8",
            colon_color="#888888",
            colon_follow=False,
            background_style="pure_transparent",
            font_family="JetBrains Mono",
        )
        self.assertEqual(colors.colors(), ("#E8E8E8", "#888888", False))
        colors.close()

        countdown = CountdownDialog(25 * 60)
        self.assertEqual(countdown.seconds(), 25 * 60)
        countdown.close()

        fonts = FontDialog(
            "JetBrains Mono",
            digit_color="#E8E8E8",
            colon_color="#888888",
            colon_follow=False,
        )
        self.assertEqual(fonts.selected_family(), "JetBrains Mono")
        fonts.close()

    def test_stats_dialog_refresh(self) -> None:
        stats = StatsDialog(lambda: ([], None, self.path))
        stats.refresh()
        self.assertEqual(stats._hero.text(), "00:00:00")
        self.assertEqual(stats._table.item(0, 0).text(), "今日")
        self.assertEqual(stats._table.item(4, 0).text(), "历史总计")
        stats.close()

    def test_window_grab_has_transparent_corner(self) -> None:
        self.window._set_background_style("pure_transparent")
        self.app.processEvents()
        image = self.window.grab().toImage()
        self.assertEqual(image.pixelColor(1, 1).alpha(), 0)

    def test_clock_blink_colon_alpha(self) -> None:
        clock = FlipClock()
        clock.resize(300, 100)
        clock.set_running(True)
        clock.refresh_blink()
        self.assertGreater(clock._colon1._alpha, 0.9)
        clock.set_time(61, animate=False)
        clock._blink_started -= 0.9
        clock.refresh_blink()
        self.assertLess(clock._colon1._alpha, 0.5)
        clock.set_running(False)
        self.assertEqual(clock._colon1._alpha, 1.0)
        clock.close()


if __name__ == "__main__":
    unittest.main()
