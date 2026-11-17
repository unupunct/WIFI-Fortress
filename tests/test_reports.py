"""Reports: real files on disk, no secrets, correct registration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wififortress.core.database import Database
from wififortress.models.entities import Security, WirelessNetwork
from wififortress.services.audit_service import AuditContext, SecurityAuditService
from wififortress.services.report_service import ReportService


@pytest.fixture
def audit_payload():
    network = WirelessNetwork(
        ssid="HomeNet",
        bssid="aa:bb:cc:dd:ee:ff",
        channel=6,
        frequency=2437,
        signal_dbm=-52,
        security=Security.WPA2,
        cipher="CCMP",
        authentication="PSK",
    )
    result = SecurityAuditService().audit(AuditContext(network=network))
    return result.to_dict()


@pytest.fixture
def report_service():
    return ReportService(db=Database())


def test_all_three_formats_are_written(report_service, audit_payload):
    paths = report_service.generate(audit_payload, ("pdf", "html", "json"))
    for path in (paths.pdf, paths.html, paths.json):
        assert path is not None
        assert Path(path).is_file()
        assert Path(path).stat().st_size > 200


def test_single_format_only_writes_that_file(report_service, audit_payload):
    paths = report_service.generate(audit_payload, ("json",))
    assert paths.json and not paths.pdf and not paths.html


def test_json_report_is_valid_and_redacted(report_service, audit_payload):
    payload = dict(audit_payload)
    payload["password"] = "SuperSecret123"
    payload["psk"] = "deadbeef" * 8
    paths = report_service.generate(payload, ("json",))
    data = json.loads(Path(paths.json).read_text(encoding="utf-8"))
    text = json.dumps(data)
    assert "SuperSecret123" not in text
    assert "deadbeef" * 8 not in text


def test_html_report_contains_no_secret(report_service, audit_payload):
    payload = dict(audit_payload)
    payload["password"] = "SuperSecret123"
    paths = report_service.generate(payload, ("html",))
    assert "SuperSecret123" not in Path(paths.html).read_text(encoding="utf-8")


def test_pdf_starts_with_pdf_header(report_service, audit_payload):
    paths = report_service.generate(audit_payload, ("pdf",))
    assert Path(paths.pdf).read_bytes()[:5] == b"%PDF-"


def test_reports_are_registered_in_history(report_service, audit_payload):
    report_service.generate(audit_payload, ("json",))
    history = report_service.history(10)
    assert history
    assert history[0]["path"]


def test_delete_removes_file_and_record(report_service, audit_payload):
    paths = report_service.generate(audit_payload, ("json",))
    history = report_service.history(1)
    record = history[0]
    assert report_service.delete(record["id"]) is True
    assert not Path(paths.json).exists()
    assert all(h["id"] != record["id"] for h in report_service.history(10))


def test_compare_reports_score_delta(report_service, audit_payload):
    first = dict(audit_payload, score=90)
    second = dict(audit_payload, score=70)
    comparison = report_service.compare(first, second)
    assert comparison["delta"] == -20
