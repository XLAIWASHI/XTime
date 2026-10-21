"""Platform specific window effects."""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def apply_background_blur(
    window,
    *,
    enabled: bool,
    alpha: float = 0.18,
    radius: int = 16,
) -> bool:
    """Apply the optional light acrylic/blur effect to *window*.

    Pure-transparent mode never calls this with ``enabled=True``; failures are
    non-fatal and simply leave the faint-gray layer in place.
    """

    try:
        hwnd = int(window.winId())
    except Exception:
        return False

    try:
        if sys.platform.startswith("win"):
            from .blur_windows import apply_blur
        elif sys.platform == "darwin":
            from .blur_macos import apply_blur
        else:
            from .blur_linux import apply_blur

        return bool(
            apply_blur(
                hwnd,
                enabled=enabled,
                alpha=alpha,
                radius=radius,
                width=window.width(),
                height=window.height(),
            )
        )
    except Exception:
        log.exception("Background blur failed; continuing without it")
        return False
