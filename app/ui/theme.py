"""Shared dark styling for dialogs, menus and small controls."""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QMenu, QWidget

from ..resources import asset_path

ACCENT = "#6FD3E8"
ACCENT_DARK = "#10171A"
TEXT = "#EDEEF0"
MUTED = "#9CA0A6"
PANEL = "#1B1C1F"
CARD = "#24262A"
BORDER = "rgba(255, 255, 255, 0.10)"

UI_FONT_FAMILIES = ("Microsoft YaHei UI", "Segoe UI", "Arial")

_CHECK_ICON = asset_path("icons", "check.svg").as_posix()

DIALOG_QSS = f"""
QDialog, QMessageBox {{
    background-color: {PANEL};
    color: {TEXT};
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel[muted="true"] {{
    color: {MUTED};
}}
QLabel[heading="true"] {{
    color: {TEXT};
    font-size: 18px;
    font-weight: 700;
}}
QLabel[section="true"] {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QPushButton {{
    background-color: #2A2D33;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 16px;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: #343840;
}}
QPushButton:pressed {{
    background-color: #202227;
}}
QPushButton:disabled {{
    color: #62666D;
    background-color: #232529;
}}
QPushButton[primary="true"] {{
    background-color: {ACCENT};
    color: {ACCENT_DARK};
    border: 1px solid {ACCENT};
    font-weight: 700;
}}
QPushButton[primary="true"]:hover {{
    background-color: #8BE0F0;
}}
QPushButton[flat="true"] {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 4px 6px;
}}
QPushButton[flat="true"]:hover {{
    color: {TEXT};
}}
QPushButton[chip="true"] {{
    background-color: {CARD};
    color: #C9CBD0;
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 9px;
    min-height: 16px;
}}
QPushButton[chip="true"]:hover {{
    background-color: #31353C;
    color: {TEXT};
    border-color: rgba(255, 255, 255, 0.18);
}}
QLineEdit, QSpinBox, QComboBox {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 20px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_DARK};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: #31353C;
    selection-color: {TEXT};
    outline: 0;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 18px;
    background: transparent;
    border: none;
}}
QSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {MUTED};
    width: 0; height: 0;
}}
QSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {MUTED};
    width: 0; height: 0;
}}
QCheckBox {{
    color: {TEXT};
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #4A4E55;
    background: {CARD};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    image: url("{_CHECK_ICON}");
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #34373D;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #F2F2F2;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
QTableWidget {{
    background-color: {PANEL};
    color: {TEXT};
    border: none;
    gridline-color: transparent;
    selection-background-color: transparent;
    selection-color: {TEXT};
    outline: 0;
}}
QHeaderView::section {{
    background-color: transparent;
    color: {MUTED};
    border: none;
    padding: 6px 4px;
    font-size: 12px;
    font-weight: 600;
}}
QTableWidget::item {{
    border-bottom: 1px solid rgba(255, 255, 255, 0.055);
    padding: 4px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #41454C;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QToolTip {{
    background-color: #26282C;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
}}
"""

MENU_QSS = f"""
QMenu {{
    background-color: #202226;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 7px;
}}
QMenu::item {{
    background: transparent;
    padding: 7px 26px 7px 24px;
    border-radius: 6px;
    margin: 1px 3px;
}}
QMenu::item:selected {{
    background-color: rgba(255, 255, 255, 0.09);
}}
QMenu::item:disabled {{
    color: #62666D;
}}
QMenu::separator {{
    height: 1px;
    background: rgba(255, 255, 255, 0.08);
    margin: 6px 12px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
    margin-left: 6px;
}}
QMenu::indicator:checked {{
    background-color: {ACCENT};
    border-radius: 7px;
}}
QMenu::right-arrow {{
    width: 8px;
    height: 8px;
    margin-right: 8px;
}}
QMenu QLabel {{
    background: transparent;
}}
QMenu QSlider::groove:horizontal {{
    height: 4px;
    background: #34373D;
    border-radius: 2px;
}}
QMenu QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QMenu QSlider::handle:horizontal {{
    background: #F2F2F2;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
"""


def ui_font(size: int = 13, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(list(UI_FONT_FAMILIES))
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def apply_dialog_theme(widget: QWidget) -> None:
    widget.setStyleSheet(DIALOG_QSS)
    enable_dark_title_bar(widget)


def style_menu(menu: QMenu) -> None:
    menu.setStyleSheet(MENU_QSS)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, False)


def enable_dark_title_bar(widget: QWidget) -> None:
    """Use the dark Windows title bar for standard dialog frames."""

    if not sys.platform.startswith("win"):
        return
    try:
        hwnd = int(widget.winId())
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except Exception:
        pass


def swatch_style(color: QColor, selected: bool = False) -> str:
    border = "2px solid #FFFFFF" if selected else "1px solid rgba(255,255,255,0.22)"
    return (
        "QPushButton {"
        f"background-color: {color.name()};"
        f"border: {border};"
        "border-radius: 11px;"
        "}"
    )
