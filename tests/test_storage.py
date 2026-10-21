"""Storage, settings normalization and aggregation tests."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app.storage import (
    DataLocation,
    DataStore,
    DEFAULT_SETTINGS,
    aggregate,
    format_duration,
    normalize_settings,
    parse_iso,
    resolve_data_path,
)

from .helpers import make_case_dir, remove_dir

TZ = timezone(timedelta(hours=8))


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = make_case_dir("storage")
        self.path = self.dir / "data.json"

    def tearDown(self) -> None:
        remove_dir(self.dir)

    def test_missing_file_creates_default_document(self) -> None:
        store = DataStore(DataLocation(self.path))
        document = store.load()
        self.assertTrue(self.path.exists())
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["sessions"], [])
        self.assertEqual(store.settings["background_style"], "faint_gray")
        self.assertEqual(store.settings["font_weight"], 700)

    def test_settings_are_normalized_and_extras_preserved(self) -> None:
        raw = {
            "version": 1,
            "sessions": [],
            "settings": {
                "font_color": "#abcdef",
                "window_scale": 9.5,
                "font_weight": 100,
                "last_countdown": "bad",
                "background_alpha": 0.9,
                "window_pos": [1, 2, 3],
                "custom_key": "keep-me",
            },
        }
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        store = DataStore(DataLocation(self.path))
        store.load()
        settings = store.settings
        self.assertEqual(settings["font_color"], "#ABCDEF")
        self.assertEqual(settings["window_scale"], 2.0)
        self.assertEqual(settings["font_weight"], 700)
        self.assertEqual(settings["last_countdown"], "00:25:00")
        self.assertEqual(settings["background_alpha"], 0.30)
        self.assertEqual(settings["window_pos"], [200, 300])
        self.assertEqual(settings["custom_key"], "keep-me")

    def test_session_roundtrip_and_upsert(self) -> None:
        store = DataStore(DataLocation(self.path))
        store.load()
        session = {
            "id": "one",
            "mode": "countdown",
            "start": "2026-10-19T10:00:00+08:00",
            "end": "2026-10-19T10:25:00+08:00",
            "duration_seconds": 1500,
        }
        self.assertTrue(store.upsert_session(session))
        self.assertTrue(
            store.upsert_session(
                {
                    **session,
                    "duration_seconds": 1499,
                    "end": "2026-10-19T10:24:59+08:00",
                }
            )
        )
        store.save()

        reloaded = DataStore(DataLocation(self.path))
        reloaded.load()
        self.assertEqual(len(reloaded.sessions), 1)
        self.assertEqual(reloaded.sessions[0]["duration_seconds"], 1499)
        self.assertEqual(reloaded.sessions[0]["start"], "2026-10-19T10:00:00+08:00")

    def test_invalid_sessions_are_dropped(self) -> None:
        raw = {
            "version": 1,
            "sessions": [
                {"id": "ok", "mode": "stopwatch", "start": "2026-10-19T10:00:00+08:00",
                 "end": "2026-10-19T10:01:00+08:00", "duration_seconds": 60},
                {"id": "bad-mode", "mode": "nope", "start": "2026-10-19T10:00:00+08:00",
                 "duration_seconds": 5},
                {"id": "bad-date", "mode": "countdown", "start": "not-a-date",
                 "duration_seconds": 5},
                "not-an-object",
            ],
            "settings": {},
        }
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        store = DataStore(DataLocation(self.path))
        store.load()
        self.assertEqual([item["id"] for item in store.sessions], ["ok"])

    def test_utf8_bom_is_accepted(self) -> None:
        raw = {
            "version": 1,
            "sessions": [],
            "settings": {"font_color": "#6FD3E8"},
        }
        self.path.write_text(json.dumps(raw), encoding="utf-8-sig")
        store = DataStore(DataLocation(self.path))
        store.load()
        self.assertEqual(store.settings["font_color"], "#6FD3E8")
        self.assertFalse(list(self.dir.glob("data.json.broken-*")))

    def test_corrupt_file_is_backed_up_and_recreated(self) -> None:
        self.path.write_text("{ this is not json", encoding="utf-8")
        store = DataStore(DataLocation(self.path))
        store.load()
        backups = list(self.dir.glob("data.json.broken-*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(self.path.exists())
        json.loads(self.path.read_text(encoding="utf-8"))

    def test_save_is_atomic_and_leaves_no_tmp_files(self) -> None:
        store = DataStore(DataLocation(self.path))
        store.load()
        store.set_setting("font_color", "#FFC46B")
        store.save()
        self.assertEqual(list(self.dir.glob("*.tmp")), [])
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["settings"]["font_color"], "#FFC46B")

    def test_parse_iso_and_naive_datetime(self) -> None:
        parsed = parse_iso("2026-10-19T10:00:00")
        self.assertIsNotNone(parsed)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertIsNone(parse_iso("garbage"))
        self.assertIsNone(parse_iso(None))

    def test_normalize_settings_keeps_known_values(self) -> None:
        settings = normalize_settings(
            {
                "last_mode": "stopwatch",
                "last_countdown": "00:05:00",
                "always_on_top": True,
                "background_style": "pure_transparent",
                "window_scale": 1.25,
                "font_family": "Consolas",
            }
        )
        self.assertEqual(settings["last_mode"], "stopwatch")
        self.assertEqual(settings["last_countdown"], "00:05:00")
        self.assertTrue(settings["always_on_top"])
        self.assertEqual(settings["background_style"], "pure_transparent")
        self.assertEqual(settings["window_scale"], 1.25)
        self.assertEqual(settings["font_family"], "Consolas")


class AggregationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 19, 12, 0, tzinfo=TZ)  # Monday

    def session(self, start: datetime, seconds: int, mode: str = "countdown") -> dict:
        return {
            "id": f"s-{start.isoformat()}-{mode}",
            "mode": mode,
            "start": start.isoformat(timespec="seconds"),
            "end": (start + timedelta(seconds=seconds)).isoformat(timespec="seconds"),
            "duration_seconds": seconds,
        }

    def test_period_buckets(self) -> None:
        sessions = [
            self.session(self.now - timedelta(hours=2), 100),
            self.session(self.now - timedelta(days=1), 200, "stopwatch"),
            self.session(self.now - timedelta(days=40), 300),
            self.session(self.now - timedelta(days=400), 400, "stopwatch"),
        ]
        rows = aggregate(sessions, now=self.now)
        self.assertEqual(rows["today"].total_seconds, 100)
        self.assertEqual(rows["week"].total_seconds, 100)
        self.assertEqual(rows["month"].total_seconds, 300)
        self.assertEqual(rows["year"].total_seconds, 600)
        self.assertEqual(rows["all"].total_seconds, 1000)
        self.assertEqual(rows["all"].countdown_sessions, 2)
        self.assertEqual(rows["all"].stopwatch_sessions, 2)

    def test_week_starts_monday(self) -> None:
        sessions = [
            self.session(datetime(2026, 10, 18, 23, 0, tzinfo=TZ), 50),  # Sunday
            self.session(datetime(2026, 10, 19, 0, 5, tzinfo=TZ), 70),  # Monday
        ]
        rows = aggregate(sessions, now=self.now)
        self.assertEqual(rows["week"].total_seconds, 70)
        self.assertEqual(rows["all"].total_seconds, 120)

    def test_bad_sessions_are_ignored(self) -> None:
        rows = aggregate(
            [
                {"mode": "countdown", "start": "nope", "duration_seconds": 10},
                {"mode": "wrong", "start": self.now.isoformat(), "duration_seconds": 10},
            ],
            now=self.now,
        )
        self.assertEqual(rows["all"].total_seconds, 0)

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "0 秒")
        self.assertEqual(format_duration(45), "45 秒")
        self.assertEqual(format_duration(65), "1 分 05 秒")
        self.assertEqual(format_duration(3725), "1 小时 02 分")


class DataPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = make_case_dir("datapath")

    def tearDown(self) -> None:
        remove_dir(self.dir)

    def test_preferred_path_when_writable(self) -> None:
        app_dir = self.dir / "app"
        app_dir.mkdir()
        location = resolve_data_path(app_dir=app_dir, probe=lambda path: True)
        self.assertFalse(location.is_fallback)
        self.assertEqual(location.path, app_dir / "data.json")

    def test_fallback_path_when_app_dir_is_read_only(self) -> None:
        app_dir = self.dir / "ProgramFiles" / "XTime"
        app_dir.mkdir(parents=True)
        user_root = self.dir / "userdata"
        with mock.patch("app.storage.user_data_dir", return_value=user_root):
            location = resolve_data_path(app_dir=app_dir, probe=lambda path: False)
        self.assertTrue(location.is_fallback)
        self.assertEqual(location.path, user_root / "XTime" / "data.json")
        self.assertTrue(location.path.parent.exists())


if __name__ == "__main__":
    unittest.main()
