"""Redaction: nothing secret may reach logs, reports or the UI."""

from __future__ import annotations

import pytest

from wififortress.core.redaction import (
    REDACTED,
    redact_mapping,
    redact_text,
    sanitize_command,
)


@pytest.mark.parametrize(
    "line",
    [
        "psk=MySecret123",
        "wpa-psk MySecret123",
        "password: MySecret123",
        "PASSWORD=MySecret123",
        "key-mgmt=wpa-psk\npsk=MySecret123",
    ],
)
def test_common_secret_forms_are_redacted(line):
    out = redact_text(line)
    assert "MySecret123" not in out
    assert REDACTED in out


def test_redaction_is_case_insensitive():
    assert "abc123" not in redact_text("PSK=abc123")


def test_command_arguments_are_scrubbed():
    assert "hunter2" not in sanitize_command(["nmcli", "-s", "-p", "psk", "hunter2"])


def test_mapping_drops_secret_keys():
    cleaned = redact_mapping({"ssid": "Home", "psk": "secret", "Password": "x", "key": "y"})
    assert cleaned["ssid"] == "Home"
    assert "psk" not in {k.lower() for k in cleaned}
    assert "password" not in {k.lower() for k in cleaned}


def test_plain_text_survives():
    text = "Scan completed on wlan0: 12 networks found."
    assert redact_text(text) == text
