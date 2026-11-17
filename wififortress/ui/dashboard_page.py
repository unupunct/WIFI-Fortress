"""Dashboard: at-a-glance state plus the two primary action cards."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.core.paths import data_dir
from wififortress.services.audit_service import audit_summary
from wififortress.ui.theme import PALETTE
from wififortress.widgets.common import (
    ActionCard,
    Card,
    Pill,
    StatTile,
    button,
    divider,
    heading,
    icon_label,
)


class DashboardPage(QWidget):
    navigate = Signal(str)
    start_recovery = Signal()
    start_audit = Signal()

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
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.addWidget(heading(
            "Dashboard",
            "Wireless adapter state, network overview and the two guided workflows.",
        ), 1)
        self.mode_pill = Pill("Quick mode")
        header.addWidget(self.mode_pill, 0, Qt.AlignTop)
        self.refresh_btn = button("Refresh", icon="refresh", on_click=self.refresh)
        header.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        # --- action cards -------------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(16)
        self.recovery_card = ActionCard(
            "Wi-Fi Recovery",
            "Guided process to locate an accessible saved credential for a network you "
            "own, or recover access through the router's administration page or a "
            "documented password reset.",
            "Start Wi-Fi Recovery",
            icon="key",
        )
        self.recovery_card.activated.connect(self.start_recovery)
        self.audit_card = ActionCard(
            "Security Audit",
            "Guided defensive examination of a selected wireless network: encryption, "
            "authentication, WPS, PMF, congestion and router exposure, with evidence "
            "and a documented 0-100 score.",
            "Start Security Audit",
            icon="shield",
        )
        self.audit_card.activated.connect(self.start_audit)
        actions.addWidget(self.recovery_card, 1)
        actions.addWidget(self.audit_card, 1)
        layout.addLayout(actions)

        # --- stat tiles ---------------------------------------------------
        tiles = QGridLayout()
        tiles.setSpacing(14)
        self.adapter_tile = StatTile("Wireless adapter", "—", "", icon="adapter")
        self.connection_tile = StatTile("Connected network", "—", "", icon="wifi")
        self.networks_tile = StatTile("Nearby networks", "—", "", icon="wifi")
        self.bands_tile = StatTile("Supported bands", "—", "", icon="pulse")
        self.interface_tile = StatTile("Active interface", "—", "", icon="adapter")
        self.audit_tile = StatTile("Last security audit", "—", "", icon="shield")
        self.score_tile = StatTile("Security score", "—", "", icon="shield")
        self.password_tile = StatTile("Password assessment", "—", "", icon="lock")
        for index, tile in enumerate(
            [
                self.adapter_tile,
                self.connection_tile,
                self.networks_tile,
                self.bands_tile,
                self.interface_tile,
                self.audit_tile,
                self.score_tile,
                self.password_tile,
            ]
        ):
            tiles.addWidget(tile, index // 4, index % 4)
        layout.addLayout(tiles)

        self.interface_tile.clicked.connect(lambda: self.navigate.emit("adapters"))
        self.networks_tile.clicked.connect(lambda: self.navigate.emit("networks"))
        self.audit_tile.clicked.connect(lambda: self.navigate.emit("audit"))
        self.password_tile.clicked.connect(lambda: self.navigate.emit("recovery"))
        self.score_tile.clicked.connect(lambda: self.navigate.emit("reports"))

        # --- lower panels -------------------------------------------------
        lower = QHBoxLayout()
        lower.setSpacing(16)
        self.recent_card = Card("Recent operations", "The last actions performed in this session.")
        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(6)
        self.recent_card.add_layout(self.recent_list)
        self.recent_card.body().addStretch(1)
        lower.addWidget(self.recent_card, 3)

        self.recs_card = Card("Security recommendations", "Derived from the most recent audit.")
        self.recs_list = QVBoxLayout()
        self.recs_list.setSpacing(6)
        self.recs_card.add_layout(self.recs_list)
        self.recs_card.body().addStretch(1)
        lower.addWidget(self.recs_card, 2)
        layout.addLayout(lower)

        self.env_card = Card("Environment", "Where WiFi Fortress keeps its data on this machine.")
        self.env_label = QLabel(str(data_dir()))
        self.env_label.setObjectName("Mono")
        self.env_label.setWordWrap(True)
        self.env_card.add(self.env_label)
        self.env_note = QLabel("")
        self.env_note.setObjectName("Muted")
        self.env_note.setWordWrap(True)
        self.env_card.add(self.env_note)
        layout.addWidget(self.env_card)
        layout.addStretch(1)

    # -- data binding ---------------------------------------------------
    def refresh(self) -> None:
        ctx = self.context
        self.mode_pill.set_status(
            "Advanced mode" if ctx.settings.is_advanced else "Quick mode",
            PALETTE.accent2 if ctx.settings.is_advanced else PALETTE.accent,
        )

        adapter = ctx.active_adapter
        if adapter:
            self.adapter_tile.set_value(adapter.interface)
            self.adapter_tile.set_hint(
                " ".join(x for x in (adapter.vendor, adapter.model) if x) or adapter.driver or "Driver unknown"
            )
            self.interface_tile.set_value(adapter.interface)
            state = adapter.state or ("up" if adapter.is_up else "down")
            self.interface_tile.set_hint(f"{state} · driver {adapter.driver or 'unknown'}")
            if adapter.connection_ssid:
                self.connection_tile.set_value(adapter.connection_ssid)
                self.connection_tile.set_hint("Connected" if adapter.is_connected else adapter.state)
            else:
                self.connection_tile.set_value("Not connected")
                self.connection_tile.set_hint("No active Wi-Fi connection")
            bands = adapter.bands or []
            self.bands_tile.set_value(", ".join(b.replace(" GHz", "") for b in bands) + " GHz" if bands else "Not verified")
            self.bands_tile.set_hint(
                "From iw list" if bands else "Capabilities not verified (iw missing or phy not readable)"
            )
        else:
            for tile in (self.adapter_tile, self.connection_tile, self.bands_tile, self.interface_tile):
                tile.set_value("—")
            self.adapter_tile.set_hint("No wireless adapter detected")
            self.bands_tile.set_hint("Run Adapter Manager to refresh")

        self.networks_tile.set_value(str(len(ctx.networks)) if ctx.networks else "—")
        self.networks_tile.set_hint(
            f"Source: {ctx.last_scan_source}" if ctx.networks else "Run a scan in Wireless Networks"
        )

        if ctx.last_audit:
            self.audit_tile.set_value(ctx.last_audit.get("ssid", "—"))
            self.audit_tile.set_hint(ctx.last_audit_at or ctx.last_audit.get("created_at", ""))
            score = ctx.last_audit.get("score", 0)
            self.score_tile.set_value(f"{score}/100")
            grade = ctx.last_audit.get("grade", "")
            color = (
                PALETTE.success if score >= 75 else PALETTE.warning if score >= 50 else PALETTE.critical
            )
            self.score_tile.set_value(f"{score}/100", color)
            self.score_tile.set_hint(f"Grade {grade}")
        else:
            self.audit_tile.set_value("None yet")
            self.audit_tile.set_hint("No audit has been run in this session")
            self.score_tile.set_value("—")
            self.score_tile.set_hint("Run a Security Audit")

        if ctx.last_recovery_summary:
            self.password_tile.set_value(str(ctx.last_recovery_summary.get("profiles", 0)))
            self.password_tile.set_hint("Saved Wi-Fi profiles visible to your user")
        else:
            self.password_tile.set_value("—")
            self.password_tile.set_hint("Open Wi-Fi Recovery to inspect saved profiles")

        self._fill_recent()
        self._fill_recommendations()
        self.env_note.setText(
            "Logs are redacted before they are written. Reports contain no credentials."
        )

    def _fill_recent(self) -> None:
        while self.recent_list.count():
            item = self.recent_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.context.db.operations(8)
        if not rows:
            label = QLabel("No operations recorded yet.")
            label.setObjectName("Dim")
            self.recent_list.addWidget(label)
            return
        for row in rows:
            line = QHBoxLayout()
            dot = icon_label(
                "check" if row["status"] == "ok" else "warning",
                14,
                PALETTE.success if row["status"] == "ok" else PALETTE.warning,
            )
            line.addWidget(dot)
            title = QLabel(row["title"])
            title.setWordWrap(True)
            line.addWidget(title, 1)
            when = QLabel(row["created_at"].replace("T", " ").replace("+00:00", " UTC"))
            when.setObjectName("Dim")
            line.addWidget(when)
            wrapper = QWidget()
            wrapper.setLayout(line)
            self.recent_list.addWidget(wrapper)

    def _fill_recommendations(self) -> None:
        while self.recs_list.count():
            item = self.recs_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        audit = self.context.last_audit
        if not audit:
            label = QLabel(
                "No audit yet. Run a Security Audit on your own network to receive "
                "recommendations based on evidence."
            )
            label.setObjectName("Dim")
            label.setWordWrap(True)
            self.recs_list.addWidget(label)
            return
        summary = QLabel(audit_summary(type("A", (), {
            "score": audit.get("score", 0),
            "grade": audit.get("grade", ""),
            "severity_counts": audit.get("severity_counts", {}),
        })()))
        summary.setWordWrap(True)
        self.recs_list.addWidget(summary)
        self.recs_list.addWidget(divider())
        for item in audit.get("checklist", [])[:5]:
            label = QLabel("• " + item)
            label.setWordWrap(True)
            self.recs_list.addWidget(label)
