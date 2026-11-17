"""Core safety: process execution, privilege handling, paths, database."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from wififortress.core import paths
from wififortress.core.process import (
    CancelToken,
    CancelledError,
    CommandError,
    run as run_command,
    validate_interface_name,
    validate_target,
)


# -- path validation -----------------------------------------------------
@pytest.mark.parametrize("name", ["wlan0", "wlan0mon", "eth0", "wlx00c0ca123456"])
def test_valid_interface_names_accepted(name):
    assert validate_interface_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["", "wlan0; rm -rf /", "wlan0 && reboot", "../etc/passwd", "wlan 0", "a" * 40, "$(id)"],
)
def test_dangerous_interface_names_rejected(name):
    with pytest.raises(CommandError):
        validate_interface_name(name)


@pytest.mark.parametrize("target", ["192.168.1.1", "10.0.0.254", "example.org", "::1"])
def test_valid_targets_accepted(target):
    assert validate_target(target) == target


@pytest.mark.parametrize("target", ["", "1.1.1.1; rm -rf /", "host|cat", "`id`", "a b"])
def test_dangerous_targets_rejected(target):
    with pytest.raises(CommandError):
        validate_target(target)


# -- process execution ---------------------------------------------------
def test_run_command_returns_output_without_a_shell():
    python = sys.executable
    result = run_command([python, "-c", "print('hello')"], timeout=30)
    assert result.ok
    assert "hello" in result.stdout


def test_run_command_never_interprets_shell_metacharacters():
    python = sys.executable
    result = run_command([python, "-c", "print('a;b|c')"], timeout=30)
    assert "a;b|c" in result.stdout


def test_missing_binary_is_reported_not_raised():
    result = run_command(["this-binary-does-not-exist-xyz"], timeout=10)
    assert result.ok is False
    assert result.returncode != 0


def test_nonzero_exit_is_visible():
    python = sys.executable
    result = run_command([python, "-c", "import sys; sys.exit(3)"], timeout=30)
    assert result.ok is False
    assert result.returncode == 3


def test_command_error_is_exported():
    assert issubclass(CommandError, RuntimeError)


def test_cancel_token_stops_a_long_command():
    python = sys.executable
    token = CancelToken()
    token.cancel()
    result = run_command(
        [python, "-c", "import time; time.sleep(5)"], timeout=30, token=token
    )
    assert result.cancelled is True
    assert result.ok is False


def test_output_is_redacted_before_it_is_returned():
    python = sys.executable
    result = run_command([python, "-c", "print('psk=SuperSecret123')"], timeout=30)
    assert "SuperSecret123" not in result.stdout


# -- paths ---------------------------------------------------------------
def test_data_dirs_honour_the_environment_override(tmp_path, monkeypatch):
    target = tmp_path / "custom-data"
    monkeypatch.setenv("WIFI_FORTRESS_DATA_DIR", str(target))
    paths.data_dir.cache_clear()
    assert paths.data_dir() == target
    assert paths.data_dir().is_dir()


def test_reports_and_logs_live_under_the_data_dir():
    data = paths.data_dir()
    assert paths.reports_dir().is_relative_to(data)
    assert paths.log_dir().is_relative_to(data)
    assert paths.database_path().is_relative_to(data)


# -- database ------------------------------------------------------------
def test_database_creates_schema(database):
    with database.cursor() as cur:
        rows = cur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    tables = {row[0] for row in rows}
    for expected in ("audits", "reports", "dictionaries", "operations", "scans", "networks"):
        assert expected in tables


def test_audit_round_trip(database):
    payload = {"ssid": "HomeNet", "bssid": "aa:bb:cc:dd:ee:ff", "score": 82, "grade": "B"}
    audit_id = database.save_audit(payload)
    stored = database.audit(audit_id)
    assert stored["ssid"] == "HomeNet"
    assert stored["score"] == 82


def test_audit_history_is_ordered_newest_first(database):
    first = database.save_audit({"ssid": "A", "bssid": "1", "score": 10, "grade": "F"})
    second = database.save_audit({"ssid": "B", "bssid": "2", "score": 20, "grade": "F"})
    rows = database.audits(10)
    assert [r["id"] for r in rows][:2] == [second, first]


def test_settings_persist(settings):
    settings.set("ui_mode", "advanced")
    from wififortress.services.settings_service import SettingsService

    assert SettingsService().get("ui_mode") == "advanced"


def test_operation_log_records_actions(database):
    database.log_operation("scan", "Scan on wlan0", "ok", "12 networks")
    rows = database.operations(5)
    assert rows and rows[0]["category"] == "scan"
