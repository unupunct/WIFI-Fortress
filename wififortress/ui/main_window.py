"""Main window: sidebar navigation, page stack and status bar."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from wififortress import APP_NAME, APP_VERSION
from wififortress.app.context import AppContext
from wififortress.ui.adapters_page import AdapterPage
from wififortress.ui.audit_page import AuditPage
from wififortress.ui.dashboard_page import DashboardPage
from wififortress.ui.diagnostics_page import DiagnosticsPage
from wififortress.ui.dictionaries_page import DictionaryPage
from wififortress.ui.hardening_page import HardeningPage
from wififortress.ui.environment_page import EnvironmentPage
from wififortress.ui.networks_page import NetworksPage
from wififortress.ui.password_page import PasswordPage
from wififortress.ui.recovery_page import RecoveryPage
from wififortress.ui.reports_page import ReportsPage
from wififortress.ui.settings_page import SettingsPage
from wififortress.ui.theme import PALETTE
from wififortress.widgets.common import Pill, app_icon, make_icon

NAV_ITEMS = [
    ("dashboard", "Dashboard", "dashboard"),
    ("networks", "Wireless Networks", "wifi"),
    ("recovery", "Wi-Fi Recovery", "key"),
    ("audit", "Security Audit", "shield"),
    ("tools", "Wireless Tools", "tools"),
    ("adapters", "Adapter Manager", "adapter"),
    ("hardening", "Passphrase Hardening", "shield"),
    ("password", "Password Laboratory", "lock"),
    ("dictionaries", "Dictionary Manager", "book"),
    ("diagnostics", "Diagnostics", "pulse"),
    ("reports", "Reports", "report"),
    ("settings", "Settings", "settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1120, 720)
        if context.settings.get("remember_window", True):
            self.resize(
                int(context.settings.get("window_width", 1440)),
                int(context.settings.get("window_height", 900)),
            )
        else:
            self.resize(1440, 900)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.pages: dict[str, QWidget] = {}
        self.dashboard = DashboardPage(context)
        self.networks = NetworksPage(context)
        self.recovery = RecoveryPage(context)
        self.audit = AuditPage(context)
        self.tools = ToolsPageLazy(context)
        self.adapters = AdapterPage(context)
        self.password = PasswordPage(context)
        self.hardening = HardeningPage(context)
        self.dictionaries = DictionaryPage(context)
        self.diagnostics = DiagnosticsPage(context)
        self.reports = ReportsPage(context)
        self.settings_page = SettingsPage(context)

        for key, page in (
            ("dashboard", self.dashboard),
            ("networks", self.networks),
            ("recovery", self.recovery),
            ("audit", self.audit),
            ("tools", self.tools),
            ("adapters", self.adapters),
            ("hardening", self.hardening),
            ("password", self.password),
            ("dictionaries", self.dictionaries),
            ("diagnostics", self.diagnostics),
            ("reports", self.reports),
            ("settings", self.settings_page),
        ):
            self.pages[key] = page
            self.stack.addWidget(page)

        self._wire()
        self._build_statusbar()

        start = context.settings.get("last_section", "dashboard")
        self.navigate(start if start in self.pages else "dashboard")
        self.dashboard.refresh()
        # First-run discovery of adapters and tools, off the GUI thread.
        self.adapters.refresh()

    # -- construction ---------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(34, 34))
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("WiFi <span style='color:#00D4C7'>Fortress</span>")
        title.setObjectName("BrandTitle")
        title.setTextFormat(Qt.RichText)
        subtitle = QLabel("Parrot OS security suite")
        subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(14)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for index, (key, label, icon) in enumerate(NAV_ITEMS):
            button = QPushButton(f"  {label}")
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setIcon(make_icon(icon))
            button.setIconSize(QSize(18, 18))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_group.addButton(button, index)
            self.nav_buttons[key] = button
            layout.addWidget(button)
        layout.addStretch(1)

        footer = QLabel(
            "Defensive use only.\nWi-Fi Fortress never cracks\nunknown passwords."
        )
        footer.setObjectName("SidebarFooter")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addSpacing(6)
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("SidebarFooter")
        layout.addWidget(version)
        return sidebar

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)
        self.status_label = QLabel("Ready")
        bar.addWidget(self.status_label, 1)
        self.mode_pill = Pill("Quick mode", PALETTE.accent)
        bar.addPermanentWidget(self.mode_pill)
        self.iface_label = QLabel("no adapter")
        self.iface_label.setObjectName("Muted")
        bar.addPermanentWidget(self.iface_label)
        self._update_mode_pill(self.context.settings.get("ui_mode", "quick"))

    def _wire(self) -> None:
        self.dashboard.navigate.connect(self.navigate)
        self.dashboard.start_recovery.connect(lambda: self.navigate("recovery"))
        self.dashboard.start_audit.connect(lambda: self.navigate("audit"))
        self.networks.audit_requested.connect(self._audit_network)
        self.recovery.status_changed.connect(
            lambda status: self.status_label.setText(f"Recovery: {status}")
        )
        self.audit.report_requested.connect(self._show_report)
        self.adapters.adapter_selected.connect(self._on_adapter_selected)
        self.settings_page.mode_changed.connect(self._update_mode_pill)
        self.dictionaries.dictionaries_changed.connect(self.context.load_dictionaries_into_assessment)

    # -- navigation -----------------------------------------------------
    def navigate(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        self.context.settings.set("last_section", key)
        self.status_label.setText(NAV_ITEMS[[i[0] for i in NAV_ITEMS].index(key)][1])

        if key == "networks":
            self.networks.refresh_interfaces()
        elif key == "recovery":
            self.recovery.start_for_network(None)
        elif key == "audit":
            self.audit.refresh_targets()
        elif key == "diagnostics":
            self.diagnostics.refresh_interfaces()
        elif key == "reports":
            self.reports.refresh()
        elif key == "dashboard":
            self.dashboard.refresh()
        elif key == "tools" and not self.context.tools_cache:
            self.tools.scan_tools()
        elif key == "adapters":
            if not self.context.adapter_list:
                self.adapters.refresh()

    def _audit_network(self, network) -> None:
        self.navigate("audit")
        self.audit.start_for_network(network)

    def _show_report(self, payload: dict) -> None:
        self.navigate("reports")
        self.reports.generate_from_payload(payload)

    def _on_adapter_selected(self, interface: str) -> None:
        self.iface_label.setText(interface)
        self.networks.refresh_interfaces()
        self.diagnostics.refresh_interfaces()

    def _update_mode_pill(self, mode: str) -> None:
        advanced = mode == "advanced"
        self.mode_pill.set_status(
            "Advanced mode" if advanced else "Quick mode",
            PALETTE.accent2 if advanced else PALETTE.accent,
        )
        self.dashboard.refresh()

    # -- lifecycle ------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802
        if self.context.settings.get("remember_window", True):
            self.context.settings.update(
                window_width=self.width(), window_height=self.height()
            )
        super().closeEvent(event)


class ToolsPageLazy(QWidget):
    """Thin wrapper so the tools page is imported only when used."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from wififortress.ui.tools_page import ToolsPage

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inner = ToolsPage(context)
        layout.addWidget(self.inner)
        self.installed = getattr(self.inner, "installed", None)

    def scan_tools(self) -> None:
        self.inner.scan_tools()
