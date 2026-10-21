"""Windows acrylic blur for the optional faint-gray glass effect."""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_ACCENT_DISABLED = 0
_ACCENT_BLURBEHIND = 3
_ACCENT_ACRYLICBLURBEHIND = 4

_WCA_ACCENT_POLICY = 19


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WindowCompositionAttributeData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

_SetWindowCompositionAttribute = _user32.SetWindowCompositionAttribute
_SetWindowCompositionAttribute.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(_WindowCompositionAttributeData),
]
_SetWindowCompositionAttribute.restype = wintypes.BOOL


def _abgr(color: str, alpha: float) -> int:
    color = color.lstrip("#")
    if len(color) != 6:
        color = "1E1E1E"
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    alpha_byte = max(1, min(255, int(round(alpha * 255))))
    return (alpha_byte << 24) | (blue << 16) | (green << 8) | red


def _set_accent(hwnd: int, state: int, gradient_color: int = 0, flags: int = 2) -> bool:
    policy = _AccentPolicy(
        AccentState=state,
        AccentFlags=flags,
        GradientColor=gradient_color,
        AnimationId=0,
    )
    data = _WindowCompositionAttributeData(
        Attribute=_WCA_ACCENT_POLICY,
        Data=ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
        SizeOfData=ctypes.sizeof(policy),
    )
    try:
        return bool(_SetWindowCompositionAttribute(hwnd, ctypes.byref(data)))
    except Exception:
        log.exception("SetWindowCompositionAttribute failed")
        return False


def set_rounded_region(hwnd: int, width: int, height: int, radius: int) -> None:
    """Clip a blurred window so its acrylic layer follows the rounded card."""

    try:
        if width <= 1 or height <= 1:
            return
        diameter = max(2, int(radius) * 2)
        region = _gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, diameter, diameter)
        if region:
            if not _user32.SetWindowRgn(hwnd, region, True):
                _gdi32.DeleteObject(region)
    except Exception:
        log.exception("Could not set rounded window region")


def clear_region(hwnd: int) -> None:
    try:
        _user32.SetWindowRgn(hwnd, None, True)
    except Exception:
        pass


def apply_blur(
    hwnd: int,
    *,
    enabled: bool,
    alpha: float = 0.18,
    radius: int = 16,
    width: int = 0,
    height: int = 0,
) -> bool:
    """Enable or disable acrylic blur behind the window."""

    if not hwnd:
        return False

    if not enabled:
        _set_accent(hwnd, _ACCENT_DISABLED)
        clear_region(hwnd)
        return True

    color = _abgr("1E1E1E", max(0.12, min(0.30, alpha)))
    # Try the newer acrylic state first, then fall back to plain blur.
    if _set_accent(hwnd, _ACCENT_ACRYLICBLURBEHIND, color):
        set_rounded_region(hwnd, width, height, radius)
        return True
    if _set_accent(hwnd, _ACCENT_BLURBEHIND, color):
        set_rounded_region(hwnd, width, height, radius)
        return True

    clear_region(hwnd)
    log.warning("Acrylic blur is not available on this Windows build")
    return False
