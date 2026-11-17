"""Parsing and classification of wireless scan output."""

from __future__ import annotations

import pytest

from pathlib import Path

from wififortress.models.entities import Band, Security
from wififortress.services.discovery_service import NetworkClassifier, WirelessDiscoveryService

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def by_ssid(networks, ssid):
    return next(n for n in networks if n.ssid == ssid)


def test_every_bssid_is_parsed(networks):
    assert len(networks) == 6
    assert len({n.bssid for n in networks}) == 6


def test_transition_mode_reported_as_wpa2_wpa3(networks):
    net = by_ssid(networks, "HomeNetwork")
    assert net.security is Security.WPA2_WPA3
    assert net.security_verified is True
    assert net.cipher == "CCMP"
    assert net.authentication == "PSK + SAE"


def test_enterprise_detected(networks):
    net = by_ssid(networks, "Office5G")
    assert net.security is Security.WPA2_ENTERPRISE
    assert net.authentication == "IEEE 802.1X"
    assert net.security_verified is True


def test_open_network_has_no_encryption(networks):
    net = by_ssid(networks, "FreeCafeWiFi")
    assert net.security is Security.OPEN
    assert net.security_verified is True
    assert net.cipher in ("", "NONE")


def test_wep_only_network_detected():
    service = WirelessDiscoveryService()
    text = (
        "BSS de:ad:be:ef:00:01(on wlan0)\n"
        "\tfreq: 2437.0\n"
        "\tsignal: -60.00 dBm\n"
        "\tcapability: ESS Privacy (0x0011)\n"
        "\tSSID: LegacyWep\n"
        "\tDS Parameter set: channel 6\n"
    )
    parsed = service.parse_iw_scan(text)
    assert len(parsed) == 1
    assert parsed[0].security is Security.WEP
    assert parsed[0].security_verified is True


def test_wpa_and_rsn_reported_as_mixed_mode(networks):
    net = by_ssid(networks, "OldRouter")
    assert net.security is Security.WPA_WPA2


def test_band_inferred_from_frequency(networks):
    assert by_ssid(networks, "HomeNetwork").band is Band.GHZ_2_4
    assert by_ssid(networks, "Office5G").band is Band.GHZ_5


def test_signal_quality_is_monotonic(networks):
    strong = by_ssid(networks, "HomeNetwork")
    weak = by_ssid(networks, "FreeCafeWiFi")
    assert strong.signal_dbm == -42
    assert weak.signal_dbm == -80
    assert 0 <= weak.signal_percent < strong.signal_percent <= 100


def test_hidden_ssid_marked_hidden(networks):
    net = next(n for n in networks if not n.ssid)
    assert net.hidden is True
    assert net.display_ssid == "<hidden>"


def test_unknown_security_is_never_guessed():
    # RSN IE present but no authentication suite reported -> not verified.
    security, auth, _cipher, verified = NetworkClassifier.classify("rsn", "CCMP")
    assert security is Security.WPA2
    assert verified is False
    # Nothing reported at all -> Unknown, never a guess.
    security, auth, _cipher, verified = NetworkClassifier.classify("ess", "")
    assert security is Security.UNKNOWN
    assert auth == "Unknown"
    assert verified is False


def test_channel_distribution_counts_networks(networks):
    service = WirelessDiscoveryService()
    dist = service.channel_distribution(networks)
    per_band = {band: sum(channels.values()) for band, channels in dist.items()}
    assert sum(per_band.values()) == len(networks)
    assert per_band["2.4 GHz"] >= 1
    assert dist["2.4 GHz"][1] == 1


def test_security_distribution_groups_labels(networks):
    service = WirelessDiscoveryService()
    dist = service.security_distribution(networks)
    assert dist.get("WPA2/WPA3", 0) >= 1
    assert dist.get("Open", 0) >= 1
    assert sum(dist.values()) == len(networks)


def test_merge_history_keeps_first_seen_and_counts_sightings(networks):
    service = WirelessDiscoveryService()
    previous = service.parse_iw_scan((FIXTURES / "iw_scan_mixed.txt").read_text(encoding="utf-8"))
    for net in previous:
        net.sightings = 3
        net.first_seen = "2024-01-01T00:00:00+00:00"
    current = service.parse_iw_scan((FIXTURES / "iw_scan_mixed.txt").read_text(encoding="utf-8"))
    merged = service.merge_history(previous, current)
    assert len(merged) == len(networks)
    assert all(n.sightings == 4 for n in merged)
    assert all(n.first_seen == "2024-01-01T00:00:00+00:00" for n in merged)


def test_nmcli_fallback_parsing(nmcli_scan_text):
    service = WirelessDiscoveryService()
    parsed = service.parse_nmcli(nmcli_scan_text)
    assert len(parsed) == 5
    home = by_ssid(parsed, "HomeNetwork")
    assert home.security is Security.WPA2_WPA3
    office = by_ssid(parsed, "Office5G")
    assert office.security is Security.WPA2_ENTERPRISE
    cafe = by_ssid(parsed, "FreeCafeWiFi")
    assert cafe.security is Security.OPEN
    assert by_ssid(parsed, "OldRouter").security is Security.WPA_WPA2
    assert by_ssid(parsed, "HomeNetwork").band is Band.GHZ_2_4
    assert by_ssid(parsed, "Office5G").band is Band.GHZ_5


@pytest.mark.parametrize("text", ["", "\n\n", "garbage line without structure"])
def test_empty_or_garbage_input_yields_no_networks(text):
    service = WirelessDiscoveryService()
    assert service.parse_iw_scan(text) == []
