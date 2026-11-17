"""Data models shared by services and the GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Band(str, Enum):
    GHZ_2_4 = "2.4 GHz"
    GHZ_5 = "5 GHz"
    GHZ_6 = "6 GHz"
    UNKNOWN = "Unknown"

    @classmethod
    def from_frequency(cls, mhz: int | None) -> "Band":
        if not mhz:
            return cls.UNKNOWN
        if 2400 <= mhz < 2500:
            return cls.GHZ_2_4
        if 4900 <= mhz < 5925:
            return cls.GHZ_5
        if 5925 <= mhz < 7125:
            return cls.GHZ_6
        return cls.UNKNOWN


class Security(str, Enum):
    OPEN = "Open"
    WEP = "WEP"
    WPA = "WPA"
    WPA2 = "WPA2"
    WPA2_ENTERPRISE = "WPA2-Enterprise"
    WPA3 = "WPA3"
    WPA3_ENTERPRISE = "WPA3-Enterprise"
    WPA_WPA2 = "WPA/WPA2"
    WPA2_WPA3 = "WPA2/WPA3"
    OWE = "OWE (Enhanced Open)"
    UNKNOWN = "Unknown"

    @property
    def is_enterprise(self) -> bool:
        return "Enterprise" in self.value

    @property
    def is_secure(self) -> bool:
        return self in {
            Security.WPA2,
            Security.WPA2_ENTERPRISE,
            Security.WPA3,
            Security.WPA3_ENTERPRISE,
            Security.WPA_WPA2,
            Security.WPA2_WPA3,
            Security.OWE,
        }


class Severity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFORMATIONAL = "Informational"
    UNKNOWN = "Unknown"

    @property
    def order(self) -> int:
        return {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFORMATIONAL: 4,
            Severity.UNKNOWN: 5,
        }[self]


class Verification(str, Enum):
    VERIFIED = "Verified"
    PARTIAL = "Partially verified"
    UNVERIFIED = "Unverified"
    UNKNOWN = "Unknown - not determinable"

    @property
    def is_known(self) -> bool:
        return self is not Verification.UNKNOWN


class CapabilityState(str, Enum):
    SUPPORTED = "Supported"
    UNSUPPORTED = "Not supported"
    UNKNOWN = "Not verified"
    UNAVAILABLE = "Unavailable"


@dataclass
class AdapterInfo:
    """A wireless network adapter as reported by the system."""

    interface: str
    mac: str = ""
    vendor: str = ""
    model: str = ""
    chipset: str = ""
    driver: str = ""
    driver_version: str = ""
    driver_problem: str = ""
    bus: str = ""
    state: str = ""
    is_up: bool = False
    is_connected: bool = False
    connection_ssid: str = ""
    frequencies: list[int] = field(default_factory=list)
    bands: list[str] = field(default_factory=list)
    standards: list[str] = field(default_factory=list)
    phy: str = ""
    monitor_mode: CapabilityState = CapabilityState.UNKNOWN
    monitor_evidence: str = ""
    ap_mode: CapabilityState = CapabilityState.UNKNOWN
    packet_injection: CapabilityState = CapabilityState.UNKNOWN
    power_management: str = ""
    tx_power_dbm: str = ""
    interface_modes: list[str] = field(default_factory=list)
    is_virtual: bool = False
    origin: str = ""
    soft_blocked: bool = False
    hard_blocked: bool = False
    discovered_at: str = field(default_factory=now_iso)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        parts = [self.interface]
        if self.vendor or self.model:
            parts.append(" ".join(p for p in (self.vendor, self.model) if p))
        return " - ".join(parts)

    @property
    def supports_2ghz(self) -> bool | None:
        if not self.frequencies:
            return None
        return any(2400 <= f < 2500 for f in self.frequencies)

    @property
    def supports_5ghz(self) -> bool | None:
        if not self.frequencies:
            return None
        return any(4900 <= f < 5925 for f in self.frequencies)

    @property
    def supports_6ghz(self) -> bool | None:
        if not self.frequencies:
            return None
        return any(5925 <= f < 7125 for f in self.frequencies)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["monitor_mode"] = self.monitor_mode.value
        data["ap_mode"] = self.ap_mode.value
        data["packet_injection"] = self.packet_injection.value
        return data


@dataclass
class WirelessNetwork:
    ssid: str
    bssid: str
    channel: int | None = None
    frequency: int | None = None
    signal_dbm: int | None = None
    security: Security = Security.UNKNOWN
    encryption: str = "Unknown"
    authentication: str = "Unknown"
    cipher: str = ""
    wps: bool | None = None
    wps_locked: bool | None = None
    pmf: str = "Unknown"
    hidden: bool = False
    beacon_interval: int | None = None
    seen_at: str = field(default_factory=now_iso)
    first_seen: str = field(default_factory=now_iso)
    last_seen: str = field(default_factory=now_iso)
    source: str = "iw"
    raw: dict[str, Any] = field(default_factory=dict)
    # Number of times this BSSID was seen across scans in this session.
    sightings: int = 1
    security_verified: bool = True

    @property
    def band(self) -> Band:
        if self.frequency:
            return Band.from_frequency(self.frequency)
        return Band.UNKNOWN

    @property
    def signal_percent(self) -> int:
        """Map dBm to a 0-100 quality percentage (heuristic, documented)."""
        if self.signal_dbm is None:
            return 0
        # -30 dBm or better => 100 %, -90 dBm => 0 %
        pct = int(round((self.signal_dbm + 90) / 60 * 100))
        return max(0, min(100, pct))

    @property
    def quality_label(self) -> str:
        pct = self.signal_percent
        if self.signal_dbm is None:
            return "Unknown"
        if pct >= 80:
            return "Excellent"
        if pct >= 60:
            return "Good"
        if pct >= 40:
            return "Fair"
        if pct >= 20:
            return "Weak"
        return "Very weak"

    @property
    def display_ssid(self) -> str:
        return self.ssid or "<hidden>"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ssid": self.ssid,
            "bssid": self.bssid,
            "channel": self.channel,
            "frequency": self.frequency,
            "band": self.band.value,
            "signal": self.signal_dbm,
            "security": self.security.value,
            "encryption": self.encryption,
            "authentication": self.authentication,
            "cipher": self.cipher,
            "wps": self.wps,
            "pmf": self.pmf,
            "hidden": self.hidden,
            "seen_at": self.seen_at,
            "source": self.source,
            "sightings": self.sightings,
            "security_verified": self.security_verified,
        }


@dataclass
class Finding:
    title: str
    severity: Severity
    evidence: str
    explanation: str
    impact: str
    recommendation: str
    verification: Verification = Verification.VERIFIED
    category: str = "General"
    points: int = 0
    cwe: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "severity": self.severity.value,
            "evidence": self.evidence,
            "explanation": self.explanation,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "verification": self.verification.value,
            "category": self.category,
            "points": self.points,
        }


@dataclass
class AuditResult:
    ssid: str
    bssid: str
    interface: str
    created_at: str = field(default_factory=now_iso)
    score: int = 0
    grade: str = ""
    findings: list[Finding] = field(default_factory=list)
    score_breakdown: list[dict[str, Any]] = field(default_factory=list)
    network: dict[str, Any] = field(default_factory=dict)
    adapter: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    checklist: list[str] = field(default_factory=list)
    app_version: str = ""

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "informational": 0,
            "unknown": 0,
        }
        for finding in self.findings:
            key = finding.severity.value.lower()
            if key == "unknown":
                key = "unknown"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "ssid": self.ssid,
            "bssid": self.bssid,
            "interface": self.interface,
            "created_at": self.created_at,
            "score": self.score,
            "grade": self.grade,
            "findings": [f.to_dict() for f in self.findings],
            "severity_counts": self.severity_counts,
            "score_breakdown": self.score_breakdown,
            "network": self.network,
            "adapter": self.adapter,
            "environment": self.environment,
            "checklist": self.checklist,
            "app_version": self.app_version,
        }


@dataclass
class PasswordAssessment:
    length: int = 0
    entropy_bits: float = 0.0
    score: int = 0
    strength: str = ""
    category: str = ""
    weaknesses: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    composition: dict[str, Any] = field(default_factory=dict)
    dictionary_hits: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    crack_time_estimate: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "length": self.length,
            "entropy_bits": round(self.entropy_bits, 1),
            "score": self.score,
            "strength": self.strength,
            "category": self.category,
            "weaknesses": self.weaknesses,
            "recommendations": self.recommendations,
            "composition": self.composition,
            "dictionary_hits": self.dictionary_hits,
            "patterns": self.patterns,
            "crack_time_estimate": self.crack_time_estimate,
        }


@dataclass
class DiagnosticCheck:
    key: str
    label: str
    status: str  # ok | warn | fail | skip | running
    detail: str = ""
    fix: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"


@dataclass
class ToolInfo:
    key: str
    name: str
    package: str
    description: str
    purpose: str
    installed: bool = False
    path: str = ""
    version: str = ""
    version_command: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    missing_dependencies: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    restricted: bool = False
    restriction_note: str = ""
    install_hint: str = ""
    diagnostics: str = ""

    @property
    def status_label(self) -> str:
        if not self.installed:
            return "Not installed"
        if self.missing_dependencies:
            return "Missing dependencies"
        return "Available"


@dataclass
class RecoveryMethod:
    key: str
    title: str
    status: str  # available | unavailable | required | unknown
    detail: str
    evidence: str = ""


@dataclass
class RecoveryResult:
    status: str  # one of RecoveryStatus values
    ssid: str
    message: str
    credential: str | None = None
    credential_source: str = ""
    methods: list[RecoveryMethod] = field(default_factory=list)
    gateway: str = ""
    router_vendor: str = ""
    router_admin_url: str = ""
    guidance: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class RecoveryStatus:
    CREDENTIAL_RECOVERED = "Credential recovered"
    SAVED_CREDENTIAL_UNAVAILABLE = "Saved credential unavailable"
    ROUTER_ADMIN_REQUIRED = "Router administration required"
    PASSWORD_RESET_REQUIRED = "Password reset required"
    METHOD_UNAVAILABLE = "Recovery method unavailable"
