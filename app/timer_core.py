"""Timer state machine for XTime.

The module is intentionally free of Qt so that the timer and session logic can
be unit-tested with a fake monotonic clock.  The UI polls :meth:`TimerCore.tick`
and :meth:`TimerCore.snapshot`; completed sessions are drained and persisted by
the window.

State machine::

    IDLE --start--> RUNNING --pause--> PAUSED
                       |                 |
                       |--reset----------+--> IDLE
                       |
                       +--(countdown reaches zero)--> IDLE + finished flag
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable

from .constants import DEFAULT_COUNTDOWN_SECONDS, MAX_COUNTDOWN_SECONDS


class TimerMode(str, Enum):
    """The two supported timer modes."""

    COUNTDOWN = "countdown"
    STOPWATCH = "stopwatch"

    @property
    def label(self) -> str:
        return "倒计时" if self is TimerMode.COUNTDOWN else "正计时"

    @classmethod
    def from_value(cls, value: object) -> "TimerMode":
        if isinstance(value, TimerMode):
            return value
        return cls.STOPWATCH if str(value).lower() == "stopwatch" else cls.COUNTDOWN


class TimerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass(frozen=True)
class TimerSnapshot:
    """Immutable view of the timer at one instant."""

    mode: TimerMode
    state: TimerState
    display_seconds: int
    remaining_seconds: int
    elapsed_seconds: int
    initial_seconds: int
    progress: float
    just_finished: bool = False


def format_hms(seconds: int) -> str:
    """Format a non-negative number of seconds as HH:MM:SS.

    Hours are allowed to grow past 99 for the stopwatch, as required by F2.
    """

    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_hms(text: str, default: int = DEFAULT_COUNTDOWN_SECONDS) -> int:
    """Parse ``HH:MM:SS`` to seconds, returning *default* when invalid."""

    try:
        parts = str(text).strip().split(":")
        if len(parts) != 3:
            return default
        hours, minutes, seconds = (int(part) for part in parts)
        total = hours * 3600 + minutes * 60 + seconds
        if hours < 0 or minutes < 0 or seconds < 0:
            return default
        return max(1, min(MAX_COUNTDOWN_SECONDS, total))
    except (TypeError, ValueError):
        return default


def clamp_countdown(seconds: int | float) -> int:
    """Clamp a countdown length to the supported 1 s .. 23:59:59 range."""

    return max(1, min(MAX_COUNTDOWN_SECONDS, int(seconds)))


class TimerCore:
    """A monotonic-clock based countdown / stopwatch."""

    def __init__(
        self,
        mode: TimerMode | str = TimerMode.COUNTDOWN,
        countdown_seconds: int = DEFAULT_COUNTDOWN_SECONDS,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wallclock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._monotonic = monotonic
        self._wallclock: Callable[[], datetime] = wallclock or (
            lambda: datetime.now().astimezone()
        )
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)

        self._mode = TimerMode.from_value(mode)
        self._initial_ms = float(clamp_countdown(countdown_seconds) * 1000)
        self._accumulated_ms = 0.0
        self._state = TimerState.IDLE

        self._segment_started_at = 0.0
        self._segment_base_ms = 0.0
        self._session_id: str | None = None
        self._session_started_wall: datetime | None = None

        self._completed_sessions: list[dict] = []

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------
    @property
    def mode(self) -> TimerMode:
        return self._mode

    @property
    def state(self) -> TimerState:
        return self._state

    @property
    def initial_seconds(self) -> int:
        return int(round(self._initial_ms / 1000))

    @property
    def is_running(self) -> bool:
        return self._state is TimerState.RUNNING

    @property
    def is_idle(self) -> bool:
        return self._state is TimerState.IDLE

    @property
    def has_progress(self) -> bool:
        """True while there is time on the clock worth preserving."""

        return self._current_total_ms() > 0.5

    # ------------------------------------------------------------------
    # Clock helpers
    # ------------------------------------------------------------------
    def _now(self) -> float:
        return float(self._monotonic())

    def _current_total_ms(self, now: float | None = None) -> float:
        if self._state is not TimerState.RUNNING:
            return self._accumulated_ms
        now = self._now() if now is None else now
        delta_ms = max(0.0, now - self._segment_started_at) * 1000.0
        total = self._accumulated_ms + delta_ms
        if self._mode is TimerMode.COUNTDOWN:
            total = min(total, self._initial_ms)
        return total

    def _absorb(self, now: float | None = None) -> float:
        """Fold the current running segment into the accumulated total."""

        total = self._current_total_ms(now)
        self._accumulated_ms = total
        self._segment_started_at = self._now() if now is None else now
        return total

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def start(self) -> bool:
        """Start or resume the timer.  Returns True when state changed."""

        if self._state is TimerState.RUNNING:
            return False

        # Restarting a finished countdown begins from the configured length.
        if self._mode is TimerMode.COUNTDOWN and self._remaining_ms() <= 0.5:
            self._accumulated_ms = 0.0

        now = self._now()
        self._segment_started_at = now
        self._segment_base_ms = self._accumulated_ms
        self._session_id = str(self._id_factory())
        self._session_started_wall = self._wallclock()
        self._state = TimerState.RUNNING
        return True

    def pause(self) -> bool:
        """Pause a running timer and close its session record."""

        if self._state is not TimerState.RUNNING:
            return False

        now = self._now()
        self._absorb(now)
        self._finalize_session(now)
        self._state = TimerState.PAUSED
        return True

    def stop(self) -> bool:
        """Stop the timer, keeping the current value (alias for pause)."""

        return self.pause()

    def reset(self) -> bool:
        """Stop and return the timer to its initial value."""

        if self._state is TimerState.RUNNING:
            now = self._now()
            self._absorb(now)
            self._finalize_session(now)
        elif self._state is TimerState.PAUSED:
            self._finalize_session(self._now())

        self._accumulated_ms = 0.0
        self._state = TimerState.IDLE
        self._clear_session()
        return True

    def tick(self) -> TimerSnapshot:
        """Advance the clock and return a snapshot.

        A countdown that reaches zero transitions to IDLE exactly once and the
        resulting snapshot carries ``just_finished=True``.
        """

        just_finished = False
        if self._state is TimerState.RUNNING and self._mode is TimerMode.COUNTDOWN:
            now = self._now()
            total = self._current_total_ms(now)
            if total >= self._initial_ms - 0.5:
                self._accumulated_ms = self._initial_ms
                self._finalize_session(now)
                self._state = TimerState.IDLE
                just_finished = True

        return self.snapshot(just_finished=just_finished)

    def snapshot(self, *, just_finished: bool = False) -> TimerSnapshot:
        total_ms = self._current_total_ms()

        if self._mode is TimerMode.COUNTDOWN:
            remaining_ms = max(0.0, self._initial_ms - total_ms)
            # The display should read 25:00 for the whole first second and
            # switch to 24:59 only once a full second has elapsed.
            display = int(math.ceil(remaining_ms / 1000.0 - 1e-9))
            remaining = max(0, display)
            elapsed = int(min(total_ms, self._initial_ms) // 1000)
            progress = (
                min(1.0, total_ms / self._initial_ms) if self._initial_ms else 0.0
            )
        else:
            display = int(total_ms // 1000)
            remaining = 0
            elapsed = display
            progress = 0.0

        return TimerSnapshot(
            mode=self._mode,
            state=self._state,
            display_seconds=max(0, display),
            remaining_seconds=remaining,
            elapsed_seconds=elapsed,
            initial_seconds=self.initial_seconds,
            progress=progress,
            just_finished=just_finished,
        )

    def set_mode(self, mode: TimerMode | str) -> bool:
        """Switch modes, discarding the current run.

        The caller is responsible for asking the user before switching while a
        session is active.  Any running session is closed cleanly here.
        """

        mode = TimerMode.from_value(mode)
        if mode is self._mode:
            return False

        if self._state is TimerState.RUNNING:
            now = self._now()
            self._absorb(now)
            self._finalize_session(now)

        self._mode = mode
        self._accumulated_ms = 0.0
        self._state = TimerState.IDLE
        self._clear_session()
        return True

    def set_countdown_seconds(self, seconds: int, *, reset: bool = True) -> None:
        """Change the configured countdown duration."""

        new_initial = float(clamp_countdown(seconds) * 1000)
        if self._state is TimerState.RUNNING:
            now = self._now()
            self._absorb(now)
            self._finalize_session(now)
            self._state = TimerState.IDLE

        self._initial_ms = new_initial
        if reset:
            self._accumulated_ms = 0.0
            self._state = TimerState.IDLE
            self._clear_session()

    # ------------------------------------------------------------------
    # Session records
    # ------------------------------------------------------------------
    def live_session(self) -> dict | None:
        """A session snapshot for the currently running segment.

        Used for the 30-second periodic flush described in the plan.  Returns
        None when there is no running session or it is younger than one second.
        """

        if self._state is not TimerState.RUNNING or self._session_id is None:
            return None

        now = self._now()
        total = self._current_total_ms(now)
        duration = int(max(0.0, total - self._segment_base_ms) // 1000)
        if duration < 1:
            return None

        start = self._session_started_wall or self._wallclock()
        return self._session_dict(start, self._wallclock(), duration)

    def drain_sessions(self) -> list[dict]:
        """Return finished session records and clear the internal queue."""

        sessions = self._completed_sessions
        self._completed_sessions = []
        return sessions

    def _session_dict(
        self, start: datetime, end: datetime, duration_seconds: int
    ) -> dict:
        return {
            "id": self._session_id,
            "mode": self._mode.value,
            "start": start.isoformat(timespec="seconds"),
            "end": end.isoformat(timespec="seconds"),
            "duration_seconds": int(duration_seconds),
        }

    def _finalize_session(self, now: float) -> None:
        if self._session_id is None or self._session_started_wall is None:
            return

        total = self._accumulated_ms
        if self._state is TimerState.RUNNING:
            total = self._current_total_ms(now)
            self._accumulated_ms = total

        duration_ms = max(0.0, total - self._segment_base_ms)
        duration = int(duration_ms // 1000)
        if self._mode is TimerMode.COUNTDOWN:
            duration = min(duration, self.initial_seconds)

        # Sub-second sessions are noise; do not create dirty records.
        if duration >= 1:
            self._completed_sessions.append(
                self._session_dict(
                    self._session_started_wall,
                    self._wallclock(),
                    duration,
                )
            )
        self._clear_session()

    def _clear_session(self) -> None:
        self._session_id = None
        self._session_started_wall = None
        self._segment_base_ms = self._accumulated_ms

    # ------------------------------------------------------------------
    # Small helpers used by the UI
    # ------------------------------------------------------------------
    def _remaining_ms(self) -> float:
        if self._mode is not TimerMode.COUNTDOWN:
            return math.inf
        return max(0.0, self._initial_ms - self._current_total_ms())

    def remaining_seconds(self) -> int:
        return self.snapshot().remaining_seconds

    def display_seconds(self) -> int:
        return self.snapshot().display_seconds
