"""Dictionary Manager page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
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
from wififortress.services.wordlist_catalog import (
    CATEGORIES,
    SOURCES,
    WordlistCatalogService,
)
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
        self._worker.finished.connect(self._on_task_finished)
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

        # -- public word lists -----------------------------------------
        self.catalog = WordlistCatalogService(self.context.dictionaries)
        catalog_card = Card(
            "Public word lists",
            f"{len(SOURCES)} verified public lists. Download one to disk, then import it "
            "as a dictionary. Nothing is fetched until you press Download.",
        )
        filter_row = QHBoxLayout()
        self.category_filter = QComboBox()
        self.category_filter.addItem("All categories")
        for category in CATEGORIES:
            self.category_filter.addItem(category)
        self.category_filter.currentTextChanged.connect(lambda _=None: self._refresh_catalog())
        filter_row.addWidget(self.category_filter)
        self.only_wifi = QCheckBox("Wi-Fi focused only")
        self.only_wifi.stateChanged.connect(lambda _=None: self._refresh_catalog())
        filter_row.addWidget(self.only_wifi)
        filter_row.addStretch(1)
        self.catalog_status = QLabel("")
        self.catalog_status.setObjectName("Muted")
        filter_row.addWidget(self.catalog_status)
        catalog_card.add_layout(filter_row)

        self.catalog_list = QTableWidget(0, 4)
        self.catalog_list.setHorizontalHeaderLabels(["List", "Category", "Licence", "Status"])
        self.catalog_list.setSelectionBehavior(QTableWidget.SelectRows)
        self.catalog_list.setSelectionMode(QTableWidget.SingleSelection)
        self.catalog_list.setEditTriggers(QTableWidget.NoEditTriggers)
        self.catalog_list.verticalHeader().setVisible(False)
        self.catalog_list.horizontalHeader().setStretchLastSection(False)
        header = self.catalog_list.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.catalog_list.setMinimumHeight(240)
        self.catalog_list.itemSelectionChanged.connect(self._on_catalog_selected)
        self.catalog_list.cellDoubleClicked.connect(
            lambda row, _col: self._open_catalog_page(row)
        )
        catalog_card.add(self.catalog_list, 1)

        self.catalog_note = QLabel(
            "Select a list to see what it is. Licences belong to the upstream project; "
            "WiFi Fortress records each file's origin and SHA-256 and never relicenses it."
        )
        self.catalog_note.setObjectName("Muted")
        self.catalog_note.setWordWrap(True)
        catalog_card.add(self.catalog_note)

        catalog_actions = QHBoxLayout()
        catalog_actions.addWidget(
            button("Download selected", "secondary", "", self._download_selected)
        )
        catalog_actions.addWidget(
            button("Download + import", "primary", "", self._download_import_selected)
        )
        catalog_actions.addWidget(
            button("Import downloaded", "secondary", "", self._import_downloaded)
        )
        catalog_actions.addWidget(button("Open page", "ghost", "", self._open_selected_page))
        catalog_actions.addWidget(button("Clear downloads", "ghost", "", self._clear_downloads))
        catalog_actions.addStretch(1)
        catalog_card.add_layout(catalog_actions)
        layout.addWidget(catalog_card)
        self._catalog_rows: list = []

        manage = QHBoxLayout()
        manage.addWidget(button("Import dictionary…", "secondary", "", self._import))
        manage.addWidget(button("Remove imported", "danger", "", self._remove))
        manage.addWidget(button("Restore bundled", "secondary", "", self._restore))
        manage.addWidget(button("Open folder", "ghost", "", self._open_folder))
        manage.addStretch(1)
        layout.addLayout(manage)
        layout.addStretch(0)
        self.refresh()
        self._refresh_catalog()

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

    def _on_task_finished(self, result) -> None:
        """One entry point for both task kinds the page runs."""
        from wififortress.services.wordlist_catalog import DownloadResult

        if isinstance(result, DownloadResult):
            self._on_downloaded(result)
        else:
            self._on_verified(result)

    def _on_downloaded(self, result) -> None:
        self._refresh_catalog()
        if not result.ok:
            self.banner.set_text(f"{result.source.name}: {result.message}", "critical")
            return
        if result.entry_count:
            self.refresh()
            self.context.record_operation(
                "dictionary", f"Imported {result.source.name}", "ok",
                f"{result.entry_count} entries",
            )
        self.banner.set_text(f"{result.source.name}: {result.message}", "success")

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

    # -- public word list catalogue -------------------------------------
    def _refresh_catalog(self) -> None:
        category = self.category_filter.currentText()
        wifi_only = self.only_wifi.isChecked()
        rows = [
            s for s in SOURCES
            if (category == "All categories" or s.category == category)
            and (not wifi_only or s.wifi_focused)
        ]
        self._catalog_rows = rows
        self.catalog_list.setRowCount(len(rows))
        for index, source in enumerate(rows):
            downloaded = self.catalog.existing(source)
            if downloaded is not None:
                status = f"Downloaded ({downloaded.stat().st_size / 1024:.0f} KB)"
            elif source.is_file:
                status = "Available"
            else:
                status = "Project page"
            values = [source.name, source.category, source.licence, status]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(source.note or source.name)
                self.catalog_list.setItem(index, column, item)
        if not rows:
            self.catalog_note.setText("No list matches this filter.")
        else:
            self.catalog_note.setText(
                "Select a list to see what it is. Licences belong to the upstream "
                "project; WiFi Fortress records each file's origin and SHA-256."
            )
        size = self.catalog.cache_size()
        self.catalog_status.setText(
            f"{len(rows)} of {len(SOURCES)} shown · {size / 1_048_576:.1f} MB on disk"
        )

    def _selected_source(self):
        rows = self.catalog_list.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self._catalog_rows):
            return self._catalog_rows[index]
        return None

    def _on_catalog_selected(self) -> None:
        source = self._selected_source()
        if source is None:
            self.catalog_note.setText("Select a list to see what it is.")
            return
        kind = "single file" if source.is_file else "project page"
        self.catalog_note.setText(
            f"{source.name} ({kind}) — {source.note or 'No description.'} "
            f"Licence: {source.licence}. Source: {source.homepage}"
        )

    def _open_catalog_page(self, row: int) -> None:
        if 0 <= row < len(self._catalog_rows):
            self._open_url(self._catalog_rows[row].homepage)

    def _open_selected_page(self) -> None:
        source = self._selected_source()
        if source is not None:
            self._open_url(source.homepage)

    @staticmethod
    def _open_url(url: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))

    def _download_selected(self) -> None:
        self._download(import_after=False)

    def _download_import_selected(self) -> None:
        self._download(import_after=True)

    def _download(self, import_after: bool) -> None:
        source = self._selected_source()
        if source is None:
            self.banner.set_text("Select a word list first.", "warning")
            return
        if not source.is_file:
            self.banner.set_text(
                f"{source.name} is a project page, not a single file. Open it to choose a list.",
                "warning",
            )
            self._open_url(source.homepage)
            return
        if self._worker.running:
            return
        self.banner.set_text(f"Downloading {source.name}…", "info")
        self._download_import = import_after
        self._worker.start(self._download_task, source)

    def _download_task(self, source, token=None):
        def progress(written: int, total: int) -> None:
            if total:
                self.banner.set_text(
                    f"Downloading {source.name}… {written / 1048576:.1f} of "
                    f"{total / 1048576:.1f} MB", "info",
                )
            else:
                self.banner.set_text(
                    f"Downloading {source.name}… {written / 1048576:.1f} MB", "info"
                )

        if self._download_import:
            return self.catalog.download_and_import(source, progress=progress, token=token)
        return self.catalog.download(source, progress=progress, token=token)

    def _import_downloaded(self) -> None:
        source = self._selected_source()
        if source is None:
            self.banner.set_text("Select a word list first.", "warning")
            return
        path = self.catalog.existing(source)
        if path is None:
            self.banner.set_text(
                f"{source.name} has not been downloaded yet — use Download first.", "warning"
            )
            return
        try:
            info = self.context.dictionaries.import_file(path, name=source.name)
        except (OSError, ValueError) as exc:
            self.banner.set_text(f"Import failed: {exc}", "critical")
            return
        self.refresh()
        self._refresh_catalog()
        self.context.record_operation(
            "dictionary", f"Imported {source.name}", "ok", f"{info.entry_count} entries"
        )
        self.banner.set_text(
            f"Imported {source.name}: {info.entry_count:,} entries.", "success"
        )

    def _clear_downloads(self) -> None:
        removed = self.catalog.clear_cache()
        self._refresh_catalog()
        self.banner.set_text(
            f"Removed {removed} downloaded file(s) from the cache. Imported dictionaries stay.",
            "info",
        )

    def _open_folder(self) -> None:
        from wififortress.core.paths import dictionaries_dir

        open_in_file_manager(dictionaries_dir())
