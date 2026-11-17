"""Connection Diagnostics page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.models.entities import DiagnosticCheck
from wififortress.ui.theme import PALETTE, STATUS_COLORS
from wififortress.ui.workers import WorkerController
from wififortress.widgets.common import Banner, Card, Pill, button, divider, heading


class DiagnosticsPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._worker = WorkerController(self)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._rows: dict[str, tuple[QLabel, QLabel, QLabel]] = {}

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

        header = QHBoxLayout()
        header.addWidget(heading(
            "Connection Diagnostics",
            "Interface, addressing, gateway, DNS, internet reachability, latency and loss.",
        ), 1)
        self.interface_combo = QComboBox()
        self.interface_combo.setMinimumWidth(140)
        header.addWidget(self.interface_combo, 0, Qt.AlignTop)
        self.run_btn = button("Run diagnostics", "primary", "pulse", self.run_checks)
        header.addWidget(self.run_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        self.banner = Banner("Diagnostics have not run yet.", "info")
        layout.addWidget(self.banner)

        self.summary_card = Card("Summary", "")
        self.summary_label = QLabel("—")
        self.summary_label.setObjectName("Muted")
        self.summary_label.setWordWrap(True)
        self.summary_card.add(self.summary_label)
        layout.addWidget(self.summary_card)

        self.checks_card = Card("Checks", "")
        self.checks_layout = QVBoxLayout()
        self.checks_layout.setSpacing(10)
        self.checks_card.add_layout(self.checks_layout)
        self.checks_card.body().addStretch(1)
        layout.addWidget(self.checks_card, 1)
        layout.addStretch(1)
        self.refresh_interfaces()

    def refresh_interfaces(self) -> None:
        interfaces = [a.interface for a in self.context.adapter_list]
        self.interface_combo.clear()
        self.interface_combo.addItems(interfaces or ["no adapter"])
        if self.context.active_interface in interfaces:
            self.interface_combo.setCurrentText(self.context.active_interface)

    def run_checks(self) -> None:
        if self._worker.running:
            return
        interface = self.interface_combo.currentText()
        if not interface or interface == "no adapter":
            self.banner.set_text("No adapter selected. Refresh the Adapter Manager first.", "warning")
            return
        self.run_btn.setEnabled(False)
        self.banner.set_text("Running diagnostics…", "info")
        self._clear_rows()
        self._worker.start(self.context.diagnostics.run_all, interface)

    def _clear_rows(self) -> None:
        while self.checks_layout.count():
            item = self.checks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

    def _on_finished(self, report) -> None:
        self.run_btn.setEnabled(True)
        self.context.record_operation(
            "diagnostics", f"Diagnostics on {report.interface}", report.overall
        )
        kind = {"ok": "success", "warn": "warning", "fail": "error"}.get(report.overall, "info")
        self.banner.set_text(
            f"{report.passed} passed, {report.warnings} warnings, {report.failed} failed.",
            kind,
        )
        self.summary_label.setText(
            f"Interface {report.interface} · overall {report.overall.upper()} · "
            f"{report.passed}/{len(report.checks)} checks passed"
        )
        for check in report.checks:
            self._add_check(check)

    def _on_failed(self, message: str, detail: str) -> None:
        self.run_btn.setEnabled(True)
        self.banner.set_text(f"Diagnostics failed: {message}", "error")

    def _add_check(self, check: DiagnosticCheck) -> None:
        wrapper = QWidget()
        row = QVBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        top = QHBoxLayout()
        pill = Pill(check.status.upper(), STATUS_COLORS.get(check.status, PALETTE.text_muted))
        top.addWidget(pill)
        label = QLabel(check.label)
        label.setObjectName("SectionTitle")
        top.addWidget(label, 1)
        row.addLayout(top)
        detail = QLabel(check.detail)
        detail.setWordWrap(True)
        detail.setObjectName("Muted")
        detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(detail)
        if check.fix:
            fix = QLabel(f"Suggested fix: {check.fix}")
            fix.setWordWrap(True)
            fix.setStyleSheet(f"color: {PALETTE.warning};")
            fix.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(fix)
        self.checks_layout.addWidget(wrapper)
        self.checks_layout.addWidget(divider())
