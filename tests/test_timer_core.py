"""Timer state machine tests (no Qt required)."""

from __future__ import annotations

import unittest

from app.timer_core import (
    MAX_COUNTDOWN_SECONDS,
    TimerCore,
    TimerMode,
    TimerState,
    clamp_countdown,
    format_hms,
    parse_hms,
)

from .helpers import FakeClock, FakeWallClock


class TimerCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.wall = FakeWallClock()
        self.wall.clock = self.clock
        self.ids = iter(f"id-{index}" for index in range(100))
        self.core = TimerCore(
            mode=TimerMode.COUNTDOWN,
            countdown_seconds=60,
            monotonic=self.clock,
            wallclock=self.wall,
            id_factory=lambda: next(self.ids),
        )

    def test_initial_snapshot(self) -> None:
        snapshot = self.core.snapshot()
        self.assertEqual(snapshot.mode, TimerMode.COUNTDOWN)
        self.assertEqual(snapshot.state, TimerState.IDLE)
        self.assertEqual(snapshot.display_seconds, 60)
        self.assertEqual(snapshot.initial_seconds, 60)
        self.assertEqual(snapshot.progress, 0.0)
        self.assertFalse(snapshot.just_finished)

    def test_countdown_ticks_and_finishes(self) -> None:
        self.assertTrue(self.core.start())
        self.clock.advance(0.2)
        self.assertEqual(self.core.tick().display_seconds, 60)
        self.clock.advance(1.0)
        snapshot = self.core.tick()
        self.assertEqual(snapshot.display_seconds, 59)
        self.assertEqual(snapshot.state, TimerState.RUNNING)

        self.clock.advance(59.0)
        snapshot = self.core.tick()
        self.assertEqual(snapshot.display_seconds, 0)
        self.assertTrue(snapshot.just_finished)
        self.assertEqual(snapshot.state, TimerState.IDLE)

        sessions = self.core.drain_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["mode"], "countdown")
        self.assertEqual(sessions[0]["duration_seconds"], 60)
        self.assertEqual(self.core.drain_sessions(), [])

    def test_pause_resume_creates_segments(self) -> None:
        self.core.start()
        self.clock.advance(10.2)
        self.assertTrue(self.core.pause())
        self.assertEqual(self.core.snapshot().display_seconds, 50)
        self.clock.advance(30)
        self.assertEqual(self.core.snapshot().display_seconds, 50)

        self.core.start()
        self.clock.advance(4.9)
        self.core.pause()
        sessions = self.core.drain_sessions()
        self.assertEqual([item["duration_seconds"] for item in sessions], [10, 4])
        self.assertEqual(self.core.snapshot().display_seconds, 45)

    def test_reset_clears_timer_and_closes_session(self) -> None:
        self.core.start()
        self.clock.advance(8.5)
        self.core.reset()
        snapshot = self.core.snapshot()
        self.assertEqual(snapshot.state, TimerState.IDLE)
        self.assertEqual(snapshot.display_seconds, 60)
        sessions = self.core.drain_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["duration_seconds"], 8)

    def test_sub_second_pause_does_not_create_dirty_session(self) -> None:
        self.core.start()
        self.clock.advance(0.4)
        self.core.pause()
        self.assertEqual(self.core.drain_sessions(), [])

    def test_restart_after_finish_resets_to_initial(self) -> None:
        self.core.start()
        self.clock.advance(60.1)
        self.core.tick()
        self.assertEqual(self.core.snapshot().display_seconds, 0)
        self.core.drain_sessions()
        self.core.start()
        self.assertEqual(self.core.snapshot().display_seconds, 60)
        self.assertEqual(self.core.snapshot().state, TimerState.RUNNING)

    def test_stopwatch_counts_up_without_limit(self) -> None:
        self.core.set_mode(TimerMode.STOPWATCH)
        self.core.start()
        self.clock.advance(2.9)
        self.assertEqual(self.core.tick().display_seconds, 2)
        self.clock.advance(3600)
        self.assertEqual(self.core.tick().display_seconds, 3602)
        self.assertEqual(self.core.snapshot().state, TimerState.RUNNING)
        self.assertEqual(format_hms(90061), "25:01:01")

    def test_mode_switch_finalizes_running_session(self) -> None:
        self.core.start()
        self.clock.advance(3.3)
        self.assertTrue(self.core.set_mode(TimerMode.STOPWATCH))
        self.assertEqual(self.core.mode, TimerMode.STOPWATCH)
        self.assertEqual(self.core.state, TimerState.IDLE)
        sessions = self.core.drain_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["duration_seconds"], 3)
        self.assertEqual(self.core.snapshot().display_seconds, 0)

    def test_live_session_snapshot(self) -> None:
        self.core.start()
        self.clock.advance(1.2)
        live = self.core.live_session()
        self.assertIsNotNone(live)
        self.assertEqual(live["duration_seconds"], 1)
        self.assertEqual(live["id"], "id-0")
        self.core.pause()
        self.assertEqual(self.core.live_session(), None)
        sessions = self.core.drain_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], live["id"])

    def test_set_countdown_seconds(self) -> None:
        self.core.start()
        self.clock.advance(5.5)
        self.core.set_countdown_seconds(30)
        self.assertEqual(self.core.initial_seconds, 30)
        self.assertEqual(self.core.state, TimerState.IDLE)
        self.assertEqual(self.core.snapshot().display_seconds, 30)
        self.assertEqual(self.core.drain_sessions()[0]["duration_seconds"], 5)

    def test_clamping_and_parsing(self) -> None:
        self.assertEqual(clamp_countdown(0), 1)
        self.assertEqual(clamp_countdown(10**9), MAX_COUNTDOWN_SECONDS)
        self.assertEqual(parse_hms("01:02:03"), 3723)
        self.assertEqual(parse_hms("bad", default=70), 70)
        self.assertEqual(parse_hms("99:99:99"), MAX_COUNTDOWN_SECONDS)
        self.assertEqual(format_hms(0), "00:00:00")
        self.assertEqual(format_hms(3600), "01:00:00")

    def test_progress_counts_down(self) -> None:
        self.core.start()
        self.clock.advance(15)
        self.assertAlmostEqual(self.core.snapshot().progress, 0.25, places=3)


if __name__ == "__main__":
    unittest.main()
