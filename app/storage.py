"""Portable JSON storage, data-path resolution and duration aggregation.

The data file lives next to the executable for the green/portable build.  If
that directory is not writable (for example when the app is unpacked into
``C:\\Program Files``), the store transparently falls back to the per-user
application-data directory and the window tells the user once.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from .constants import (
    APP_NAME,
    DATA_FILENAME,
    DEFAULT_COLON_COLOR,
    DEFAULT_COUNTDOWN_SECONDS,
    DEFAULT_FONT_COLOR,
    MAX_COUNTDOWN_SECONDS,
    MAX_SCALE,
    MIN_SCALE,
)
from .timer_core import TimerMode, format_hms

log = logging.getLogger(__name__)

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_DATA_VERSION = 1

DEFAULT_SETTINGS: dict = {
    "last_mode": TimerMode.COUNTDOWN.value,
    "last_countdown": format_hms(DEFAULT_COUNTDOWN_SECONDS),
    "always_on_top": False,
    "window_pos": [200, 300],
    "window_scale": 1.0,
    "background_style": "faint_gray",
    "background_alpha": 0.18,
    "font_family": "JetBrains Mono",
    "font_weight": 700,
    "font_color": DEFAULT_FONT_COLOR,
    "colon_color": DEFAULT_COLON_COLOR,
    "colon_follow_digit": False,
    "blur_enabled": False,
    "sound_enabled": True,
    "confirm_on_exit": True,
    "fallback_notice_shown": False,
}

BACKGROUND_STYLES = ("faint_gray", "pure_transparent")


# ---------------------------------------------------------------------------
# Data location
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DataLocation:
    path: Path
    is_fallback: bool = False
    reason: str = ""

    @property
    def directory(self) -> Path:
        return self.path.parent


def application_dir() -> Path:
    """Directory that contains the executable, or the project root in dev."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Platform specific per-user application-data root."""

    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata)
        return Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


def _probe_directory(directory: Path) -> bool:
    """Verify that a directory accepts new files (and data.json is writable)."""

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    probe = directory / f".xtime-probe-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        probe.unlink()
    except OSError:
        try:
            probe.unlink()
        except OSError:
            pass
        return False

    data_file = directory / DATA_FILENAME
    if data_file.exists():
        try:
            with open(data_file, "a", encoding="utf-8"):
                pass
        except OSError:
            return False
    return True


def resolve_data_path(
    app_dir: Path | None = None,
    *,
    probe: Callable[[Path], bool] | None = None,
) -> DataLocation:
    """Choose the portable data path, falling back to the user directory.

    *probe* is injectable for tests; by default it performs a real write test.
    """

    directory = Path(app_dir) if app_dir is not None else application_dir()
    checker = probe or _probe_directory

    try:
        if checker(directory):
            return DataLocation(directory / DATA_FILENAME, False, "")
    except Exception:  # pragma: no cover - defensive, checker normally catches
        log.exception("Unexpected error while probing %s", directory)

    fallback_dir = user_data_dir() / APP_NAME
    reason = f"{directory} 不可写"
    try:
        if checker(fallback_dir) or not (fallback_dir / DATA_FILENAME).exists():
            fallback_dir.mkdir(parents=True, exist_ok=True)
            return DataLocation(fallback_dir / DATA_FILENAME, True, reason)
    except OSError:
        log.exception("User data directory is not writable either: %s", fallback_dir)

    # Last resort: keep the expected path; saving will report a helpful error.
    return DataLocation(fallback_dir / DATA_FILENAME, True, reason)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def normalize_color(value: object, default: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if _HEX_COLOR.match(text):
            return text.upper()
    return default


def normalize_settings(raw: object) -> dict:
    """Merge user data over the defaults and repair invalid fields."""

    settings = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        settings.update(raw)  # merge user values, keep hand-added keys

    mode = str(settings.get("last_mode", "")).lower()
    settings["last_mode"] = (
        TimerMode.STOPWATCH.value
        if mode == TimerMode.STOPWATCH.value
        else TimerMode.COUNTDOWN.value
    )

    countdown_text = settings.get("last_countdown")
    try:
        parts = str(countdown_text).split(":")
        seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) != 3 or seconds < 1:
            raise ValueError
        seconds = min(seconds, MAX_COUNTDOWN_SECONDS)
        settings["last_countdown"] = format_hms(seconds)
    except (TypeError, ValueError, IndexError):
        settings["last_countdown"] = format_hms(DEFAULT_COUNTDOWN_SECONDS)

    settings["always_on_top"] = bool(settings.get("always_on_top", False))

    position = settings.get("window_pos")
    if (
        isinstance(position, (list, tuple))
        and len(position) == 2
        and all(isinstance(item, (int, float)) for item in position)
    ):
        settings["window_pos"] = [
            max(-100000, min(100000, int(position[0]))),
            max(-100000, min(100000, int(position[1]))),
        ]
    else:
        settings["window_pos"] = list(DEFAULT_SETTINGS["window_pos"])

    try:
        scale = float(settings.get("window_scale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    settings["window_scale"] = round(max(MIN_SCALE, min(MAX_SCALE, scale)), 4)

    style = settings.get("background_style")
    settings["background_style"] = (
        style if style in BACKGROUND_STYLES else "faint_gray"
    )

    try:
        alpha = float(settings.get("background_alpha", 0.18))
    except (TypeError, ValueError):
        alpha = 0.18
    settings["background_alpha"] = round(max(0.10, min(0.30, alpha)), 3)

    family = settings.get("font_family")
    if not isinstance(family, str) or not family.strip():
        family = DEFAULT_SETTINGS["font_family"]
    settings["font_family"] = family.strip()[:120]

    # F28: the main timer is always bold; never trust a hand-edited value.
    settings["font_weight"] = 700
    settings["font_color"] = normalize_color(
        settings.get("font_color"), DEFAULT_FONT_COLOR
    )
    settings["colon_color"] = normalize_color(
        settings.get("colon_color"), DEFAULT_COLON_COLOR
    )

    for key in (
        "colon_follow_digit",
        "blur_enabled",
        "sound_enabled",
        "confirm_on_exit",
        "fallback_notice_shown",
    ):
        settings[key] = bool(settings.get(key, DEFAULT_SETTINGS[key]))

    return settings


def normalize_session(raw: object) -> dict | None:
    """Validate one raw session record; return a clean dict or None."""

    if not isinstance(raw, dict):
        return None

    mode = str(raw.get("mode", "")).lower()
    if mode not in (TimerMode.COUNTDOWN.value, TimerMode.STOPWATCH.value):
        return None

    start = parse_iso(raw.get("start"))
    if start is None:
        return None
    end = parse_iso(raw.get("end")) or start
    if end.tzinfo is None:
        end = end.replace(tzinfo=start.tzinfo)
    if end < start:
        end = start

    try:
        duration = int(raw.get("duration_seconds", 0))
    except (TypeError, ValueError):
        return None
    if duration < 0:
        return None

    session_id = raw.get("id")
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = uuid.uuid4().hex

    return {
        "id": session_id.strip(),
        "mode": mode,
        "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
        "duration_seconds": duration,
    }


def default_document() -> dict:
    return {
        "version": _DATA_VERSION,
        "sessions": [],
        "settings": dict(DEFAULT_SETTINGS),
    }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
@dataclass
class StatsRow:
    countdown_seconds: int = 0
    stopwatch_seconds: int = 0
    countdown_sessions: int = 0
    stopwatch_sessions: int = 0

    @property
    def total_seconds(self) -> int:
        return self.countdown_seconds + self.stopwatch_seconds

    @property
    def total_sessions(self) -> int:
        return self.countdown_sessions + self.stopwatch_sessions


PERIOD_KEYS = ("today", "week", "month", "year", "all")
PERIOD_LABELS = {
    "today": "今日",
    "week": "本周",
    "month": "本月",
    "year": "今年",
    "all": "历史总计",
}


class DataStore:
    """Read/write the single portable JSON document."""

    def __init__(self, location: DataLocation | str | Path) -> None:
        if isinstance(location, DataLocation):
            self.location = location
        else:
            self.location = DataLocation(Path(location))
        self.path = self.location.path
        self.document = default_document()
        self.last_error: str = ""
        self._loaded = False

    # -- loading ---------------------------------------------------------
    def load(self) -> dict:
        path = self.path
        if not path.exists():
            self.document = default_document()
            self._loaded = True
            try:
                self.save()
            except OSError:
                log.exception("Could not create initial data file")
            return self.document

        try:
            text = path.read_text(encoding="utf-8-sig")
            raw = json.loads(text)
            if not isinstance(raw, dict):
                raise ValueError("data root is not an object")
        except (OSError, ValueError) as exc:
            log.warning("Cannot read %s: %s", path, exc)
            self._backup_broken_file()
            self.document = default_document()
            self._loaded = True
            try:
                self.save()
            except OSError:
                log.exception("Could not recreate data file after corruption")
            return self.document

        self.document = self._normalize_document(raw)
        self._loaded = True
        return self.document

    def _normalize_document(self, raw: dict) -> dict:
        sessions_raw = raw.get("sessions")
        sessions: list[dict] = []
        if isinstance(sessions_raw, list):
            seen: dict[str, dict] = {}
            for item in sessions_raw:
                normalized = normalize_session(item)
                if normalized is not None:
                    seen[normalized["id"]] = normalized
            sessions = list(seen.values())

        settings = normalize_settings(raw.get("settings"))
        return {
            "version": _DATA_VERSION,
            "sessions": sessions,
            "settings": settings,
        }

    def _backup_broken_file(self) -> None:
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_name(f"{self.path.name}.broken-{stamp}")
            shutil.copy2(self.path, backup)
            log.warning("Saved broken data file as %s", backup)
            try:
                self.path.unlink()
            except OSError:
                pass
        except OSError:
            log.exception("Could not back up broken data file")

    # -- convenience accessors ------------------------------------------
    @property
    def sessions(self) -> list[dict]:
        return self.document.setdefault("sessions", [])

    @property
    def settings(self) -> dict:
        return self.document.setdefault("settings", dict(DEFAULT_SETTINGS))

    def get_setting(self, key: str, default: object = None) -> object:
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: object) -> None:
        self.settings[key] = value

    def update_settings(self, values: dict) -> None:
        self.settings.update(values)

    def upsert_session(self, session: object) -> bool:
        normalized = normalize_session(session)
        if normalized is None:
            return False
        for index, existing in enumerate(self.sessions):
            if existing.get("id") == normalized["id"]:
                self.sessions[index] = normalized
                return True
        self.sessions.append(normalized)
        return True

    def replace_sessions(self, sessions: Iterable[object]) -> None:
        normalized = [item for item in map(normalize_session, sessions) if item]
        self.document["sessions"] = normalized

    # -- saving ----------------------------------------------------------
    def save(self) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(self.document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            self.last_error = ""
        except OSError as exc:
            self.last_error = str(exc)
            try:
                tmp.unlink()
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _local_midnight(day: date) -> datetime:
    return datetime.combine(day, dtime.min).astimezone()


def period_starts(now: datetime | None = None) -> dict[str, datetime]:
    now = (now or datetime.now().astimezone()).astimezone()
    today = _local_midnight(now.date())
    week = today - timedelta(days=now.weekday())
    month = today.replace(day=1)
    year = today.replace(month=1, day=1)
    return {
        "today": today,
        "week": week,
        "month": month,
        "year": year,
        "all": datetime.min.replace(tzinfo=timezone.utc),
    }


def aggregate(
    sessions: Iterable[dict], now: datetime | None = None
) -> dict[str, StatsRow]:
    """Sum sessions into today/week/month/year/all buckets.

    Sessions are attributed to the period in which they *started*, which keeps
    a session that crosses midnight in one bucket.
    """

    now = (now or datetime.now().astimezone()).astimezone()
    starts = period_starts(now)
    rows = {key: StatsRow() for key in PERIOD_KEYS}

    for raw in sessions:
        session = normalize_session(raw)
        if session is None:
            continue
        start = parse_iso(session["start"])
        if start is None:
            continue
        start = start.astimezone()
        duration = int(session["duration_seconds"])
        mode = session["mode"]

        for key in PERIOD_KEYS:
            if start >= starts[key]:
                row = rows[key]
                if mode == TimerMode.COUNTDOWN.value:
                    row.countdown_seconds += duration
                    row.countdown_sessions += 1
                else:
                    row.stopwatch_seconds += duration
                    row.stopwatch_sessions += 1

    return rows


def format_duration(seconds: int, *, always_seconds: bool = False) -> str:
    """Human friendly duration for the statistics view."""

    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} 小时 {minutes:02d} 分"
    if minutes:
        return f"{minutes} 分 {secs:02d} 秒"
    if always_seconds or secs:
        return f"{secs} 秒"
    return "0 秒"


def merge_live_session(sessions: Iterable[dict], live: dict | None) -> list[dict]:
    """Return sessions with a live session replacing its flushed counterpart."""

    result = list(sessions)
    if not live:
        return result
    for index, item in enumerate(result):
        if item.get("id") == live.get("id"):
            result[index] = live
            return result
    result.append(live)
    return result
