"""Shared test helpers: project-local temp directories and fake clocks."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = ROOT / ".testwork" / "tests"


def make_case_dir(name: str) -> Path:
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_ROOT / f"{name}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = float(start)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> float:
        self.value += float(seconds)
        return self.value


class FakeWallClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.start = start or datetime(2026, 10, 19, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        self.clock: FakeClock | None = None

    def __call__(self) -> datetime:
        offset = self.clock.value if self.clock is not None else 0.0
        return self.start + timedelta(seconds=offset)
