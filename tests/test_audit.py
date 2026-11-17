"""Audit scoring: deterministic, documented, and never invented."""

from __future__ import annotations

import pytest

from wififortress.models.entities import (
    AuditResult,
    Security,
    Severity,
    WirelessNetwork,
)
from wififortress.services import audit_service
from wififortress.services.audit_service import AuditContext, SecurityAuditService


def make_network(**kwargs) -> WirelessNetwork:
    base = dict(
        ssid="HomeNet",
        bssid="aa:bb:cc:dd:ee:ff",
        channel=6,
        frequency=2437,
        signal_dbm=-50,
        security=Security.WPA2,
        cipher="CCMP",
        authentication="PSK",
        security_verified=True,
    )
    base.update(kwargs)
    return WirelessNetwork(**base)


@pytest.fixture
def service():
    return SecurityAuditService()


def result_has_unknown_or_none(result) -> bool:
    """Unknown information must never be counted as a scored finding."""
    return all(
        f.verification.is_known or f.severity is Severity.UNKNOWN for f in result.findings
    )


def run(service, network, **context):
    return service.audit(AuditContext(network=network, **context))


def test_open_network_scores_worse_than_wpa3(service):
    open_result = run(service, make_network(security=Security.OPEN, cipher=""))
    wpa3_result = run(service, make_network(security=Security.WPA3))
    assert open_result.score < wpa3_result.score


def test_score_is_bounded_and_grade_assigned(service):
    for security in (Security.OPEN, Security.WEP, Security.WPA, Security.WPA2, Security.WPA3):
        result = run(service, make_network(security=security))
        assert 0 <= result.score <= 100
        assert result.grade in ("A", "B", "C", "D", "F")


def test_unknown_security_does_not_lower_the_score(service):
    known = run(service, make_network(security=Security.WPA2))
    unknown = run(service, make_network(security=Security.UNKNOWN, security_verified=False))
    assert unknown.score >= known.score
    assert result_has_unknown_or_none(unknown)


def test_audit_is_deterministic(service):
    first = run(service, make_network())
    second = run(service, make_network())
    assert first.score == second.score
    assert [f.title for f in first.findings] == [f.title for f in second.findings]


def test_every_finding_is_explained(service):
    result = run(service, make_network(security=Security.WEP, cipher="WEP"))
    assert result.findings
    for finding in result.findings:
        assert finding.title
        assert finding.severity in Severity
        assert finding.evidence
        assert finding.recommendation


def test_wep_is_critical(service):
    result = run(service, make_network(security=Security.WEP, cipher="WEP"))
    assert any(f.severity is Severity.CRITICAL for f in result.findings)
    assert result.score <= 60


def test_open_network_is_reported(service):
    result = run(service, make_network(security=Security.OPEN, cipher=""))
    assert any("open" in f.title.lower() or "encryption" in f.title.lower()
               for f in result.findings)


def test_wps_enabled_is_reported(service):
    result = run(service, make_network(wps=True))
    assert any("wps" in f.title.lower() for f in result.findings)


def test_wpa3_scores_high(service):
    result = run(service, make_network(security=Security.WPA3, cipher="CCMP"))
    assert result.score >= 75


def test_hidden_network_is_informational_only(service):
    result = run(service, make_network(hidden=True))
    hidden = [f for f in result.findings if "hidden" in f.title.lower()]
    assert all(f.severity is Severity.INFORMATIONAL for f in hidden)


def test_severity_counts_match_findings(service):
    result = run(service, make_network(security=Security.WEP, wps=True))
    assert sum(result.severity_counts.values()) == len(result.findings)


def test_checklist_never_empty(service):
    result = run(service, make_network(security=Security.WPA3))
    assert result.checklist


def test_grade_boundaries():
    grade = SecurityAuditService.grade
    assert grade(100) == "A" and grade(90) == "A"
    assert grade(89) == "B" and grade(75) == "B"
    assert grade(74) == "C" and grade(60) == "C"
    assert grade(59) == "D" and grade(45) == "D"
    assert grade(44) == "F" and grade(0) == "F"


def test_score_never_below_zero(service):
    result = run(
        service,
        make_network(security=Security.WEP, cipher="WEP", wps=True, hidden=True, signal_dbm=-92),
    )
    assert result.score >= 0


def test_audit_summary_describes_the_result(service):
    result = run(service, make_network())
    assert isinstance(result, AuditResult)
    summary = audit_service.audit_summary(result)
    assert str(result.score) in summary


def test_neighbour_statistics(networks):
    stats = audit_service.neighbour_statistics(networks)
    assert stats["count"] == len(networks)
    assert stats["median_signal"] is not None


def test_compare_audits_reports_delta(service):
    before = run(service, make_network(security=Security.WEP, cipher="WEP"))
    after = run(service, make_network(security=Security.WPA3))
    comparison = audit_service.compare_audits(before.to_dict(), after.to_dict())
    assert comparison["delta"] > 0
