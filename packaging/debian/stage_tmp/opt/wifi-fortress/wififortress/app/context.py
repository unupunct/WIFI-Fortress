"""Application context: services, settings and shared state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from wififortress.core.database import Database
from wififortress.core.logging import EventLogger, get_logger
from wififortress.models.entities import AdapterInfo, WirelessNetwork
from wififortress.services.adapter_service import AdapterService
from wififortress.services.audit_service import SecurityAuditService
from wififortress.services.diagnostics_service import WirelessDiagnosticsService
from wififortress.services.dictionary_service import DictionaryManagerService
from wififortress.services.discovery_service import WirelessDiscoveryService
from wififortress.services.password_service import (
    DictionarySet,
    PasswordAssessmentService,
    PasswordGeneratorService,
)
from wififortress.services.recovery_service import SavedCredentialRecoveryService
from wififortress.services.report_service import ReportService
from wififortress.services.router_assistant import RouterRecoveryAssistant
from wififortress.services.settings_service import SettingsService
from wififortress.services.tools_service import WirelessToolIntegrationService

log = get_logger(__name__)


@dataclass
class AppContext:
    """Everything the UI needs, created once in main()."""

    settings: SettingsService
    db: Database
    adapters: AdapterService
    discovery: WirelessDiscoveryService
    recovery: SavedCredentialRecoveryService
    router: RouterRecoveryAssistant
    audit: SecurityAuditService
    tools: WirelessToolIntegrationService
    password: PasswordAssessmentService
    generator: PasswordGeneratorService
    dictionaries: DictionaryManagerService
    diagnostics: WirelessDiagnosticsService
    reports: ReportService
    events: EventLogger = field(default_factory=lambda: EventLogger("wififortress.app"))

    # --- shared in-memory state --------------------------------------
    adapter_list: list[AdapterInfo] = field(default_factory=list)
    active_interface: str = ""
    networks: list[WirelessNetwork] = field(default_factory=list)
    last_scan_source: str = ""
    last_scan_error: str = ""
    last_audit: dict | None = None
    last_audit_at: str = ""
    last_recovery_summary: dict | None = None
    recovery_count: int = 0
    audit_count: int = 0
    tools_cache: list = field(default_factory=list)

    # --- helpers ------------------------------------------------------
    @property
    def active_adapter(self) -> AdapterInfo | None:
        for adapter in self.adapter_list:
            if adapter.interface == self.active_interface:
                return adapter
        return self.adapter_list[0] if self.adapter_list else None

    def load_dictionaries_into_assessment(self) -> None:
        paths = self.dictionaries.enabled_paths()
        word_set = DictionarySet.from_files(paths)
        self.password.set_dictionary(word_set)
        self.generator.set_word_source(word_set.words)
        log.info("Loaded %d dictionary words from %d files", len(word_set), len(paths))

    def record_operation(self, category: str, title: str, status: str, detail: str = "") -> None:
        self.db.log_operation(category, title, status, detail)


def build_context(data_override: Path | None = None) -> AppContext:
    settings = SettingsService()
    db = Database()
    dictionaries = DictionaryManagerService(db=db)
    password = PasswordAssessmentService()
    generator = PasswordGeneratorService()
    context = AppContext(
        settings=settings,
        db=db,
        adapters=AdapterService(),
        discovery=WirelessDiscoveryService(),
        recovery=SavedCredentialRecoveryService(),
        router=RouterRecoveryAssistant(),
        audit=SecurityAuditService(),
        tools=WirelessToolIntegrationService(),
        password=password,
        generator=generator,
        dictionaries=dictionaries,
        diagnostics=WirelessDiagnosticsService(),
        reports=ReportService(db=db),
    )
    # Dictionary metadata may be stale on first run; recount in the
    # background would delay startup, so only verify missing counts.
    for info in dictionaries.all():
        if info.exists and info.entry_count == 0:
            try:
                dictionaries.verify(info.dict_id)
            except OSError as exc:  # pragma: no cover
                log.warning("Could not verify %s: %s", info.dict_id, exc)
    context.load_dictionaries_into_assessment()
    return context
