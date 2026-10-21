"""Application-wide constants and defaults for XTime."""

from __future__ import annotations

APP_NAME = "XTime"
APP_DISPLAY_NAME = "XTime"
APP_VERSION = "1.0.0"

DATA_FILENAME = "data.json"
LOG_FILENAME = "xtime.log"

# Base window geometry (before user scaling).
BASE_WIDTH = 320
BASE_HEIGHT = 160
MIN_SCALE = 0.6
MAX_SCALE = 2.0
SCALE_STEP = 1.05
BASE_RADIUS = 16

# Countdown limits: 00:00:01 .. 23:59:59
MAX_COUNTDOWN_SECONDS = 23 * 3600 + 59 * 60 + 59
DEFAULT_COUNTDOWN_SECONDS = 25 * 60

# Fonts bundled with the app (relative to app/assets/fonts).
BUNDLED_FONTS = (
    "JetBrainsMono-Bold.ttf",
    "JetBrainsMono-Medium.ttf",
    "JetBrainsMono-Regular.ttf",
)

FONT_FAMILY_FALLBACKS = (
    "JetBrains Mono",
    "Fira Code",
    "Cascadia Mono",
    "Consolas",
    "SF Mono",
    "Menlo",
    "Arial",
)

COLOR_PRESETS = (
    ("白", "#F2F2F2"),
    ("暖白", "#F5E6C8"),
    ("青", "#6FD3E8"),
    ("薄荷绿", "#7FE0B0"),
    ("琥珀", "#FFC46B"),
    ("粉", "#F5A9C8"),
)

DEFAULT_FONT_COLOR = "#E8E8E8"
DEFAULT_COLON_COLOR = "#888888"
