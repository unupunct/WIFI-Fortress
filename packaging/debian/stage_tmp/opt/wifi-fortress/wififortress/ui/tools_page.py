"""Wireless Tools page: Parrot OS tool detection and safe operations."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
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


class ToolsPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._worker = WorkerController(self)
        self._worker.finished.connect(self._on_scanned)
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
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(heading(
            "Wireless Tools",
            "Utilities detected on this Parrot OS system. Only documented interfaces are "
            "used, always with fixed argument lists.",
        ), 1)
        self.scan_btn = button("Detect tools", "primary", "refresh", self.scan_tools)
        header.addWidget(self.scan_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        self.banner = Banner("Tool detection has not run yet.", "info")
        layout.addWidget(self.banner)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(12)
        layout.addLayout(self.list_layout)
        layout.addStretch(1)

    def scan_tools(self) -> None:
        if self._worker.running:
            return
        self.scan_btn.setEnabled(False)
        self.banner.set_text("Detecting tools and versions…", "info")
        self._worker.start(self.context.tools.discover_all)

    def _on_scanned(self, infos) -> None:
        self.scan_btn.setEnabled(True)
        self.context.tools_cache = infos
        installed = sum(1 for i in infos if i.installed)
        self.banner.set_text(
            f"{installed} of {len(infos)} tools installed. Restricted tools are listed "
            "for transparency and are never launched.",
            "success" if installed else "warning",
        )
        self._render(infos)

    def _on_failed(self, message: str, detail: str) -> None:
        self.scan_btn.setEnabled(True)
        self.banner.set_text(f"Tool detection failed: {message}", "error")

    def _tshark(self) -> None:
        """Run a fixed tshark summary on a capture file the user selects."""
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Select a capture file", str(Path.home()), "Capture files (*.pcap *.pcapng);;All files (*)"
        )
        if not path:
            return
        try:
            output = self.context.tools.tshark_summary(Path(path))
        except Exception as exc:
            self.banner.set_text(f"tshark failed: {exc}", "error")
            return
        self.context.record_operation("tools", "tshark summary", "ok", path)
        dialog = Card("tshark protocol hierarchy", path)
        label = QLabel(output[:6000])
        label.setObjectName("Mono")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dialog.add(label)
        self.list_layout.insertWidget(0, dialog)
        self.banner.set_text("Capture summarised (read-only, no packets modified).", "success")

    def _render(self, infos) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        advanced = self.context.settings.is_advanced
        for info in infos:
            card = Card()
            header = QHBoxLayout()
            title = QLabel(info.name)
            title.setObjectName("SectionTitle")
            header.addWidget(title)
            header.addStretch(1)
            status_color = (
                PALETTE.success if info.installed and not info.missing_dependencies
                else PALETTE.warning if info.installed
                else PALETTE.text_dim
            )
            header.addWidget(Pill(info.status_label, status_color))
            if info.restricted:
                header.addWidget(Pill("Restricted", PALETTE.warning))
            card.add_layout(header)

            desc = QLabel(info.description)
            desc.setObjectName("Muted")
            desc.setWordWrap(True)
            card.add(desc)
            purpose = QLabel(f"<b>Use in WiFi Fortress:</b> {info.purpose}")
            purpose.setWordWrap(True)
            card.add(purpose)

            meta_bits = []
            if info.version:
                meta_bits.append(f"version {info.version}")
            if info.path:
                meta_bits.append(info.path)
            meta_bits.append(f"package {info.package}")
            meta = QLabel(" · ".join(meta_bits))
            meta.setObjectName("Dim")
            meta.setWordWrap(True)
            card.add(meta)

            if info.missing_dependencies:
                warn = QLabel("Missing dependencies: " + ", ".join(info.missing_dependencies))
                warn.setStyleSheet(f"color: {PALETTE.warning};")
                warn.setWordWrap(True)
                card.add(warn)
            if not info.installed and info.install_hint:
                hint = QLabel(f"Install with: {info.install_hint}")
                hint.setObjectName("Mono")
                hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card.add(hint)
            if info.restriction_note:
                note = QLabel(info.restriction_note)
                note.setStyleSheet(f"color: {PALETTE.warning};")
                note.setWordWrap(True)
                card.add(note)
            if advanced and info.diagnostics:
                diag = QLabel(info.diagnostics)
                diag.setObjectName("Dim")
                diag.setWordWrap(True)
                card.add(diag)
            if advanced and info.capabilities:
                card.add(QLabel("Capabilities: " + ", ".join(info.capabilities)))

            spec = self.context.tools.spec(info.key)
            if spec and spec.related_binaries:
                binaries = []
                for binary in spec.related_binaries:
                    present, path = self.context.tools.binary_status(binary)
                    binaries.append(f"{binary} ({'installed' if present else 'missing'})")
                row = QLabel("Binaries: " + ", ".join(binaries))
                row.setObjectName("Dim")
                row.setWordWrap(True)
                card.add(row)
            if info.installed and info.key == "tshark":
                card.add(button("Summarise a capture file...", "secondary", "", self._tshark))
            self.list_layout.addWidget(card)

        missing = [i for i in infos if not i.installed]
        if missing:
            install_card = Card("Installation guidance", "Install everything with one command.")
            cmd = "sudo apt update && sudo apt install " + " ".join(sorted({i.package for i in missing}))
            label = QLabel(cmd)
            label.setObjectName("Mono")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            install_card.add(label)
            self.list_layout.addWidget(install_card)
