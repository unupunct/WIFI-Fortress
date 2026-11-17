"""Wireless network discovery and classification.

Primary source is ``iw dev <iface> scan`` (requires the interface to be up;
on most systems an active scan also needs root, which is reported clearly).
Fallbacks: ``nmcli -f ... device wifi list`` and ``/proc/net/wireless`` for
signal only.

Security classification is derived strictly from what the scan reports:

* ``RSN`` block with ``Authentication suites: SAE`` -> WPA3
* ``RSN`` with both PSK and SAE -> WPA2/WPA3 transition
* ``RSN`` with ``IEEE 802.1X`` -> WPA2-Enterprise
* ``WPA`` (vendor IE) only -> WPA
* ``WEP`` privacy bit without RSN/WPA -> WEP
* no privacy -> Open
* ``OWE`` -> Enhanced Open

When the beacon does not carry enough information, the network is labelled
Unknown and marked as not verified rather than assumed secure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from wififortress.core.logging import get_logger
from wififortress.core.process import CancelToken, run, which
from wififortress.models.entities import Security, WirelessNetwork

log = get_logger(__name__)


@dataclass
class ScanResult:
    networks: list[WirelessNetwork]
    interface: str
    source: str
    started_at: str
    finished_at: str
    duration: float = 0.0
    error: str = ""
    permission_denied: bool = False
    cancelled: bool = False
    raw: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and not self.cancelled


class NetworkClassifier:
    """Turn scan text into a :class:`Security` value plus evidence."""

    @staticmethod
    def classify(capability: str, encryption: str) -> tuple[Security, str, str, bool]:
        """Return (security, authentication, cipher, verified)."""
        cap = (capability or "").lower()
        enc = (encryption or "").lower()

        rsn = "rsn" in cap
        wpa_vendor = "wpa" in cap

        auth = ""
        cipher = ""
        if enc:
            parts = [p.strip() for p in enc.split()]
            ciphers = [p for p in parts if p.upper() in {"CCMP", "TKIP", "GCMP", "WEP", "AES"}]
            if ciphers:
                cipher = "/".join(sorted(set(ciphers)))

        if rsn:
            if "wpa" in cap:
                # Both an RSN IE and a legacy WPA IE: mixed WPA/WPA2 network.
                return Security.WPA_WPA2, "WPA-PSK + PSK", cipher or "TKIP/CCMP", True
            if "sae" in cap or "owe" in cap:
                if "owe" in cap and "sae" not in cap:
                    return Security.OWE, "OWE", cipher or "GCMP", True
                if "psk" in cap:
                    return Security.WPA2_WPA3, "PSK + SAE", cipher or "CCMP", True
                return Security.WPA3, "SAE", cipher or "CCMP", True
            if "802.1x" in cap:
                return Security.WPA2_ENTERPRISE, "IEEE 802.1X", cipher or "CCMP", True
            if "psk" in cap:
                return Security.WPA2, "PSK", cipher or "CCMP", True
            # RSN present but the authentication suite was not reported.
            return Security.WPA2, "RSN (suite not reported)", cipher, False
        if wpa_vendor:
            return Security.WPA, "WPA-PSK", cipher or "TKIP", True
        if "wep" in cap:
            return Security.WEP, "WEP", "WEP", True
        if "privacy" in cap and "no privacy" not in cap:
            return Security.WEP, "WEP", "WEP", True
        if not cap or "open" in cap:
            return Security.OPEN, "Open", "None", True
        return Security.UNKNOWN, "Unknown", cipher, False


class WirelessDiscoveryService:
    def __init__(self, token: CancelToken | None = None) -> None:
        self.token = token or CancelToken()
        self.classifier = NetworkClassifier()

    # -- tool availability ---------------------------------------------
    def available_sources(self) -> dict[str, bool]:
        return {name: which(name) is not None for name in ("iw", "nmcli", "iwlist")}

    # -- scanning ------------------------------------------------------
    def scan(
        self,
        interface: str,
        duration: float = 10.0,
        progress_cb: Callable[[str, int], None] | None = None,
    ) -> ScanResult:
        started = datetime.now(timezone.utc)
        if progress_cb:
            progress_cb(f"Scanning on {interface}...", -1)
        sources = self.available_sources()
        if sources["iw"]:
            result = self._scan_iw(interface)
            if result.ok and result.networks:
                return result
            if result.ok and not result.networks:
                result.notes.append(
                    "iw reported no BSS entries. The adapter may not see any network, "
                    "or the scan was too short."
                )
            if not result.permission_denied and sources["nmcli"]:
                fallback = self._scan_nmcli(interface)
                if fallback.ok and fallback.networks:
                    fallback.notes.extend(result.notes)
                    fallback.notes.append(
                        "iw scan did not return results; NetworkManager's cached "
                        "scan list was used instead."
                    )
                    return fallback
            return result
        if sources["nmcli"]:
            result = self._scan_nmcli(interface)
            result.notes.append("iw is not installed; NetworkManager data used.")
            return result
        return ScanResult(
            networks=[],
            interface=interface,
            source="none",
            started_at=started.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            error="Neither iw nor nmcli is available. Install them with: "
            "sudo apt install iw network-manager",
        )

    def _scan_iw(self, interface: str) -> ScanResult:
        started = datetime.now(timezone.utc)
        result = run(["iw", "dev", interface, "scan"], timeout=45, token=self.token)
        finished = datetime.now(timezone.utc)
        if result.cancelled:
            return ScanResult(
                [], interface, "iw", started.isoformat(), finished.isoformat(),
                cancelled=True, error="Scan cancelled",
            )
        if not result.ok:
            text = (result.stderr or result.stdout).strip()
            denied = "operation not permitted" in text.lower() or result.returncode == 1 and "permitted" in text.lower()
            error = (
                "Scanning requires elevated privileges on this system. "
                "Run WiFi Fortress as your normal user and allow the elevation "
                "prompt, or start a scan from the adapter's elevated scan action."
                if denied
                else f"iw scan failed: {result.summary()}"
            )
            return ScanResult(
                [], interface, "iw", started.isoformat(), finished.isoformat(),
                error=error, permission_denied=denied, raw=text,
            )
        if progress_cb:
            progress_cb("Parsing scan results...", 70)
        networks = self.parse_iw_scan(result.stdout)
        for n in networks:
            n.seen_at = started.isoformat()
            n.first_seen = started.isoformat()
            n.last_seen = started.isoformat()
        return ScanResult(
            networks=networks,
            interface=interface,
            source="iw",
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration=(finished - started).total_seconds(),
            raw=result.stdout,
        )

    def _scan_nmcli(self, interface: str) -> ScanResult:
        started = datetime.now(timezone.utc)
        # nmcli requires a rescan request first; failures are not fatal.
        run(
            ["nmcli", "device", "wifi", "rescan", "ifname", interface],
            timeout=30,
            token=self.token,
        )
        result = run(
            [
                "nmcli", "-t", "-f",
                "BSSID,SSID,CHAN,FREQ,SIGNAL,SECURITY,MODE,RATE,WPA-FLAGS,RSN-FLAGS",
                "device", "wifi", "list", "ifname", interface,
            ],
            timeout=30,
            token=self.token,
        )
        finished = datetime.now(timezone.utc)
        if not result.ok:
            return ScanResult(
                [], interface, "nmcli", started.isoformat(), finished.isoformat(),
                error=f"NetworkManager scan failed: {result.summary()}",
            )
        networks = self.parse_nmcli(result.stdout)
        return ScanResult(
            networks=networks,
            interface=interface,
            source="nmcli",
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration=(finished - started).total_seconds(),
            raw=result.stdout,
        )

    # -- parsing -------------------------------------------------------
    def parse_iw_scan(self, text: str) -> list[WirelessNetwork]:
        networks: list[WirelessNetwork] = []
        blocks = re.split(r"^BSS ", text, flags=re.M)
        for block in blocks[1:]:
            network = self._parse_iw_block(block)
            if network:
                networks.append(network)
        networks.sort(key=lambda n: n.signal_dbm or -999, reverse=True)
        return networks

    def _parse_iw_block(self, block: str) -> WirelessNetwork | None:
        lines = block.splitlines()
        if not lines:
            return None
        header = lines[0]
        bssid_match = re.match(r"([0-9a-fA-F:]{17})", header)
        if not bssid_match:
            return None
        bssid = bssid_match.group(1).lower()
        network = WirelessNetwork(ssid="", bssid=bssid, source="iw")
        capability = ""
        encryption = ""
        rsn_auth = ""
        rsn_cipher = ""
        wpa_auth = ""
        wpa_cipher = ""
        section = ""
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("freq:"):
                try:
                    freq = float(stripped.split(":", 1)[1].strip())
                    network.frequency = int(round(freq))
                except ValueError:
                    pass
            elif stripped.startswith("signal:"):
                try:
                    network.signal_dbm = int(float(stripped.split(":", 1)[1].split()[0]))
                except (ValueError, IndexError):
                    pass
            elif stripped.startswith("beacon interval:"):
                try:
                    network.beacon_interval = int(stripped.split(":", 1)[1].split()[0])
                except (ValueError, IndexError):
                    pass
            elif stripped.startswith("capability:"):
                capability = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("SSID:"):
                network.ssid = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("DS Parameter set: channel"):
                try:
                    network.channel = int(stripped.rsplit(" ", 1)[1])
                except (ValueError, IndexError):
                    pass
            elif stripped.startswith("RSN:"):
                section = "rsn"
            elif stripped.startswith("WPA:"):
                section = "wpa"
            elif stripped.startswith("WPS:"):
                section = "wps"
                network.wps = True
            elif stripped.startswith("HT capabilities") or stripped.startswith("VHT") or stripped.startswith("HE "):
                section = ""
            elif stripped.startswith("* Authentication suites:"):
                suites = stripped.split(":", 1)[1].strip()
                if section == "rsn":
                    rsn_auth = suites
                elif section == "wpa":
                    wpa_auth = suites
            elif stripped.startswith("* Pairwise ciphers:"):
                ciphers = stripped.split(":", 1)[1].strip()
                if section == "rsn":
                    rsn_cipher = ciphers
                elif section == "wpa":
                    wpa_cipher = ciphers
            elif stripped.startswith("* WPS:"):
                network.wps = True
                network.wps_locked = "locked" in stripped.lower()
            elif section == "wps" and stripped.startswith("* Wi-Fi Protected Setup State:"):
                network.wps = True
                if "locked" in stripped.lower():
                    network.wps_locked = True
                else:
                    network.wps_locked = False

        network.hidden = not network.ssid.strip()
        if network.frequency and not network.channel:
            network.channel = self.frequency_to_channel(network.frequency)

        # Build the capability string used by the classifier.
        if rsn_auth:
            cap = "rsn"
            if "sae" in rsn_auth.lower():
                cap += " sae"
            if "psk" in rsn_auth.lower():
                cap += " psk"
            if "802.1x" in rsn_auth.lower():
                cap += " 802.1x"
            if "owe" in rsn_auth.lower():
                cap += " owe"
            enc = rsn_cipher
        elif wpa_auth:
            # A WPA1 IE next to an RSN IE is a WPA/WPA2 mixed-mode network.
            cap = "wpa psk" + (" rsn" if rsn_auth else "")
            enc = wpa_cipher or rsn_cipher
        elif "privacy" in capability.lower():
            cap = "privacy wep"
            enc = "WEP"
        else:
            cap = "open"
            enc = ""
        if rsn_auth and wpa_auth:
            # Both IEs present: report the mixed mode explicitly.
            cap = cap + " wpa"
        security, auth, cipher, verified = self.classifier.classify(cap, enc)
        network.security = security
        network.authentication = auth
        network.cipher = cipher.upper()
        network.encryption = cipher or ("None" if security is Security.OPEN else security.value)
        network.security_verified = verified
        network.raw = {"capability": capability, "rsn": rsn_auth, "wpa": wpa_auth}
        if network.wps is None:
            network.wps = None
        return network

    def parse_nmcli(self, text: str) -> list[WirelessNetwork]:
        networks: list[WirelessNetwork] = []
        for line in text.splitlines():
            # nmcli -t escapes ':' inside fields as '\:'
            fields = re.split(r"(?<!\\):", line)
            if len(fields) < 6:
                continue
            fields = [f.replace("\\:", ":") for f in fields]
            bssid, ssid, chan, freq, signal, security = fields[:6]
            network = WirelessNetwork(ssid=ssid.strip(), bssid=bssid.strip().lower(), source="nmcli")
            try:
                network.channel = int(chan) if chan.strip() else None
            except ValueError:
                network.channel = None
            try:
                network.frequency = int(freq.split()[0]) if freq.strip() else None
            except (ValueError, IndexError):
                network.frequency = None
            try:
                pct = int(signal.strip())
                network.signal_dbm = int(round(pct * 0.6 - 90))  # documented approximation
                network.raw["signal_percent_from_nmcli"] = pct
            except ValueError:
                network.signal_dbm = None
            if not network.frequency and network.channel:
                network.frequency = self.channel_to_frequency(network.channel)
            sec = security.strip().upper()
            mapping = {
                "WPA3": Security.WPA3,
                "WPA2 WPA3": Security.WPA2_WPA3,
                "WPA2": Security.WPA2,
                "WPA1": Security.WPA,
                "WPA1 WPA2": Security.WPA_WPA2,
                "WPA2 802.1X": Security.WPA2_ENTERPRISE,
                "WPA3 802.1X": Security.WPA3_ENTERPRISE,
                "WEP": Security.WEP,
                "": Security.OPEN,
                "--": Security.OPEN,
                "OWE": Security.OWE,
            }
            normalized = " ".join(sec.split())
            network.security = mapping.get(normalized, Security.UNKNOWN)
            network.security_verified = normalized in mapping
            network.authentication = network.security.value
            network.encryption = "None" if network.security is Security.OPEN else network.security.value
            networks.append(network)
        networks.sort(key=lambda n: n.signal_dbm or -999, reverse=True)
        return networks

    # -- helpers -------------------------------------------------------
    @staticmethod
    def frequency_to_channel(freq: int) -> int | None:
        if 2412 <= freq <= 2472:
            return (freq - 2407) // 5
        if freq == 2484:
            return 14
        if 5000 <= freq <= 5925:
            return (freq - 5000) // 5
        if 5925 <= freq <= 7125:
            return (freq - 5950) // 5
        return None

    @staticmethod
    def channel_to_frequency(channel: int) -> int | None:
        if 1 <= channel <= 13:
            return 2407 + channel * 5
        if channel == 14:
            return 2484
        if 32 <= channel <= 177:
            return 5000 + channel * 5
        return None

    # -- history helpers ----------------------------------------------
    @staticmethod
    def merge_history(previous: list[WirelessNetwork], current: list[WirelessNetwork]) -> list[WirelessNetwork]:
        """Carry first-seen/sighting counters across scans."""
        by_bssid = {n.bssid: n for n in previous}
        for net in current:
            old = by_bssid.get(net.bssid)
            if old:
                net.first_seen = old.first_seen
                net.sightings = old.sightings + 1
        return current

    @staticmethod
    def channel_distribution(networks: list[WirelessNetwork]) -> dict[str, dict[int, int]]:
        dist: dict[str, dict[int, int]] = {"2.4 GHz": {}, "5 GHz": {}, "6 GHz": {}, "Unknown": {}}
        for net in networks:
            band = net.band.value
            if net.channel is None:
                continue
            dist.setdefault(band, {})
            dist[band][net.channel] = dist[band].get(net.channel, 0) + 1
        return dist

    @staticmethod
    def security_distribution(networks: list[WirelessNetwork]) -> dict[str, int]:
        dist: dict[str, int] = {}
        for net in networks:
            dist[net.security.value] = dist.get(net.security.value, 0) + 1
        return dist
