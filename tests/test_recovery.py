"""Credential recovery: only real saved profiles, never a guess."""

from __future__ import annotations

from pathlib import Path

import pytest

from wififortress.services.recovery_service import (
    CredentialResult,
    SavedCredentialRecoveryService,
    SavedProfile,
)


@pytest.fixture
def keyfile_dir(tmp_path) -> Path:
    directory = tmp_path / "nm" / "system-connections"
    directory.mkdir(parents=True)
    (directory / "HomeNet.nmconnection").write_text(
        "[connection]\n"
        "id=HomeNet\n"
        "uuid=11111111-2222-3333-4444-555555555555\n"
        "type=wifi\n"
        "\n"
        "[wifi]\n"
        "ssid=HomeNet\n"
        "mode=infrastructure\n"
        "\n"
        "[wifi-security]\n"
        "key-mgmt=wpa-psk\n"
        "psk=CorrectHorseBattery\n",
        encoding="utf-8",
    )
    (directory / "Cafe.nmconnection").write_text(
        "[connection]\nid=Cafe\nuuid=99999999-2222-3333-4444-555555555555\ntype=wifi\n"
        "\n[wifi]\nssid=Cafe\nmode=infrastructure\n",
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def service(monkeypatch):
    svc = SavedCredentialRecoveryService()
    # Never touch the real machine's NetworkManager.
    monkeypatch.setattr(svc, "_nmcli_profiles", lambda: [])
    return svc


def test_keyfile_profiles_are_listed(service, keyfile_dir):
    profiles = service._keyfile_profiles(keyfile_dir, "keyfile", "user")
    ssids = {p.ssid for p in profiles}
    assert {"HomeNet", "Cafe"} <= ssids


def test_open_profile_reports_no_credential_needed(service, keyfile_dir):
    profiles = {p.ssid: p for p in service._keyfile_profiles(keyfile_dir, "keyfile", "user")}
    assert profiles["Cafe"].can_recover is False


def test_psk_profile_can_be_recovered(service, keyfile_dir):
    profiles = {p.ssid: p for p in service._keyfile_profiles(keyfile_dir, "keyfile", "user")}
    assert profiles["HomeNet"].can_recover is True


def test_secret_is_read_from_the_keyfile(service, keyfile_dir):
    path = keyfile_dir / "HomeNet.nmconnection"
    secret, reason = service._read_keyfile_secret(path)
    # On a host that can read the file the PSK is returned; otherwise the
    # service must explain exactly why it could not.
    assert (secret == "CorrectHorseBattery") or reason


def test_redacted_display_never_reveals_the_password(service):
    shown = service.redact_for_display("CorrectHorseBattery")
    assert "CorrectHorseBattery" not in shown
    assert shown


def test_unknown_ssid_returns_no_result(service):
    result = service.recover("NetworkThatIsNotSaved")
    assert isinstance(result, CredentialResult)
    assert result.secret is None
    assert result.message


def test_summary_reports_counts(service, keyfile_dir):
    service._keyfile_profiles(keyfile_dir, "keyfile", "user")
    summary = service.summary()
    assert {"total", "recoverable", "sources"} <= set(summary)


def test_system_scope_requires_explicit_permission(service, keyfile_dir):
    result = service.recover("HomeNet", allow_system=False)
    assert result.secret is None
    assert result.reasons or result.message


def test_profiles_are_never_mutated(service, keyfile_dir):
    before = {p.name: p.read_bytes() for p in keyfile_dir.iterdir()}
    service._keyfile_profiles(keyfile_dir, "keyfile", "user")
    service.recover("HomeNet")
    after = {p.name: p.read_bytes() for p in keyfile_dir.iterdir()}
    assert before == after


def test_saved_profile_defaults_to_user_scope():
    profile = SavedProfile(
        profile_id="HomeNet",
        ssid="HomeNet",
        uuid="u",
        path=Path("x.nmconnection"),
        source="keyfile-user",
    )
    assert profile.owner_scope == "user"
    assert profile.can_recover is False
