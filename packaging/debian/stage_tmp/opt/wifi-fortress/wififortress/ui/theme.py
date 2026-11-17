"""Parrot OS inspired visual theme.

A single QSS string plus palette constants.  Everything in the UI pulls its
colours from here so the look stays consistent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    background: str = "#101820"
    secondary: str = "#172630"
    panel: str = "#1D303B"
    panel_alt: str = "#223844"
    border: str = "#2B4453"
    accent: str = "#00D4C7"
    accent2: str = "#00A8E8"
    success: str = "#31C48D"
    warning: str = "#F5B942"
    critical: str = "#EF5350"
    text: str = "#EDF6F7"
    text_muted: str = "#94AAB3"
    text_dim: str = "#6E828B"
    hover: str = "#26414F"
    selection: str = "#0E5A63"


PALETTE = Palette()

SEVERITY_COLORS = {
    "Critical": PALETTE.critical,
    "High": PALETTE.warning,
    "Medium": PALETTE.accent2,
    "Low": PALETTE.accent,
    "Informational": PALETTE.text_muted,
    "Unknown": PALETTE.text_dim,
}

STATUS_COLORS = {
    "ok": PALETTE.success,
    "warn": PALETTE.warning,
    "fail": PALETTE.critical,
    "skip": PALETTE.text_dim,
    "running": PALETTE.accent2,
    "unknown": PALETTE.text_muted,
}


def stylesheet() -> str:
    p = PALETTE
    return f"""
* {{
    font-family: "Inter", "Cantarell", "DejaVu Sans", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {p.text};
}}
QWidget {{
    background-color: {p.background};
    selection-background-color: {p.selection};
    selection-color: {p.text};
}}
QMainWindow, QDialog {{ background-color: {p.background}; }}
QToolTip {{
    background-color: {p.panel};
    color: {p.text};
    border: 1px solid {p.border};
    padding: 6px 8px;
    border-radius: 6px;
}}

/* ---------- Sidebar ---------- */
#Sidebar {{
    background-color: {p.secondary};
    border-right: 1px solid {p.border};
}}
#BrandTitle {{
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.6px;
    color: {p.text};
    background: transparent;
}}
#BrandAccent {{ color: {p.accent}; }}
#BrandSubtitle {{
    color: {p.text_dim};
    font-size: 10.5px;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    background: transparent;
}}
#NavButton {{
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 9px;
    background: transparent;
    color: {p.text_muted};
    font-size: 13.5px;
}}
#NavButton:hover {{
    background-color: {p.hover};
    color: {p.text};
}}
#NavButton:checked {{
    background-color: {p.panel};
    color: {p.accent};
    font-weight: 600;
}}
#NavBadge {{
    color: {p.text_dim};
    font-size: 10.5px;
    padding-left: 10px;
    background: transparent;
}}
#SidebarFooter {{
    color: {p.text_dim};
    font-size: 11px;
    background: transparent;
}}

/* ---------- Headings ---------- */
#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    background: transparent;
}}
#PageSubtitle {{
    color: {p.text_muted};
    font-size: 12.5px;
    background: transparent;
}}
#SectionTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {p.text};
    background: transparent;
}}
#Muted {{ color: {p.text_muted}; background: transparent; }}
#Dim {{ color: {p.text_dim}; background: transparent; }}
#AccentText {{ color: {p.accent}; background: transparent; }}
#Mono {{
    font-family: "JetBrains Mono", "DejaVu Sans Mono", "Consolas", monospace;
    background: transparent;
}}

/* ---------- Panels and cards ---------- */
#Card, #Panel {{
    background-color: {p.panel};
    border: 1px solid {p.border};
    border-radius: 14px;
}}
#Card:hover {{ border-color: {p.selection}; }}
#PanelFlat {{
    background-color: {p.secondary};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
#StatValue {{
    font-size: 24px;
    font-weight: 700;
    color: {p.accent};
    background: transparent;
}}
#StatLabel {{
    color: {p.text_muted};
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.9px;
    background: transparent;
}}
#StatHint {{ color: {p.text_dim}; font-size: 11px; background: transparent; }}
#ActionCard {{
    background-color: {p.panel};
    border: 1px solid {p.border};
    border-radius: 16px;
}}
#ActionCard:hover {{ border-color: {p.accent}; }}
#ActionTitle {{ font-size: 16px; font-weight: 600; background: transparent; }}
#ActionBody {{ color: {p.text_muted}; font-size: 12.5px; background: transparent; }}

/* ---------- Buttons ---------- */
QPushButton {{
    background-color: {p.panel_alt};
    border: 1px solid {p.border};
    border-radius: 9px;
    padding: 8px 16px;
    color: {p.text};
}}
QPushButton:hover {{ background-color: {p.hover}; border-color: {p.accent}; }}
QPushButton:pressed {{ background-color: {p.selection}; }}
QPushButton:disabled {{ color: {p.text_dim}; background-color: {p.secondary}; border-color: {p.border}; }}
QPushButton#Primary {{
    background-color: {p.accent};
    color: #08282B;
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background-color: #14E6D8; }}
QPushButton#Primary:disabled {{ background-color: #1E5A5E; color: {p.text_dim}; }}
QPushButton#Secondary {{
    background-color: transparent;
    border: 1px solid {p.accent2};
    color: {p.accent2};
}}
QPushButton#Secondary:hover {{ background-color: rgba(0, 168, 232, 0.12); }}
QPushButton#Danger {{
    background-color: transparent;
    border: 1px solid {p.critical};
    color: {p.critical};
}}
QPushButton#Danger:hover {{ background-color: rgba(239, 83, 80, 0.15); }}
QPushButton#Ghost {{
    background: transparent;
    border: none;
    color: {p.text_muted};
    padding: 6px 10px;
}}
QPushButton#Ghost:hover {{ color: {p.accent}; background-color: {p.hover}; }}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {p.accent2};
    padding: 0;
    text-align: left;
}}
QPushButton#Link:hover {{ color: {p.accent}; }}

/* ---------- Inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background-color: {p.secondary};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 7px 10px;
    color: {p.text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {p.accent};
}}
QLineEdit:disabled, QComboBox:disabled {{ color: {p.text_dim}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {p.panel};
    border: 1px solid {p.border};
    selection-background-color: {p.selection};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; background: transparent; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {p.border};
    border-radius: 4px;
    background: {p.secondary};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QSlider::groove:horizontal {{
    height: 5px; background: {p.border}; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 15px; margin: -6px 0; border-radius: 8px; background: {p.accent};
}}
QSlider::sub-page:horizontal {{ background: {p.accent2}; border-radius: 3px; }}

/* ---------- Tables and lists ---------- */
QTableView, QTreeView, QListWidget {{
    background-color: {p.secondary};
    alternate-background-color: {p.secondary};
    border: 1px solid {p.border};
    border-radius: 10px;
    gridline-color: {p.border};
    outline: none;
}}
QTableView::item, QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid #1B2B35;
}}
QTableView::item:selected, QListWidget::item:selected {{
    background-color: {p.selection};
    color: {p.text};
}}
QListWidget::item:hover {{ background-color: {p.hover}; }}
QHeaderView::section {{
    background-color: {p.panel};
    color: {p.text_muted};
    padding: 7px 8px;
    border: none;
    border-bottom: 1px solid {p.border};
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.7px;
}}
QTableCornerButton::section {{ background-color: {p.panel}; border: none; }}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {p.border};
    border-radius: 10px;
    background-color: {p.secondary};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {p.text_muted};
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p.accent}; border-bottom: 2px solid {p.accent}; }}
QTabBar::tab:hover {{ color: {p.text}; }}

/* ---------- Progress ---------- */
QProgressBar {{
    background-color: {p.secondary};
    border: 1px solid {p.border};
    border-radius: 7px;
    height: 12px;
    text-align: center;
    color: {p.text_muted};
    font-size: 10px;
}}
QProgressBar::chunk {{
    background-color: {p.accent};
    border-radius: 6px;
}}
#BusyBar::chunk {{ background-color: {p.accent2}; }}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p.border}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.selection}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------- Misc ---------- */
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QGroupBox {{
    border: 1px solid {p.border};
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {p.text_muted};
}}
QStatusBar {{ background: {p.secondary}; color: {p.text_muted}; border-top: 1px solid {p.border}; }}
QStatusBar::item {{ border: none; }}
QMenu {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.selection}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QTextBrowser {{
    background-color: {p.secondary};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 12px;
}}
QMessageBox {{ background-color: {p.panel}; }}
QMessageBox QLabel {{ background: transparent; }}
#Divider {{ background-color: {p.border}; max-height: 1px; min-height: 1px; }}
#Pill {{
    border-radius: 9px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    background: {p.panel_alt};
    color: {p.text_muted};
}}
#StepDot {{
    border-radius: 12px;
    min-width: 24px; max-width: 24px;
    min-height: 24px; max-height: 24px;
    background: {p.secondary};
    border: 1px solid {p.border};
    color: {p.text_muted};
    font-weight: 600;
}}
#StepDot[active="true"] {{
    background: {p.accent};
    border-color: {p.accent};
    color: #08282B;
}}
#StepDot[done="true"] {{
    background: {p.success};
    border-color: {p.success};
    color: #08282B;
}}
"""
