"""Dictionary Manager page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.core.paths import open_in_file_manager
from wififortress.ui.theme import PALETTE
from wififortress.ui.workers import WorkerController
from wififortress.widgets.common import Banner, Card, Pill, button, divider, heading


class DictionaryPage(QWidget):
    dictionaries_changed = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._worker = WorkerController(self)
        self._worker.finished.connect(self._on_verified)
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
            "Dictionary Manager",
            "Ten bundled resources for local password-quality assessment, plus your own imports.",
        ), 1)
        header.addWidget(button("Verify all", "primary", "check", self._verify_all), 0, Qt.AlignTop)
        layout.addLayout(header)

        self.banner = Banner(
            "Dictionaries are used only for local assessment and explicit comparisons - "
            "never for automated Wi-Fi authentication.", "info",
        )
        layout.addWidget(self.banner)

        splitter = QSplitter(Qt.Horizontal)
        list_card = Card("Resources", "Enable, reorder and inspect.")
        self.list = QListWidget()
        self.list.setMinimumHeight(260)
        self.list.currentRowChanged.connect(self._on_selected)
        list_card.add(self.list, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("Up", "ghost", on_click=lambda: self._move(-1)))
        actions.addWidget(button("Down", "ghost", on_click=lambda: self._move(1)))
        actions.addWidget(button("Enable / disable", "secondary", on_click=self._toggle))
        list_card.add_layout(actions)
        splitter.addWidget(list_card)

        self.detail_card = Card("Details", "")
        self.detail_label = QLabel("Select a dictionary.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setObjectName("Muted")
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_card.add(self.detail_label)
        self.detail_card.add(divider())
        self.preview_label = QLabel("")
        self.preview_label.setObjectName("Mono")
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_card.add(self.preview_label)
        self.detail_card.body().addStretch(1)
        splitter.addWidget(self.detail_card)
        splitter.setSizes([420, 620])
        layout.addWidget(splitter, 1)

        manage = QHBoxLayout()
        manage.addWidget(button("Import dictionary…", "secondary", "", self._import))
        manage.addWidget(button("Remove imported", "danger", "", self._remove))
        manage.addWidget(button("Restore bundled", "secondary", "", self._restore))
        manage.addWidget(button("Open folder", "ghost", "", self._open_folder))
        manage.addStretch(1)
        layout.addLayout(manage)
        layout.addStretch(0)
        self.refresh()

    # -- rendering ------------------------------------------------------
    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for info in self.context.dictionaries.all():
            state = "enabled" if info.enabled else "disabled"
            if not info.exists:
                state = "missing"
            self.list.addItem(
                f"{info.name}  ·  {info.entry_count:,} entries  ·  {info.size_label}  ·  {state}"
            )
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(0)
            self._on_selected(0)

    def _current_info(self):
        row = self.list.currentRow()
        infos = self.context.dictionaries.all()
        if 0 <= row < len(infos):
            return infos[row]
        return None

    def _on_selected(self, row: int) -> None:
        info = self._current_info()
        if info is None:
            return
        details = [
            f"<b>{info.name}</b>",
            f"{info.description}",
            f"<i>{info.purpose}</i>",
            f"Source: {info.source} · License: {info.license}",
            f"Provenance: {info.provenance}",
            f"Path: {info.path}",
            f"Entries: {info.entry_count:,} · Size: {info.size_label}",
            f"Enabled: {'yes' if info.enabled else 'no'}",
        ]
        if info.sha256:
            details.append(f"SHA-256: {info.sha256[:32]}…")
        if info.integrity_ok is not None:
            details.append(f"Integrity: {'verified' if info.integrity_ok else 'problem'}")
        if info.problem:
            details.append(f"<span style='color:{PALETTE.warning}'>Note: {info.problem}</span>")
        self.detail_label.setText("<br>".join(details))
        entries = self.context.dictionaries.preview(info.dict_id, 24)
        self.preview_label.setText(
            "<b>Preview (first 24 entries)</b><br>" + ", ".join(entries) if entries else "No preview available."
        )

    # -- actions --------------------------------------------------------
    def _toggle(self) -> None:
        info = self._current_info()
        if info is None:
            return
        self.context.dictionaries.set_enabled(info.dict_id, not info.enabled)
        self.context.load_dictionaries_into_assessment()
        self.refresh()

    def _move(self, delta: int) -> None:
        info = self._current_info()
        if info is None:
            return
        self.context.dictionaries.move(info.dict_id, delta)
        self.refresh()

    def _verify_all(self) -> None:
        if self._worker.running:
            return
        self.banner.set_text("Verifying dictionaries…", "info")
        self._worker.start(self.context.dictionaries.verify_all)

    def _on_verified(self, reports) -> None:
        problems = [r for r in reports if not r.ok]
        self.context.load_dictionaries_into_assessment()
        self.refresh()
        if problems:
            self.banner.set_text(
                f"{len(reports)} dictionaries checked, {len(problems)} with problems: "
                + "; ".join(f"{r.dict_id}: {', '.join(r.problems)}" for r in problems),
                "warning",
            )
        else:
            total = sum(r.entry_count for r in reports)
            self.banner.set_text(
                f"All {len(reports)} dictionaries verified ({total:,} entries, UTF-8, "
                "duplicates counted).", "success",
            )

    def _on_failed(self, message: str, detail: str) -> None:
        self.banner.set_text(f"Verification failed: {message}", "error")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import dictionary", str(Path.home()), "Text files (*.txt *.lst *.dict);;All files (*)"
        )
        if not path:
            return
        try:
            info = self.context.dictionaries.import_file(Path(path))
        except Exception as exc:
            self.banner.set_text(f"Import failed: {exc}", "error")
            return
        self.context.load_dictionaries_into_assessment()
        self.banner.set_text(
            f"Imported '{info.name}' with {info.entry_count:,} entries "
            f"({info.duplicate_entries} duplicates removed from the count).", "success",
        )
        self.dictionaries_changed.emit()
        self.refresh()

    def _remove(self) -> None:
        info = self._current_info()
        if info is None or info.is_bundled:
            self.banner.set_text("Bundled dictionaries cannot be removed; disable them instead.", "warning")
            return
        if self.context.dictionaries.remove(info.dict_id):
            self.context.load_dictionaries_into_assessment()
            self.banner.set_text(f"Removed '{info.name}'.", "success")
            self.dictionaries_changed.emit()
            self.refresh()

    def _restore(self) -> None:
        restored = self.context.dictionaries.restore_bundled()
        self.context.load_dictionaries_into_assessment()
        self.banner.set_text(
            f"Restored {len(restored)} bundled dictionaries from the installation.", "success"
        )
        self.refresh()

    def _open_folder(self) -> None:
        from wififortress.core.paths import dictionaries_dir

        open_in_file_manager(dictionaries_dir())
