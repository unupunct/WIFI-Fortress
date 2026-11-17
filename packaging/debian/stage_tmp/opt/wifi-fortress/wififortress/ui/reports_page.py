"""Reports page: generation, history, comparison, export and deletion."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
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
from wififortress.core.paths import open_in_file_manager, reports_dir
from wififortress.ui.theme import PALETTE
from wififortress.widgets.common import Banner, Card, button, divider, heading


class ReportsPage(QWidget):
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

        header = QHBoxLayout()
        header.addWidget(heading(
            "Reports",
            "PDF, HTML and JSON audit reports. Reports never contain passwords or secrets.",
        ), 1)
        header.addWidget(button("Open report folder", "secondary", "report", self._open_folder),
                          0, Qt.AlignTop)
        layout.addLayout(header)

        self.banner = Banner("Reports are stored under the application data directory.", "info")
        layout.addWidget(self.banner)

        generate = Card("Generate a report", "From the last audit in this session.")
        row = QHBoxLayout()
        self.audit_combo = QComboBox()
        self.audit_combo.setMinimumWidth(320)
        row.addWidget(self.audit_combo, 2)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF + HTML + JSON", "PDF only", "HTML only", "JSON only"])
        row.addWidget(self.format_combo, 1)
        row.addWidget(button("Generate", "primary", "report", self._generate))
        generate.add_layout(row)
        layout.addWidget(generate)

        history_card = Card("Report history", "Double-click a row to open the file.")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Created", "Title", "Format", "Size", "Score", "Path"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setMinimumHeight(240)
        self.table.doubleClicked.connect(self._open_selected)
        history_card.add(self.table)
        actions = QHBoxLayout()
        actions.addWidget(button("Open", "secondary", "", self._open_selected))
        actions.addWidget(button("Export a copy…", "secondary", "", self._export))
        actions.addWidget(button("Delete", "danger", "", self._delete))
        actions.addStretch(1)
        history_card.add_layout(actions)
        layout.addWidget(history_card, 1)

        compare_card = Card("Compare audits", "Pick two stored audits to see what changed.")
        crow = QHBoxLayout()
        self.compare_a = QComboBox()
        self.compare_b = QComboBox()
        crow.addWidget(self.compare_a, 1)
        crow.addWidget(self.compare_b, 1)
        crow.addWidget(button("Compare", "secondary", "", self._compare))
        compare_card.add_layout(crow)
        self.compare_label = QLabel("No comparison yet.")
        self.compare_label.setObjectName("Muted")
        self.compare_label.setWordWrap(True)
        compare_card.add(self.compare_label)
        layout.addWidget(compare_card)
        layout.addStretch(0)

        self.refresh()

    # -- data -----------------------------------------------------------
    def refresh(self) -> None:
        self._refresh_audits()
        self._refresh_history()

    def _refresh_audits(self) -> None:
        self.audit_combo.clear()
        self.compare_a.clear()
        self.compare_b.clear()
        if self.context.last_audit:
            self.audit_combo.addItem(
                f"Session audit · {self.context.last_audit.get('ssid')} · "
                f"score {self.context.last_audit.get('score')}",
                "session",
            )
        for row in self.context.db.audits(50):
            label = (
                f"{row['created_at'][:19].replace('T', ' ')} · {row['ssid']} · "
                f"score {row['score']} ({row['grade']})"
            )
            self.audit_combo.addItem(label, row["id"])
            self.compare_a.addItem(label, row["id"])
            self.compare_b.addItem(label, row["id"])
        if self.compare_b.count() > 1:
            self.compare_b.setCurrentIndex(1)

    def _refresh_history(self) -> None:
        rows = self.context.reports.history(200)
        self.table.setRowCount(0)
        for record in rows:
            index = self.table.rowCount()
            self.table.insertRow(index)
            values = [
                record["created_at"][:19].replace("T", " "),
                record["title"],
                record["format"].upper(),
                f"{record['size_bytes'] / 1024:.1f} KB",
                str(record["score"] if record["score"] is not None else "—"),
                record["path"],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, record["id"])
                self.table.setItem(index, col, item)
            if not Path(record["path"]).exists():
                self.table.item(index, 1).setForeground(Qt.gray)

    # -- actions --------------------------------------------------------
    def _selected_format(self) -> tuple[str, ...]:
        choice = self.format_combo.currentText()
        if choice.startswith("PDF only"):
            return ("pdf",)
        if choice.startswith("HTML only"):
            return ("html",)
        if choice.startswith("JSON only"):
            return ("json",)
        return ("pdf", "html", "json")

    def _generate(self) -> None:
        if self.audit_combo.count() == 0:
            self.banner.set_text("No audit available. Run a Security Audit first.", "warning")
            return
        payload = None
        data = self.audit_combo.currentData()
        if data == "session" and self.context.last_audit:
            payload = self.context.last_audit
        elif isinstance(data, int):
            payload = self.context.db.audit(data)
        if not payload:
            self.banner.set_text("The selected audit could not be loaded.", "error")
            return
        paths = self.context.reports.generate(payload, self._selected_format())
        produced = [p for p in (paths.pdf, paths.html, paths.json) if p]
        self._refresh_history()
        self.banner.set_text(
            f"Generated {len(produced)} file(s) in {reports_dir()}.", "success"
        )
        self.context.record_operation("report", "Report generated", "ok", str(reports_dir()))

    def generate_from_payload(self, payload: dict) -> None:
        paths = self.context.reports.generate(payload, self._selected_format())
        self._refresh_history()
        produced = [p for p in (paths.pdf, paths.html, paths.json) if p]
        self.banner.set_text(f"Generated {len(produced)} report file(s).", "success")

    def _current_record(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        record_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        for record in self.context.reports.history(500):
            if record["id"] == record_id:
                return record
        return None

    def _open_selected(self) -> None:
        record = self._current_record()
        if not record:
            return
        path = Path(record["path"])
        if not path.exists():
            self.banner.set_text(f"File no longer exists: {path}", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _export(self) -> None:
        record = self._current_record()
        if not record:
            return
        source = Path(record["path"])
        if not source.exists():
            self.banner.set_text("File no longer exists.", "warning")
            return
        target, _ = QFileDialog.getSaveFileName(self, "Export report", str(Path.home() / source.name))
        if not target:
            return
        try:
            Path(target).write_bytes(source.read_bytes())
            self.banner.set_text(f"Exported to {target}.", "success")
        except OSError as exc:
            self.banner.set_text(f"Export failed: {exc}", "error")

    def _delete(self) -> None:
        record = self._current_record()
        if not record:
            return
        answer = QMessageBox.question(
            self, "Delete report",
            f"Delete the file and its history entry?\n\n{record['path']}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.context.reports.delete(record["id"])
        self._refresh_history()
        self.banner.set_text("Report deleted.", "success")

    def _open_folder(self) -> None:
        open_in_file_manager(reports_dir())

    def _compare(self) -> None:
        a = self.context.db.audit(self.compare_a.currentData()) if self.compare_a.count() else None
        b = self.context.db.audit(self.compare_b.currentData()) if self.compare_b.count() else None
        if not a or not b:
            self.compare_label.setText("Select two stored audits to compare.")
            return
        result = self.context.reports.compare(a, b)
        lines = [
            f"Previous: {result['previous_score']} · Current: {result['current_score']} · "
            f"Change: {result['delta']:+d}",
            f"Resolved findings: {', '.join(result['resolved']) or 'none'}",
            f"New findings: {', '.join(result['new']) or 'none'}",
            f"Unchanged: {len(result['unchanged'])}",
        ]
        self.compare_label.setText("<br>".join(lines))
