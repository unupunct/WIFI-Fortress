"""Adapter Manager page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.models.entities import AdapterInfo, CapabilityState
from wififortress.ui.theme import PALETTE
from wififortress.ui.workers import WorkerController
from wififortress.widgets.common import (
    Banner,
    Card,
    Pill,
    button,
    divider,
    heading,
)


class AdapterPage(QWidget):
    adapter_selected = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._worker = WorkerController(self)
        self._worker.finished.connect(self._on_discovered)
        self._worker.failed.connect(self._on_failed)

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
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.addWidget(heading(
            "Adapter Manager",
            "Wireless interfaces detected on this system, with verified capabilities only.",
        ), 1)
        self.refresh_btn = button("Refresh", "primary", "refresh", self.refresh)
        header.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        self.banner = Banner("Adapter information has not been collected yet.", "info")
        layout.addWidget(self.banner)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Interface", "Driver", "MAC", "Bands", "Monitor mode", "State"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(160)
        self.table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.use_btn = button("Use as active adapter", "primary", "check", self._use_selected)
        self.up_btn = button("Bring up", "secondary", "", lambda: self._set_link(True))
        self.down_btn = button("Bring down", "secondary", "", lambda: self._set_link(False))
        self.rfkill_btn = button("Unblock radio", "secondary", "", self._unblock)
        actions.addWidget(self.use_btn)
        actions.addWidget(self.up_btn)
        actions.addWidget(self.down_btn)
        actions.addWidget(self.rfkill_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        details = QHBoxLayout()
        details.setSpacing(16)
        self.info_card = Card("Adapter details", "Everything below comes from the kernel, iw, ethtool or NetworkManager.")
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(18)
        self.info_grid.setVerticalSpacing(8)
        self.info_card.add_layout(self.info_grid)
        details.addWidget(self.info_card, 3)

        self.compat_card = Card("Compatibility", "Capabilities are never assumed.")
        self.compat_list = QVBoxLayout()
        self.compat_list.setSpacing(6)
        self.compat_card.add_layout(self.compat_list)
        details.addWidget(self.compat_card, 2)
        layout.addLayout(details)

        self.permission_card = Card("Permissions and dependencies", "")
        self.permission_label = QLabel("")
        self.permission_label.setWordWrap(True)
        self.permission_label.setObjectName("Muted")
        self.permission_card.add(self.permission_label)
        layout.addWidget(self.permission_card)
        layout.addStretch(1)

    # -- actions --------------------------------------------------------
    def refresh(self) -> None:
        if self._worker.running:
            return
        self.refresh_btn.setEnabled(False)
        self.banner.set_text("Discovering wireless adapters…", "info")
        self._worker.start(self.context.adapters.discover)

    def _on_discovered(self, result) -> None:
        self.refresh_btn.setEnabled(True)
        self.context.adapter_list = result.adapters
        if result.adapters and not self.context.active_interface:
            self.context.active_interface = result.adapters[0].interface
        if self.context.active_interface and not any(
            a.interface == self.context.active_interface for a in result.adapters
        ):
            self.context.active_interface = result.adapters[0].interface if result.adapters else ""

        self.table.setRowCount(0)
        for adapter in result.adapters:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                adapter.interface,
                adapter.driver or "unknown",
                adapter.mac or "—",
                ", ".join(adapter.bands) or "not verified",
                adapter.monitor_mode.value,
                adapter.state or ("up" if adapter.is_up else "down"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, adapter.interface)
                self.table.setItem(row, col, item)
        if result.adapters:
            index = next(
                (i for i, a in enumerate(result.adapters)
                 if a.interface == self.context.active_interface), 0
            )
            self.table.selectRow(index)
            notes = result.notes
            self.banner.set_text(
                f"{len(result.adapters)} wireless interface(s) detected. " + " ".join(notes)
                if notes else f"{len(result.adapters)} wireless interface(s) detected.",
                "warning" if notes else "success",
            )
        else:
            self.banner.set_text(" ".join(result.notes) or "No wireless adapter found.", "error")
        self._update_permissions(result)

    def _on_failed(self, message: str, detail: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.banner.set_text(f"Adapter discovery failed: {message}", "error")

    def _selected_adapter(self) -> AdapterInfo | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        name = self.table.item(rows[0].row(), 0).text()
        return next((a for a in self.context.adapter_list if a.interface == name), None)

    def _on_selection(self) -> None:
        adapter = self._selected_adapter()
        if adapter is None:
            return
        self._fill_details(adapter)

    def _use_selected(self) -> None:
        adapter = self._selected_adapter()
        if adapter is None:
            return
        self.context.active_interface = adapter.interface
        self.context.settings.set("active_interface", adapter.interface)
        self.context.record_operation("adapter", f"Active adapter set to {adapter.interface}", "ok")
        self.adapter_selected.emit(adapter.interface)
        self.banner.set_text(f"{adapter.interface} is now the active adapter.", "success")

    def _set_link(self, up: bool) -> None:
        adapter = self._selected_adapter()
        if adapter is None:
            return
        confirm = QMessageBox.question(
            self,
            "Change interface state",
            f"{'Bring up' if up else 'Bring down'} {adapter.interface}?\n\n"
            "This changes the adapter's operational state and requires elevation. "
            "WiFi Fortress will restore the previous state afterwards if you change it back.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            result = self.context.adapters.set_interface_up(adapter.interface, up, elevated=True)
        except Exception as exc:  # PrivilegeError
            self.banner.set_text(f"Cannot change interface state: {exc}", "error")
            return
        if result.ok:
            self.context.record_operation(
                "adapter", f"{adapter.interface} brought {'up' if up else 'down'}", "ok"
            )
            self.banner.set_text(
                f"{adapter.interface} is now {'up' if up else 'down'}.", "success"
            )
            self.refresh()
        else:
            self.banner.set_text(
                f"Could not change interface state: {result.summary()}", "error"
            )

    def _unblock(self) -> None:
        adapter = self._selected_adapter()
        if adapter is None:
            return
        try:
            result = self.context.adapters.set_rfkill(adapter.interface, True)
        except Exception as exc:
            self.banner.set_text(f"rfkill failed: {exc}", "error")
            return
        if result.ok:
            self.banner.set_text("Wireless radio unblocked.", "success")
            self.refresh()
        else:
            self.banner.set_text(f"rfkill failed: {result.summary()}", "error")

    # -- rendering ------------------------------------------------------
    def _fill_details(self, adapter: AdapterInfo) -> None:
        while self.info_grid.count():
            item = self.info_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        advanced = self.context.settings.is_advanced
        fields: list[tuple[str, str]] = [
            ("Interface", adapter.interface),
            ("Manufacturer", adapter.vendor or "not reported"),
            ("Model", adapter.model or "not reported"),
            ("Chipset", adapter.chipset or "not reported"),
            ("Bus", adapter.bus or "not reported"),
            ("MAC address", adapter.mac or "not reported"),
            ("Driver", adapter.driver or "no driver bound"),
            ("Driver version", adapter.driver_version or "not reported"),
            ("phy", adapter.phy or "—"),
            ("State", adapter.state or ("up" if adapter.is_up else "down")),
            ("Connection", adapter.connection_ssid or "not connected"),
            ("Radio block", f"soft={adapter.soft_blocked} hard={adapter.hard_blocked}"),
            ("2.4 GHz", self._tri(adapter.supports_2ghz)),
            ("5 GHz", self._tri(adapter.supports_5ghz)),
            ("6 GHz", self._tri(adapter.supports_6ghz)),
        ]
        if advanced:
            fields.extend([
                ("Frequencies", f"{len(adapter.frequencies)} reported" if adapter.frequencies else "not verified"),
                ("Interface modes", ", ".join(adapter.interface_modes) or "not verified"),
                ("Standards", ", ".join(adapter.standards) or "not verified"),
                ("Monitor evidence", adapter.monitor_evidence or "—"),
            ])
        for index, (key, value) in enumerate(fields):
            key_label = QLabel(key)
            key_label.setObjectName("Muted")
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row, col = divmod(index, 2)
            self.info_grid.addWidget(key_label, row, col * 2)
            self.info_grid.addWidget(value_label, row, col * 2 + 1)

        while self.compat_list.count():
            item = self.compat_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def add_pill(label: str, state: CapabilityState, note: str = "") -> None:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch(1)
            color = {
                CapabilityState.SUPPORTED: PALETTE.success,
                CapabilityState.UNSUPPORTED: PALETTE.critical,
                CapabilityState.UNKNOWN: PALETTE.warning,
                CapabilityState.UNAVAILABLE: PALETTE.text_dim,
            }[state]
            row.addWidget(Pill(state.value, color))
            wrapper = QWidget()
            wrapper.setLayout(row)
            self.compat_list.addWidget(wrapper)
            if note:
                note_label = QLabel(note)
                note_label.setObjectName("Dim")
                note_label.setWordWrap(True)
                self.compat_list.addWidget(note_label)

        add_pill("Monitor mode", adapter.monitor_mode, adapter.monitor_evidence)
        add_pill("Access point mode", adapter.ap_mode)
        add_pill("Packet injection", adapter.packet_injection,
                 "Not advertised by nl80211; depends on the driver build and cannot be verified here.")
        if adapter.driver_problem:
            warn = QLabel(adapter.driver_problem)
            warn.setStyleSheet(f"color: {PALETTE.warning};")
            warn.setWordWrap(True)
            self.compat_list.addWidget(warn)

    @staticmethod
    def _tri(value: bool | None) -> str:
        if value is None:
            return "not verified"
        return "yes" if value else "no"

    def _update_permissions(self, result) -> None:
        tools = result.tools_available
        missing = [name for name, ok in tools.items() if not ok]
        text = (
            "Tool availability: "
            + ", ".join(f"{name}={'ok' if ok else 'missing'}" for name, ok in tools.items())
        )
        if missing:
            text += (
                "\nSome capabilities cannot be verified without: " + ", ".join(missing)
                + ". Install them with: sudo apt install " + " ".join(missing)
            )
        text += (
            "\nReading adapter information needs no privileges. Changing link state or "
            "rfkill needs elevation, which WiFi Fortress requests per operation via pkexec."
        )
        self.permission_label.setText(text)
