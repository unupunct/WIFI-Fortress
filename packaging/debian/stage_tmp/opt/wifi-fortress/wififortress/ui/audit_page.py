"""Security Audit page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.models.entities import WirelessNetwork
from wififortress.services.audit_service import AuditContext, audit_summary
from wififortress.ui.theme import PALETTE, SEVERITY_COLORS
from wififortress.ui.workers import WorkerController
from wififortress.widgets.common import (
    Banner,
    Card,
    Pill,
    button,
    divider,
    heading,
    mono_label,
)


class AuditPage(QWidget):
    report_requested = Signal(dict)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._worker = WorkerController(self)
        self._worker.finished.connect(self._on_audit_finished)
        self._worker.failed.connect(self._on_audit_failed)
        self._result: dict | None = None
        self._password_for_test: str = ""

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
            "Security Audit",
            "Defensive examination of one network using evidence from the scan, the "
            "adapter and the router. Unknown data is reported as unknown and never scored.",
        ), 1)
        self.report_btn = button("Generate report", "secondary", "report", self._emit_report)
        self.report_btn.setEnabled(False)
        header.addWidget(self.report_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        controls = Card("Audit target", "")
        row = QHBoxLayout()
        self.network_combo = QComboBox()
        self.network_combo.setMinimumWidth(320)
        self.network_combo.currentIndexChanged.connect(self._on_target_changed)
        row.addWidget(QLabel("Network"))
        row.addWidget(self.network_combo, 2)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(
            "Optional: test your own Wi-Fi password locally (never stored)"
        )
        self.password_input.setEchoMode(QLineEdit.Password)
        row.addWidget(self.password_input, 2)
        self.run_btn = button("Run audit", "primary", "shield", self.run_audit)
        row.addWidget(self.run_btn)
        controls.add_layout(row)
        layout.addWidget(controls)

        self.banner = Banner("Select a network and run the audit.", "info")
        layout.addWidget(self.banner)

        self.summary_card = Card("Result", "")
        summary_row = QHBoxLayout()
        self.score_label = QLabel("—")
        self.score_label.setObjectName("StatValue")
        self.score_label.setStyleSheet("font-size: 44px;")
        self.grade_label = QLabel("")
        self.grade_label.setObjectName("Muted")
        score_col = QVBoxLayout()
        score_col.addWidget(self.score_label)
        score_col.addWidget(self.grade_label)
        summary_row.addLayout(score_col)
        self.counts_layout = QHBoxLayout()
        self.count_labels: dict[str, QLabel] = {}
        for severity in ("Critical", "High", "Medium", "Low", "Informational", "Unknown"):
            box = QVBoxLayout()
            value = QLabel("0")
            value.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {SEVERITY_COLORS[severity]};")
            caption = QLabel(severity)
            caption.setObjectName("StatLabel")
            box.addWidget(value)
            box.addWidget(caption)
            wrapper = QWidget()
            wrapper.setLayout(box)
            summary_row.addWidget(wrapper)
            self.count_labels[severity] = value
        summary_row.addStretch(1)
        self.summary_card.add_layout(summary_row)
        layout.addWidget(self.summary_card)

        splitter = QSplitter(Qt.Horizontal)
        findings_wrap = Card("Findings", "Ordered by severity.")
        self.findings_layout = QVBoxLayout()
        self.findings_layout.setSpacing(10)
        findings_wrap.add_layout(self.findings_layout)
        findings_wrap.body().addStretch(1)
        splitter.addWidget(findings_wrap)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(12)
        self.checklist_card = Card("Improvement checklist", "")
        self.checklist_label = QLabel("No audit yet.")
        self.checklist_label.setWordWrap(True)
        self.checklist_label.setObjectName("Muted")
        self.checklist_card.add(self.checklist_label)
        side_layout.addWidget(self.checklist_card)
        self.breakdown_card = Card("Score breakdown", "Documented weights per finding.")
        self.breakdown_label = QLabel("No audit yet.")
        self.breakdown_label.setWordWrap(True)
        self.breakdown_label.setObjectName("Muted")
        self.breakdown_card.add(self.breakdown_label)
        side_layout.addWidget(self.breakdown_card)
        side_layout.addStretch(1)
        splitter.addWidget(side)
        splitter.setSizes([760, 320])
        layout.addWidget(splitter, 1)
        layout.addStretch(1)

    # -- target selection ----------------------------------------------
    def refresh_targets(self, preselect: str | None = None) -> None:
        self.network_combo.blockSignals(True)
        self.network_combo.clear()
        for network in self.context.networks:
            self.network_combo.addItem(
                f"{network.display_ssid} · {network.security.value} · {network.bssid}",
                network.bssid,
            )
        self.network_combo.blockSignals(False)
        if preselect:
            index = self.network_combo.findData(preselect)
            if index >= 0:
                self.network_combo.setCurrentIndex(index)
        self._on_target_changed()

    def _on_target_changed(self) -> None:
        if not self.context.networks:
            self.banner.set_text(
                "No networks available. Scan from Wireless Networks first, or open the "
                "audit from a network row.", "warning"
            )
        else:
            self.banner.set_text("Ready to audit the selected network.", "info")

    def _target(self) -> WirelessNetwork | None:
        bssid = self.network_combo.currentData()
        return next((n for n in self.context.networks if n.bssid == bssid), None)

    # -- audit ----------------------------------------------------------
    def run_audit(self) -> None:
        if self._worker.running:
            return
        network = self._target()
        if network is None:
            self.banner.set_text("Select a network first.", "warning")
            return
        password = self.password_input.text()
        self._password_for_test = password
        self.run_btn.setEnabled(False)
        self.banner.set_text("Running audit…", "info")
        self._worker.start(
            self._perform, network, password,
        )

    def _perform(self, network: WirelessNetwork, password: str, token=None):
        neighbours = self.context.networks
        router: dict = {}
        gateway, _ = self.context.router.default_gateway(self.context.active_interface)
        if gateway:
            info = self.context.router.probe(gateway)
            router = {
                "gateway": info.gateway,
                "open_ports": info.open_ports,
                "vendor": info.vendor,
                "page_title": info.page_title,
                "server_header": info.server_header,
                "notes": info.notes,
            }
        assessment = None
        if password:
            assessment = self.context.password.assess(password).to_dict()
            # Include how long an offline attack on this passphrase would need,
            # so the audit states the real risk rather than only structural score.
            try:
                resistance = self.context.password.attack_resistance(password)
                assessment["attack_resistance"] = resistance.to_dict()
                assessment["crack_time_estimate"] = resistance.estimates.get(
                    "gpu_flagship", assessment.get("crack_time_estimate", "unknown")
                )
            except ValueError:
                pass
        context = AuditContext(
            network=network,
            adapter=self.context.active_adapter,
            neighbours=neighbours,
            router=router,
            user_password_assessment=assessment,
            interface=self.context.active_interface,
        )
        return self.context.audit.audit(context)

    def _on_audit_finished(self, result) -> None:
        self.run_btn.setEnabled(True)
        self.password_input.clear()
        self._result = result.to_dict()
        self.context.last_audit = self._result
        self.context.last_audit_at = result.created_at
        self.context.audit_count += 1
        if self.context.settings.get("audit_store_history", True):
            self.context.db.save_audit(self._result)
        self.context.record_operation(
            "audit", f"Audit of {result.ssid}: score {result.score}", "ok"
        )
        self.banner.set_text(
            "Audit complete. " + audit_summary(result), "success"
        )
        self.report_btn.setEnabled(True)
        self._render(result)

    def _on_audit_failed(self, message: str, detail: str) -> None:
        self.run_btn.setEnabled(True)
        self.password_input.clear()
        self.banner.set_text(f"Audit failed: {message}", "error")

    def _render(self, result) -> None:
        color = (
            PALETTE.success if result.score >= 75
            else PALETTE.warning if result.score >= 50
            else PALETTE.critical
        )
        self.score_label.setText(f"{result.score}")
        self.score_label.setStyleSheet(f"font-size: 44px; color: {color};")
        self.grade_label.setText(f"/ 100 · grade {result.grade}")
        counts = result.severity_counts
        for severity, label in self.count_labels.items():
            key = severity.lower()
            label.setText(str(counts.get(key, 0)))

        while self.findings_layout.count():
            item = self.findings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for finding in result.findings:
            self.findings_layout.addWidget(self._finding_widget(finding))

        self.checklist_label.setText(
            "<br>".join(f"☐ {item}" for item in result.checklist)
        )
        breakdown = result.score_breakdown
        if breakdown:
            self.breakdown_label.setText(
                "<br>".join(
                    f"−{item['points']} {item['title']} ({item['severity']})"
                    for item in breakdown
                )
                + f"<br><br>Score = 100 − {sum(i['points'] for i in breakdown)} = {result.score}"
            )
        else:
            self.breakdown_label.setText("No deductions; the score is 100.")

    def _finding_widget(self, finding) -> QWidget:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(Pill(finding.severity.value, SEVERITY_COLORS[finding.severity.value]))
        title = QLabel(finding.title)
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        verify = QLabel(finding.verification.value)
        verify.setObjectName("Dim")
        header.addWidget(verify)
        card.add_layout(header)
        advanced = self.context.settings.is_advanced
        for label, text in (
            ("Evidence", finding.evidence),
            ("Explanation", finding.explanation),
            ("Impact", finding.impact),
            ("Correction", finding.recommendation),
        ):
            if not advanced and label == "Explanation":
                continue
            line = QLabel(f"<b>{label}:</b> {text}")
            line.setWordWrap(True)
            line.setObjectName("Muted")
            line.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card.add(line)
        return card

    def _emit_report(self) -> None:
        if self._result:
            self.report_requested.emit(self._result)

    # -- external -------------------------------------------------------
    def start_for_network(self, network: WirelessNetwork) -> None:
        self.refresh_targets(network.bssid)
        self.run_audit()
