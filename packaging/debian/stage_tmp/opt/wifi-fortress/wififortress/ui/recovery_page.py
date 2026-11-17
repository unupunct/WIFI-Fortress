"""Wi-Fi Recovery Center: guided wizard for authorised credential access."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.models.entities import RecoveryStatus, WirelessNetwork
from wififortress.ui.theme import PALETTE
from wififortress.ui.workers import WorkerController
from wififortress.widgets.common import (
    Banner,
    Card,
    Pill,
    StepIndicator,
    button,
    divider,
    heading,
    mono_label,
)

STEPS = ["Adapter", "Scan", "Network", "Methods", "Result"]


class RecoveryPage(QWidget):
    status_changed = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._worker = WorkerController(self)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._credential: str | None = None
        self._revealed = False
        self._selected: WirelessNetwork | None = None
        self._router_info = None

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

        layout.addWidget(heading(
            "Wi-Fi Recovery",
            "Recover a credential only from a profile that already exists for your user "
            "on this computer, or regain access through the router's own administration page.",
        ))

        self.legal = Banner(
            "Authorised use only. WiFi Fortress reads saved profiles of the current user "
            "and never captures handshakes, never cracks passwords and never sends "
            "credentials anywhere.",
            "warning",
        )
        layout.addWidget(self.legal)

        self.steps = StepIndicator(STEPS)
        layout.addWidget(self.steps)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step_adapter())
        self.stack.addWidget(self._build_step_scan())
        self.stack.addWidget(self._build_step_network())
        self.stack.addWidget(self._build_step_methods())
        self.stack.addWidget(self._build_step_result())
        layout.addWidget(self.stack, 1)

        nav = QHBoxLayout()
        self.back_btn = button("Back", "secondary", on_click=self._back)
        self.next_btn = button("Continue", "primary", on_click=self._next)
        nav.addStretch(1)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)
        self._update_nav()

    # -- step 1 ---------------------------------------------------------
    def _build_step_adapter(self) -> QWidget:
        page = Card("Step 1 — Select adapter", "Wireless adapters detected on this system.")
        self.adapter_combo = QComboBox()
        page.add(self.adapter_combo)
        self.adapter_note = QLabel("")
        self.adapter_note.setObjectName("Muted")
        self.adapter_note.setWordWrap(True)
        page.add(self.adapter_note)
        page.add(button("Detect adapters", "secondary", "refresh", self._load_adapters))
        page.body().addStretch(1)
        return page

    def _load_adapters(self) -> None:
        adapters = self.context.adapter_list
        self.adapter_combo.clear()
        if not adapters:
            self.adapter_note.setText(
                "No adapters detected yet. Open Adapter Manager and refresh, then return here."
            )
            return
        for adapter in adapters:
            self.adapter_combo.addItem(adapter.display_name, adapter.interface)
        index = self.adapter_combo.findData(self.context.active_interface)
        if index >= 0:
            self.adapter_combo.setCurrentIndex(index)
        self.adapter_note.setText(
            f"{len(adapters)} adapter(s) available. The adapter is used for scanning only."
        )

    # -- step 2 ---------------------------------------------------------
    def _build_step_scan(self) -> QWidget:
        page = Card("Step 2 — Scan networks", "Discover the networks your adapter can see.")
        self.scan_banner = Banner("Ready to scan.", "info")
        page.add(self.scan_banner)
        row = QHBoxLayout()
        self.scan_btn = button("Scan now", "primary", "play", self._run_scan)
        self.stop_btn = button("Stop", "secondary", "stop", self._stop_scan)
        self.stop_btn.setEnabled(False)
        row.addWidget(self.scan_btn)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        page.add_layout(row)
        self.scan_list = QListWidget()
        self.scan_list.setMinimumHeight(220)
        page.add(self.scan_list)
        page.body().addStretch(1)
        return page

    def _run_scan(self) -> None:
        if self._worker.running:
            return
        interface = self.adapter_combo.currentData() or self.context.active_interface
        if not interface:
            self.scan_banner.set_text("Select an adapter first.", "warning")
            return
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.scan_banner.set_text(f"Scanning on {interface}…", "info")
        self._worker.start(self.context.discovery.scan, interface)

    def _stop_scan(self) -> None:
        self._worker.cancel()

    def _on_scan_finished(self, result) -> None:
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if result is None or result.cancelled:
            self.scan_banner.set_text("Scan cancelled.", "warning")
            return
        if result.error:
            self.scan_banner.set_text(result.error, "error")
            return
        self.context.networks = result.networks
        self.context.last_scan_source = result.source
        self.scan_list.clear()
        for network in result.networks:
            text = (
                f"{network.display_ssid}   ·   {network.security.value}   ·   "
                f"{network.signal_dbm if network.signal_dbm is not None else '—'} dBm   ·   "
                f"{network.bssid}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, network.bssid)
            self.scan_list.addItem(item)
        self.scan_banner.set_text(
            f"{len(result.networks)} network(s) found via {result.source}.", "success"
        )

    def _on_scan_failed(self, message: str, detail: str) -> None:
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.scan_banner.set_text(f"Scan failed: {message}", "error")

    # -- step 3 ---------------------------------------------------------
    def _build_step_network(self) -> QWidget:
        page = Card("Step 3 — Select network", "Choose the network you are authorised to recover.")
        self.network_combo = QComboBox()
        page.add(self.network_combo)
        self.network_details = QLabel("No network selected.")
        self.network_details.setObjectName("Muted")
        self.network_details.setWordWrap(True)
        page.add(self.network_details)
        page.body().addStretch(1)
        return page

    def _refresh_network_combo(self) -> None:
        self.network_combo.clear()
        for network in self.context.networks:
            self.network_combo.addItem(
                f"{network.display_ssid} ({network.bssid})", network.bssid
            )
        if self._selected is not None:
            index = self.network_combo.findData(self._selected.bssid)
            if index >= 0:
                self.network_combo.setCurrentIndex(index)
        self._update_network_details()

    def _update_network_details(self) -> None:
        bssid = self.network_combo.currentData()
        network = next((n for n in self.context.networks if n.bssid == bssid), None)
        self._selected = network
        if network is None:
            self.network_details.setText("No network selected.")
            return
        self.network_details.setText(
            f"<b>{network.display_ssid}</b><br>"
            f"BSSID: {network.bssid}<br>"
            f"Security: {network.security.value} ({network.authentication})<br>"
            f"Band: {network.band.value}, channel {network.channel or '—'}<br>"
            f"Signal: {network.signal_dbm if network.signal_dbm is not None else '—'} dBm"
        )

    # -- step 4 ---------------------------------------------------------
    def _build_step_methods(self) -> QWidget:
        page = Card("Step 4 — Available recovery methods",
                    "Each method is checked against this computer's real state.")
        self.methods_list = QVBoxLayout()
        self.methods_list.setSpacing(8)
        page.add_layout(self.methods_list)
        self.methods_banner = Banner("", "info")
        page.add(self.methods_banner)
        page.body().addStretch(1)
        return page

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _evaluate_methods(self) -> None:
        self._clear_layout(self.methods_list)
        network = self._selected
        if network is None:
            self.methods_banner.set_text("Select a network first.", "warning")
            return
        recovery = self.context.recovery
        summary = recovery.summary()
        self.context.last_recovery_summary = {"profiles": summary["total"]}

        profiles = recovery.find_profiles(network.ssid)
        readable = [p for p in profiles if p.can_recover]
        system_only = [p for p in profiles if p.owner_scope == "system"]

        def add_row(title: str, status: str, detail: str) -> None:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            colors = {
                "available": PALETTE.success,
                "unavailable": PALETTE.critical,
                "required": PALETTE.warning,
                "unknown": PALETTE.text_muted,
            }
            row_layout.addWidget(Pill(status.replace("_", " ").title(),
                                      colors.get(status, PALETTE.text_muted)))
            text = QLabel(f"<b>{title}</b><br><span style='color:{PALETTE.text_muted}'>{detail}</span>")
            text.setWordWrap(True)
            row_layout.addWidget(text, 1)
            self.methods_list.addWidget(row)
            self.methods_list.addWidget(divider())

        if readable:
            add_row(
                "Saved NetworkManager credential",
                "available",
                f"{len(readable)} saved profile(s) for '{network.ssid}' belong to your user "
                f"and contain a pre-shared key. Source: {readable[0].source}.",
            )
        elif profiles:
            add_row(
                "Saved NetworkManager credential",
                "unavailable",
                f"{len(profiles)} profile(s) match, but none exposes a readable PSK. "
                + " ".join(p.reason for p in profiles if p.reason),
            )
        else:
            add_row(
                "Saved NetworkManager credential",
                "unavailable",
                "No saved profile for this SSID exists for your user account.",
            )

        if system_only:
            add_row(
                "System-wide profile",
                "required",
                f"{len(system_only)} system profile(s) exist under "
                "/etc/NetworkManager/system-connections and are owned by root.",
            )
        else:
            add_row(
                "System-wide profile",
                "unknown",
                "No system-wide profile was found for this SSID.",
            )

        gateway, iface = self.context.router.default_gateway(
            self.adapter_combo.currentData() or self.context.active_interface
        )
        if gateway:
            add_row(
                "Router administration",
                "available",
                f"Default gateway {gateway} on {iface}. The router page can be opened to "
                "read or change the wireless password.",
            )
        else:
            add_row(
                "Router administration",
                "unavailable",
                "No default gateway is present; connect to the network first.",
            )

        self.methods_banner.set_text(
            "Method availability reflects this machine's actual state at this moment.",
            "info",
        )

    # -- step 5 ---------------------------------------------------------
    def _build_step_result(self) -> QWidget:
        page = Card("Step 5 — Recovery result", "")
        self.result_banner = Banner("No result yet.", "info")
        page.add(self.result_banner)
        self.result_status = QLabel("")
        self.result_status.setObjectName("SectionTitle")
        self.result_status.setWordWrap(True)
        page.add(self.result_status)

        secret_row = QHBoxLayout()
        self.secret_label = mono_label("")
        self.secret_label.setStyleSheet(
            f"background: {PALETTE.secondary}; border: 1px solid {PALETTE.border};"
            f" border-radius: 8px; padding: 10px; font-size: 15px;"
        )
        self.reveal_btn = button("Show password", "secondary", "eye", self._toggle_reveal)
        self.reveal_btn.setEnabled(False)
        self.copy_btn = button("Copy", "secondary", "copy", self._copy_secret)
        self.copy_btn.setEnabled(False)
        secret_row.addWidget(self.secret_label, 1)
        secret_row.addWidget(self.reveal_btn)
        secret_row.addWidget(self.copy_btn)
        page.add_layout(secret_row)

        self.guidance_label = QLabel("")
        self.guidance_label.setWordWrap(True)
        self.guidance_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        page.add(self.guidance_label)

        row = QHBoxLayout()
        row.addWidget(button("Try saved credential again", "secondary", "", self._run_recovery))
        row.addWidget(button("Open router page", "secondary", "", self._open_router))
        row.addWidget(button("Check router identity", "secondary", "", self._probe_router))
        row.addStretch(1)
        page.add_layout(row)
        page.body().addStretch(1)
        return page

    def _run_recovery(self) -> None:
        network = self._selected
        if network is None:
            return
        allow_system = False
        system = [
            p for p in self.context.recovery.find_profiles(network.ssid)
            if p.owner_scope == "system"
        ]
        if system:
            answer = QMessageBox.question(
                self,
                "System-wide profile",
                "A system-wide profile exists for this network. Reading it requires "
                "access to a root-owned file.\n\nAuthorise access to system profiles?",
                QMessageBox.Yes | QMessageBox.No,
            )
            allow_system = answer == QMessageBox.Yes
        result = self.context.recovery.recover(network.ssid, allow_system=allow_system)
        self._credential = result.secret
        self._revealed = False
        self.result_status.setText(result.status)
        if result.secret:
            self.context.recovery_count += 1
            self.context.record_operation(
                "recovery", f"Credential recovered for {network.ssid}", "ok", result.source
            )
            self.result_banner.set_text(result.message, "success")
            self.secret_label.setText("•" * len(result.secret))
            self.reveal_btn.setEnabled(True)
            self.copy_btn.setEnabled(True)
            self.reveal_btn.setText("Show password")
            self.guidance_label.setText(
                f"Source: {result.source}. The password is shown only in this window; "
                "WiFi Fortress does not log, store or transmit it."
            )
        else:
            self.context.record_operation(
                "recovery", f"Credential not recovered for {network.ssid}", "warn",
                "; ".join(result.reasons)[:200],
            )
            self.secret_label.setText("")
            self.reveal_btn.setEnabled(False)
            self.copy_btn.setEnabled(False)
            kind = "warning"
            self.result_banner.set_text(result.message, kind)
            reasons = "<br>".join(f"• {r}" for r in result.reasons) if result.reasons else ""
            guidance = self.context.router.guidance(
                self._router_info or self.context.router.probe(
                    self.context.router.default_gateway()[0]
                )
            )
            steps = "<br>".join(f"{i + 1}. {s}" for i, s in enumerate(guidance))
            self.guidance_label.setText(
                f"{reasons}<br><br><b>Router administration guidance</b><br>{steps}"
            )
        self.status_changed.emit(result.status)

    def _toggle_reveal(self) -> None:
        if not self._credential:
            return
        self._revealed = not self._revealed
        self.secret_label.setText(self._credential if self._revealed else "•" * len(self._credential))
        self.reveal_btn.setText("Hide password" if self._revealed else "Show password")

    def _copy_secret(self) -> None:
        if not self._credential:
            return
        QGuiApplication.clipboard().setText(self._credential)
        self.result_banner.set_text(
            "Password copied to the clipboard. Clear the clipboard when you are done.",
            "info",
        )

    def _open_router(self) -> None:
        url = self._router_info.admin_url if self._router_info else ""
        if not url:
            gateway, _ = self.context.router.default_gateway()
            url = f"http://{gateway}" if gateway else ""
        if not url:
            self.result_banner.set_text("No router address was found.", "warning")
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))

    def _probe_router(self) -> None:
        gateway, _ = self.context.router.default_gateway()
        if not gateway:
            self.result_banner.set_text("No default gateway found.", "warning")
            return
        self.result_banner.set_text("Probing the router…", "info")
        self._router_info = self.context.router.probe(gateway)
        info = self._router_info
        self.result_status.setText("Router identification")
        self.guidance_label.setText(
            f"<b>Gateway:</b> {info.gateway}<br>"
            f"<b>Open ports:</b> {', '.join(map(str, info.open_ports)) or 'none'}<br>"
            f"<b>Vendor:</b> {info.vendor or 'not identified'}<br>"
            f"<b>Page title:</b> {info.page_title or '—'}<br>"
            f"<b>Server:</b> {info.server_header or '—'}<br>"
            + "<br>".join(info.notes)
        )
        self.result_banner.set_text(
            "Router identified." if info.identified else "Router not identified.", 
            "success" if info.identified else "warning",
        )

    # -- navigation -----------------------------------------------------
    def _current(self) -> int:
        return self.stack.currentIndex()

    def _back(self) -> None:
        index = max(0, self._current() - 1)
        self._enter(index, forward=False)

    def _next(self) -> None:
        index = self._current()
        if index == 4:
            self._restart()
            return
        self._enter(index + 1, forward=True)

    def _restart(self) -> None:
        self._credential = None
        self._revealed = False
        self._selected = None
        self._router_info = None
        self.secret_label.setText("")
        self.reveal_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.guidance_label.setText("")
        self.result_status.setText("")
        self.result_banner.set_text("No result yet.", "info")
        self.stack.setCurrentIndex(0)
        self.steps.set_step(0)
        self._update_nav()

    def _enter(self, index: int, forward: bool) -> None:
        if forward:
            if index == 1:
                self._load_adapters()
                if self.adapter_combo.count() == 0:
                    return
            if index == 2:
                self._refresh_network_combo()
                if not self.context.networks:
                    self.scan_banner.set_text(
                        "No networks available. Run a scan first.", "warning"
                    )
            if index == 3:
                self._refresh_network_combo()
                self._evaluate_methods()
            if index == 4:
                self._run_recovery()
        self.stack.setCurrentIndex(index)
        self.steps.set_step(index)
        self._update_nav()

    def _update_nav(self) -> None:
        index = self._current()
        self.back_btn.setEnabled(index > 0)
        self.next_btn.setText("Start over" if index == 4 else "Continue")

    # -- external -------------------------------------------------------
    def start_for_network(self, network: WirelessNetwork | None = None) -> None:
        self._selected = network
        self._restart()
        self._load_adapters()
        if self.adapter_combo.count():
            self._enter(1, forward=True)
