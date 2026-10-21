"""Linux background blur placeholder (compositor specific)."""

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
    log.info("Linux blur is not enabled in this build")
    return False
