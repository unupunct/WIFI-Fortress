"""Settings page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wififortress import APP_DESCRIPTION, APP_LICENSE, APP_NAME, APP_VERSION
from wififortress.app.context import AppContext
from wififortress.core.paths import (
    config_dir,
    data_dir,
    dictionaries_dir,
    log_dir,
    reports_dir,
    settings_path,
)
from wififortress.core.privileges import detect_elevation
from wififortress.ui.theme import PALETTE
from wififortress.widgets.common import Banner, Card, button, divider, heading


class SettingsPage(QWidget):
    mode_changed = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(14)

        layout.addWidget(heading("Settings", "Operating mode, data locations and diagnostics."))

        mode_card = Card("Operating mode", "Quick mode hides technical detail; Advanced shows everything.")
        row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Quick mode", "Advanced mode"])
        self.mode_combo.setCurrentIndex(1 if self.context.settings.is_advanced else 0)
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        row.addWidget(self.mode_combo, 1)
        mode_card.add_layout(row)
        self.mode_note = QLabel(
            "Quick mode: minimal terminology, guided steps, recommended settings. "
            "Advanced mode: driver and phy detail, raw scan fields, tool diagnostics and logs."
        )
        self.mode_note.setObjectName("Muted")
        self.mode_note.setWordWrap(True)
        mode_card.add(self.mode_note)
        layout.addWidget(mode_card)

        behaviour = Card("Behaviour", "")
        self.store_history = QCheckBox("Store audit history in the local database")
        self.store_history.setChecked(bool(self.context.settings.get("audit_store_history", True)))
        self.store_history.toggled.connect(
            lambda checked: self.context.settings.set("audit_store_history", checked)
        )
        behaviour.add(self.store_history)
        self.remember_window = QCheckBox("Remember window size")
        self.remember_window.setChecked(bool(self.context.settings.get("remember_window", True)))
        self.remember_window.toggled.connect(
            lambda checked: self.context.settings.set("remember_window", checked)
        )
        behaviour.add(self.remember_window)
        layout.addWidget(behaviour)

        paths = Card("Data locations", "Nothing here is ever written to the installation directory.")
        for label, value in (
            ("Data", data_dir()),
            ("Settings", settings_path()),
            ("Logs", log_dir()),
            ("Reports", reports_dir()),
            ("Dictionaries", dictionaries_dir()),
            ("Configuration", config_dir()),
        ):
            line = QHBoxLayout()
            key = QLabel(label)
            key.setObjectName("Muted")
            key.setFixedWidth(110)
            val = QLabel(str(value))
            val.setObjectName("Mono")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            line.addWidget(key)
            line.addWidget(val, 1)
            wrapper = QWidget()
            wrapper.setLayout(line)
            paths.add(wrapper)
        layout.addWidget(paths)

        env = Card("Environment", "")
        elevation = detect_elevation()
        tools = self.context.adapters.tools()
        self.env_label = QLabel(
            f"{APP_NAME} {APP_VERSION}<br>{APP_DESCRIPTION}<br>License: {APP_LICENSE}<br><br>"
            f"Elevation: {elevation.label}"
            + (f" ({elevation.reason})" if elevation.reason else "")
            + "<br>Tool availability: "
            + ", ".join(f"{name}={'ok' if ok else 'missing'}" for name, ok in tools.items())
        )
        self.env_label.setObjectName("Muted")
        self.env_label.setWordWrap(True)
        self.env_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        env.add(self.env_label)
        layout.addWidget(env)

        self.reset_card = Card("Reset", "")
        reset_row = QHBoxLayout()
        reset_row.addWidget(button("Restore default settings", "danger", "", self._reset))
        reset_row.addStretch(1)
        self.reset_card.add_layout(reset_row)
        self.reset_note = QLabel("")
        self.reset_note.setObjectName("Muted")
        self.reset_card.add(self.reset_note)
        layout.addWidget(self.reset_card)
        layout.addStretch(1)

    def _on_mode(self, index: int) -> None:
        mode = "advanced" if index == 1 else "quick"
        self.context.settings.set("ui_mode", mode)
        self.context.record_operation("settings", f"Mode set to {mode}", "ok")
        self.mode_changed.emit(mode)

    def _reset(self) -> None:
        from wififortress.services.settings_service import Settings

        self.context.settings.settings = Settings()
        self.context.settings.save()
        self.mode_combo.setCurrentIndex(0)
        self.reset_note.setText("Default settings restored.")
