"""Wireless Networks page: discovery table, filters and charts."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.models.entities import Security, WirelessNetwork
from wififortress.services.discovery_service import WirelessDiscoveryService
from wififortress.ui.theme import PALETTE
from wififortress.ui.workers import WorkerController
from wififortress.widgets.charts import BarChart, DonutChart, SignalHistoryChart
from wififortress.widgets.common import Banner, Card, SignalBars, button, divider, heading

COLUMNS = ["SSID", "BSSID", "Signal", "", "Channel", "Band", "Security", "Auth", "Quality", "Seen"]


class NetworksPage(QWidget):
    audit_requested = Signal(object)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._worker = WorkerController(self)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._history: dict[str, list[float]] = {}
        self._selected_bssid = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(heading(
            "Wireless Networks",
            "Networks in range. Discovery reveals network configuration - never a Wi-Fi password.",
        ), 1)
        self.interface_combo = QComboBox()
        self.interface_combo.setMinimumWidth(140)
        self.interface_combo.currentTextChanged.connect(self._on_interface_changed)
        header.addWidget(self.interface_combo, 0, Qt.AlignTop)
        self.scan_btn = button("Start scan", "primary", "play", self.start_scan)
        header.addWidget(self.scan_btn, 0, Qt.AlignTop)
        self.stop_btn = button("Stop", "secondary", "stop", self.stop_scan)
        self.stop_btn.setEnabled(False)
        header.addWidget(self.stop_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        self.banner = Banner(
            "No scan has been run yet. Select an adapter and start a scan.", "info"
        )
        layout.addWidget(self.banner)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by SSID or BSSID…")
        self.search.textChanged.connect(self._apply_filters)
        filters.addWidget(self.search, 2)
        self.enc_filter = QComboBox()
        self.enc_filter.addItems(
            ["All security types", "WPA3", "WPA2", "WPA", "WEP", "Open", "Enterprise", "Unknown"]
        )
        self.enc_filter.currentTextChanged.connect(self._apply_filters)
        filters.addWidget(self.enc_filter, 1)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Strongest signal", "SSID (A-Z)", "Channel", "Security"])
        self.sort_combo.currentTextChanged.connect(self._apply_filters)
        filters.addWidget(self.sort_combo, 1)
        self.auto_refresh = QComboBox()
        self.auto_refresh.addItems(["Manual refresh", "Every 15 s", "Every 30 s", "Every 60 s"])
        self.auto_refresh.currentTextChanged.connect(self._on_auto_refresh)
        filters.addWidget(self.auto_refresh, 1)
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Interactive)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 34)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 130)
        self.table.setColumnWidth(8, 80)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(12)
        self.detail_card = Card("Network details", "Select a row for the full record.")
        self.detail_label = QLabel("No network selected.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setObjectName("Muted")
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_card.add(self.detail_label)
        self.audit_btn = button("Audit this network", "primary", "shield", self._audit_selected)
        self.audit_btn.setEnabled(False)
        self.detail_card.add(self.audit_btn)
        side_layout.addWidget(self.detail_card, 1)

        self.history_card = Card("Signal history", "dBm per scan for the selected network.")
        self.history_chart = SignalHistoryChart()
        self.history_chart.setMinimumHeight(120)
        self.history_card.add(self.history_chart)
        side_layout.addWidget(self.history_card, 1)
        splitter.addWidget(side)
        splitter.setSizes([760, 340])
        layout.addWidget(splitter, 3)

        charts = QHBoxLayout()
        charts.setSpacing(14)
        self.channel_card = Card("Channel distribution", "Access points per channel.")
        self.channel_chart = BarChart()
        self.channel_chart.setMinimumHeight(150)
        self.channel_card.add(self.channel_chart)
        charts.addWidget(self.channel_card, 3)
        self.security_card = Card("Security distribution", "")
        self.security_chart = DonutChart()
        self.security_chart.setMinimumHeight(150)
        self.security_card.add(self.security_chart)
        charts.addWidget(self.security_card, 2)
        layout.addLayout(charts, 2)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.start_scan)
        self.refresh_interfaces()

    # -- lifecycle ------------------------------------------------------
    def refresh_interfaces(self) -> None:
        current = self.context.active_interface
        interfaces = [a.interface for a in self.context.adapter_list]
        self.interface_combo.blockSignals(True)
        self.interface_combo.clear()
        self.interface_combo.addItems(interfaces or ["no adapter"])
        if current in interfaces:
            self.interface_combo.setCurrentText(current)
        self.interface_combo.blockSignals(False)

    def _on_interface_changed(self, name: str) -> None:
        if name and name != "no adapter":
            self.context.active_interface = name
            self.context.settings.set("active_interface", name)

    def _on_auto_refresh(self, label: str) -> None:
        intervals = {"Every 15 s": 15000, "Every 30 s": 30000, "Every 60 s": 60000}
        if label in intervals:
            self._timer.start(intervals[label])
        else:
            self._timer.stop()

    # -- scanning -------------------------------------------------------
    def start_scan(self) -> None:
        if self._worker.running:
            return
        interface = self.interface_combo.currentText()
        if not interface or interface == "no adapter":
            self.banner.set_text(
                "No wireless adapter selected. Open Adapter Manager and refresh first.", "warning"
            )
            return
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.banner.set_text(f"Scanning on {interface}…", "info")
        self._worker.start(self.context.discovery.scan, interface)

    def stop_scan(self) -> None:
        self._worker.cancel()

    def _on_scan_finished(self, result) -> None:
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if result is None:
            return
        if result.cancelled:
            self.banner.set_text("Scan cancelled.", "warning")
            return
        if result.error:
            self.banner.set_text(result.error, "error")
            self.context.last_scan_error = result.error
            return
        merged = WirelessDiscoveryService.merge_history(self.context.networks, result.networks)
        self.context.networks = merged
        self.context.last_scan_source = result.source
        self.context.last_scan_error = ""
        for network in merged:
            history = self._history.setdefault(network.bssid, [])
            if network.signal_dbm is not None:
                history.append(float(network.signal_dbm))
                del history[:-30]
        self.context.record_operation(
            "scan", f"Scan on {result.interface}: {len(merged)} networks", "ok",
            f"source={result.source}",
        )
        note = " ".join(result.notes)
        self.banner.set_text(
            f"{len(merged)} network(s) detected via {result.source} "
            f"in {result.duration:.1f}s." + (f" {note}" if note else ""),
            "warning" if note else "success",
        )
        self._apply_filters()

    def _on_scan_failed(self, message: str, detail: str) -> None:
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.banner.set_text(f"Scan failed: {message}", "error")

    # -- rendering ------------------------------------------------------
    def _visible_networks(self) -> list[WirelessNetwork]:
        networks = list(self.context.networks)
        text = self.search.text().strip().lower()
        if text:
            networks = [
                n for n in networks
                if text in n.ssid.lower() or text in n.bssid.lower()
            ]
        choice = self.enc_filter.currentText()
        if choice != "All security types":
            if choice == "Enterprise":
                networks = [n for n in networks if n.security.is_enterprise]
            elif choice == "Unknown":
                networks = [n for n in networks if n.security is Security.UNKNOWN]
            else:
                networks = [n for n in networks if choice in n.security.value]
        sort = self.sort_combo.currentText()
        if sort == "Strongest signal":
            networks.sort(key=lambda n: n.signal_dbm or -999, reverse=True)
        elif sort == "SSID (A-Z)":
            networks.sort(key=lambda n: n.display_ssid.lower())
        elif sort == "Channel":
            networks.sort(key=lambda n: (n.band.value, n.channel or 0))
        else:
            networks.sort(key=lambda n: n.security.value)
        return networks

    def _apply_filters(self) -> None:
        networks = self._visible_networks()
        self.table.setRowCount(0)
        for network in networks:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                network.display_ssid,
                network.bssid,
                f"{network.signal_dbm} dBm" if network.signal_dbm is not None else "—",
                "",
                str(network.channel or "—"),
                network.band.value,
                network.security.value,
                network.authentication,
                network.quality_label,
                network.last_seen[11:19] if len(network.last_seen) > 19 else network.last_seen,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, network.bssid)
                if col == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, col, item)
            bars = SignalBars(network.signal_percent)
            self.table.setCellWidget(row, 3, bars)
            if network.security is Security.OPEN:
                self.table.item(row, 6).setForeground(Qt.red)
            elif network.security in (Security.WEP, Security.WPA):
                self.table.item(row, 6).setForeground(Qt.darkYellow)
        self._update_charts(networks)
        self._restore_selection()

    def _restore_selection(self) -> None:
        if not self._selected_bssid:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == self._selected_bssid:
                self.table.selectRow(row)
                return

    def _on_row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        bssid = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        network = next((n for n in self.context.networks if n.bssid == bssid), None)
        if network is None:
            return
        self._selected_bssid = bssid
        advanced = self.context.settings.is_advanced
        lines = [
            f"<b>{network.display_ssid}</b>",
            f"BSSID: {network.bssid}",
            f"Security: {network.security.value} ({'verified' if network.security_verified else 'not verified'})",
            f"Authentication: {network.authentication}",
            f"Cipher: {network.cipher or '—'}",
            f"Band / channel: {network.band.value} / {network.channel or '—'}",
            f"Frequency: {network.frequency or '—'} MHz",
            f"Signal: {network.signal_dbm if network.signal_dbm is not None else '—'} dBm "
            f"({network.signal_percent}%, {network.quality_label})",
            f"WPS: {'enabled' if network.wps else 'not reported' if network.wps is None else 'disabled'}",
            f"PMF: {network.pmf}",
            f"Hidden: {'yes' if network.hidden else 'no'}",
            f"First seen: {network.first_seen}",
            f"Last seen: {network.last_seen}",
            f"Sightings in this session: {network.sightings}",
        ]
        if advanced:
            lines.append(f"Source: {network.source}")
            lines.append(f"Raw: {network.raw}")
        self.detail_label.setText("<br>".join(lines))
        self.audit_btn.setEnabled(True)
        history = self._history.get(bssid, [])
        self.history_chart.set_series(history)

    def _audit_selected(self) -> None:
        network = next((n for n in self.context.networks if n.bssid == self._selected_bssid), None)
        if network:
            self.audit_requested.emit(network)

    def _update_charts(self, networks: list[WirelessNetwork]) -> None:
        distribution = WirelessDiscoveryService.channel_distribution(networks)
        series: list[tuple[str, dict[int, int]]] = []
        for band in ("2.4 GHz", "5 GHz", "6 GHz"):
            channels = distribution.get(band, {})
            if channels:
                series.append((band, channels))
        self.channel_chart.set_series(series)
        self.security_chart.set_values(WirelessDiscoveryService.security_distribution(networks))
