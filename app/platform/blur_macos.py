"""macOS background blur (optional, no-op when pyobjc is unavailable).

The portable build targets Windows; this module keeps the platform layer
complete and degrades gracefully on macOS.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def apply_blur(
    hwnd: int,
    *,
    enabled: bool,
    alpha: float = 0.18,
    radius: int = 16,
    width: int = 0,
    height: int = 0,
) -> bool:
    log.info("macOS blur is not enabled in this build")
    return False
