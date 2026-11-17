"""Defensive Wi-Fi security audit engine.

The engine inspects one network (as discovered) plus the local adapter and
environment, and produces :class:`~wififortress.models.entities.Finding`
objects with evidence, impact, recommendation and a verification status.

Scoring rules (documented, evidence-based)
------------------------------------------
The score starts at 100 and is reduced by the weight of each verified
finding.  Findings whose verification status is "Unknown - not determinable"
never change the score; they are reported separately so that missing
information is never presented as security or as vulnerability.

Weights
    Critical  30      High  20      Medium  12      Low  5      Informational 0
Caps
    The total deduction is capped at 100, and the score never drops below 0.

Grade bands
    90-100 A   75-89 B   60-74 C   45-59 D   0-44 F
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from wififortress import __version__
from wififortress.core.logging import get_logger
from wififortress.models.entities import (
    AdapterInfo,
    AuditResult,
    Finding,
    Security,
    Severity,
    Verification,
    WirelessNetwork,
)

log = get_logger(__name__)

SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 30,
    Severity.HIGH: 20,
    Severity.MEDIUM: 12,
    Severity.LOW: 5,
    Severity.INFORMATIONAL: 0,
    Severity.UNKNOWN: 0,
}


@dataclass
class AuditContext:
    network: WirelessNetwork
    adapter: AdapterInfo | None = None
    neighbours: list[WirelessNetwork] = field(default_factory=list)
    router: dict[str, Any] = field(default_factory=dict)
    user_password_assessment: dict[str, Any] | None = None
    interface: str = ""


class SecurityAuditService:
    """Produce a defensive audit for a single wireless network."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    # -- public API ----------------------------------------------------
    def audit(self, context: AuditContext) -> AuditResult:
        self.findings = []
        net = context.network
        result = AuditResult(
            ssid=net.display_ssid,
            bssid=net.bssid,
            interface=context.interface,
            app_version=__version__,
            network=net.to_dict(),
            adapter=context.adapter.to_dict() if context.adapter else {},
        )

        self._check_encryption(net)
        self._check_authentication(net)
        self._check_wps(net)
        self._check_pmf(net)
        self._check_cipher(net)
        self._check_band_and_channel(net, context.neighbours)
        self._check_signal(net)
        self._check_hidden(net)
        self._check_router(context.router, net)
        self._check_environment(context)
        if context.user_password_assessment:
            self._check_user_password(context.user_password_assessment)

        self.findings.sort(key=lambda f: (f.severity.order, f.title))
        result.findings = list(self.findings)
        result.score, result.score_breakdown = self.score(self.findings)
        result.grade = self.grade(result.score)
        result.environment = {
            "neighbour_count": len(context.neighbours),
            "router": context.router,
            "channel_load": self._channel_load(net, context.neighbours),
        }
        result.checklist = self.checklist(result.findings)
        return result

    # -- individual checks --------------------------------------------
    def _add(
        self,
        title: str,
        severity: Severity,
        evidence: str,
        explanation: str,
        impact: str,
        recommendation: str,
        verification: Verification = Verification.VERIFIED,
        category: str = "Wireless security",
    ) -> None:
        self.findings.append(
            Finding(
                title=title,
                severity=severity,
                evidence=evidence,
                explanation=explanation,
                impact=impact,
                recommendation=recommendation,
                verification=verification,
                category=category,
                points=SEVERITY_WEIGHTS.get(severity, 0)
                if verification.is_known
                else 0,
            )
        )

    def _check_encryption(self, net: WirelessNetwork) -> None:
        sec = net.security
        if sec is Security.OPEN:
            self._add(
                "Open network without encryption",
                Severity.CRITICAL,
                f"Scan capability '{net.raw.get('capability', 'no privacy bit')}' shows no "
                "RSN or WPA information element.",
                "An open network carries all traffic in the clear at the 802.11 layer. "
                "Any nearby device can capture it.",
                "All traffic can be read and modified by anyone in range; captive portals "
                "make this worse because users type credentials into an unauthenticated page.",
                "Enable WPA2-PSK (AES) or WPA3-Personal on the access point. Use OWE only "
                "for genuinely public guest access.",
            )
        elif sec is Security.WEP:
            self._add(
                "Obsolete WEP encryption in use",
                Severity.CRITICAL,
                f"Privacy bit set with WEP (cipher reported: {net.cipher or 'WEP'}).",
                "WEP uses RC4 with a 24-bit IV that repeats quickly; it has been "
                "practically broken since 2001.",
                "The network key can be recovered from captured traffic in minutes with "
                "widely available tools, exposing every session.",
                "Replace WEP with WPA2-PSK (AES) or WPA3-Personal. Retire hardware that "
                "cannot do better.",
            )
        elif sec is Security.WPA:
            self._add(
                "Legacy WPA (TKIP) configuration",
                Severity.HIGH,
                "Only the vendor WPA information element is advertised; no RSN element.",
                "WPA with TKIP relies on RC4 and has known weaknesses including the "
                "Beck-Tews attack against short packets.",
                "An attacker within range can decrypt selected traffic and, in some "
                "configurations, inject frames.",
                "Move the access point to WPA2-PSK with CCMP, or WPA3 where supported.",
            )
        elif sec is Security.WPA_WPA2:
            self._add(
                "WPA/WPA2 mixed mode enabled",
                Severity.MEDIUM,
                "Both the vendor WPA IE and the RSN IE are advertised.",
                "Mixed mode keeps TKIP available so that old clients can connect; every "
                "client may then be downgraded to the weaker cipher.",
                "A single legacy client weakens the whole network.",
                "Disable WPA/TKIP and allow only WPA2 (CCMP) or WPA3 clients.",
            )
        elif sec is Security.WPA2:
            self._add(
                "WPA2-PSK in use",
                Severity.INFORMATIONAL,
                "RSN element with PSK authentication and CCMP.",
                "WPA2-PSK with CCMP is acceptable but has no forward secrecy: a captured "
                "handshake can be attacked offline against a weak passphrase.",
                "Security depends entirely on passphrase strength and on PMF being enabled.",
                "Consider WPA3-Personal (SAE) and enable Protected Management Frames.",
            )
        elif sec in (Security.WPA3, Security.WPA2_WPA3):
            self._add(
                f"{sec.value} configured",
                Severity.INFORMATIONAL,
                f"RSN authentication suite reported as '{net.authentication}'.",
                "SAE (WPA3) resists offline dictionary attacks on the handshake.",
                "Good baseline; the remaining risk is passphrase reuse and management frame spoofing.",
                "Keep SAE enabled, enable PMF (required in WPA3), and disable transition "
                "mode once all clients support WPA3.",
            )
        elif sec in (Security.WPA2_ENTERPRISE, Security.WPA3_ENTERPRISE):
            self._add(
                f"{sec.value} configured",
                Severity.INFORMATIONAL,
                f"RSN with IEEE 802.1X authentication ({net.authentication}).",
                "Enterprise mode authenticates each user through a RADIUS server.",
                "Correctly configured EAP-TLS is strong; legacy EAP methods (LEAP, EAP-MD5) "
                "are not. Server certificate validation on clients is essential.",
                "Verify clients validate the RADIUS server certificate and disable legacy "
                "EAP methods.",
            )
        elif sec is Security.OWE:
            self._add(
                "Enhanced Open (OWE) network",
                Severity.INFORMATIONAL,
                "RSN with OWE authentication suite.",
                "OWE provides opportunistic encryption without a shared password.",
                "Traffic is protected against passive eavesdropping but not against an "
                "attacker who runs a look-alike access point.",
                "Appropriate for public guest access; do not use for trusted devices.",
            )
        else:
            self._add(
                "Security configuration could not be determined",
                Severity.UNKNOWN,
                f"Scan reported security as '{net.security.value}' with authentication "
                f"'{net.authentication}'.",
                "The beacon did not contain enough information to classify the network.",
                "Unknown - a missing capability report is not evidence of weakness.",
                "Re-scan while associated or inspect the access point configuration directly.",
                Verification.UNKNOWN,
            )

    def _check_authentication(self, net: WirelessNetwork) -> None:
        if net.security in (Security.WPA2_ENTERPRISE, Security.WPA3_ENTERPRISE):
            return
        if net.security is Security.OPEN:
            return
        if not net.security_verified:
            self._add(
                "Authentication suite not fully reported",
                Severity.UNKNOWN,
                f"RSN element present but authentication suites were not parsed "
                f"(reported: '{net.authentication}').",
                "Without the authentication suite the PSK/SAE/802.1X mode cannot be confirmed.",
                "Unknown - no conclusion is drawn.",
                "Inspect the access point configuration to confirm the authentication mode.",
                Verification.UNKNOWN,
            )
        elif net.security is Security.WPA2:
            self._add(
                "Pre-shared key authentication",
                Severity.LOW,
                "Authentication suite: PSK.",
                "Every user of the network shares one key, which cannot be rotated per user "
                "and is exposed to anyone who learns it.",
                "A single leaked passphrase compromises the network for everyone; guest "
                "access is not isolated.",
                "Provide a separate guest SSID with client isolation and rotate the main "
                "passphrase when someone leaves.",
            )

    def _check_wps(self, net: WirelessNetwork) -> None:
        if net.wps is True:
            locked = net.wps_locked
            evidence = "WPS information element present in the beacon"
            if locked is True:
                evidence += " (WPS reported as locked)"
            elif locked is False:
                evidence += " (WPS reported as configured/unlocked)"
            self._add(
                "Wi-Fi Protected Setup (WPS) is enabled",
                Severity.HIGH if locked is False else Severity.MEDIUM,
                evidence,
                "WPS allows a client to enrol with an 8-digit PIN. The PIN is verified in "
                "two halves, which reduces the search space to about 11,000 attempts, and "
                "push-button mode can be triggered by anyone in physical range.",
                "The network passphrase can be recovered by an attacker in range without "
                "knowing it, defeating the purpose of WPA2.",
                "Disable WPS in the access point settings. If a device needs it, enable it "
                "only for the duration of pairing.",
            )
        elif net.wps is None:
            self._add(
                "WPS status not reported by the beacon",
                Severity.UNKNOWN,
                "No WPS information element was present in the scan output.",
                "Many access points do not advertise WPS; absence in a scan is not proof "
                "that it is disabled.",
                "Unknown - not scored.",
                "Check the access point administration page and disable WPS there.",
                Verification.UNKNOWN,
            )

    def _check_pmf(self, net: WirelessNetwork) -> None:
        if net.security in (Security.WPA3, Security.WPA2_WPA3, Security.WPA3_ENTERPRISE):
            return
        if net.pmf in ("Required", "Capable"):
            return
        self._add(
            "Protected Management Frames not advertised",
            Severity.MEDIUM if net.security.is_secure else Severity.LOW,
            "RSN capabilities did not advertise management frame protection (MFPC/MFPR).",
            "Without PMF, deauthentication and disassociation frames are unauthenticated "
            "and can be spoofed.",
            "An attacker can disconnect clients at will, which enables denial of service "
            "and makes handshake capture easier.",
            "Enable PMF (802.11w) on the access point; WPA3 requires it.",
        )

    def _check_cipher(self, net: WirelessNetwork) -> None:
        cipher = (net.cipher or "").upper()
        if "TKIP" in cipher:
            self._add(
                "TKIP cipher in use",
                Severity.HIGH,
                f"Pairwise cipher reported as {net.cipher}.",
                "TKIP is deprecated and has published cryptographic weaknesses.",
                "Traffic can be decrypted in some scenarios and the cipher is disallowed "
                "by WPA3 and modern certification.",
                "Configure CCMP (AES) only.",
            )
        elif "WEP" in cipher:
            return  # already reported as obsolete encryption
        elif "CCMP" in cipher or "GCMP" in cipher:
            self._add(
                "Strong pairwise cipher",
                Severity.INFORMATIONAL,
                f"Pairwise cipher reported as {net.cipher}.",
                "CCMP (AES) and GCMP are the current ciphers for WPA2 and WPA3.",
                "No action required.",
                "No change needed.",
            )
        elif net.security.is_secure:
            self._add(
                "Cipher not reported",
                Severity.UNKNOWN,
                "The scan did not report a pairwise cipher.",
                "Cipher strength cannot be assessed from the available evidence.",
                "Unknown - not scored.",
                "Confirm the cipher on the access point.",
                Verification.UNKNOWN,
            )

    def _check_band_and_channel(
        self, net: WirelessNetwork, neighbours: list[WirelessNetwork]
    ) -> None:
        if net.channel is None:
            self._add(
                "Channel not reported",
                Severity.UNKNOWN,
                "The scan did not include channel information.",
                "Channel congestion cannot be evaluated.",
                "Unknown - not scored.",
                "Re-scan the network.",
                Verification.UNKNOWN,
            )
            return
        same_channel = [
            n for n in neighbours
            if n.bssid != net.bssid and n.channel == net.channel and n.band == net.band
        ]
        load = len(same_channel)
        if net.band.value == "2.4 GHz" and load >= 3:
            self._add(
                "Congested 2.4 GHz channel",
                Severity.MEDIUM,
                f"{load} other access points share channel {net.channel} on 2.4 GHz.",
                "2.4 GHz has only three non-overlapping channels (1, 6, 11) and co-channel "
                "contention causes airtime loss.",
                "Throughput and latency degrade for every client on the channel.",
                "Move the access point to channel 1, 6 or 11 with the least overlap, or "
                "prefer 5 GHz where clients support it.",
            )
        elif load >= 5:
            self._add(
                "Busy channel",
                Severity.LOW,
                f"{load} other access points share channel {net.channel}.",
                "High co-channel occupancy increases contention and retries.",
                "Reduced throughput under load.",
                "Consider a less crowded channel or band steering to 5/6 GHz.",
            )
        if net.band.value == "2.4 GHz":
            self._add(
                "2.4 GHz band only",
                Severity.LOW,
                f"Network advertises {net.frequency} MHz (channel {net.channel}).",
                "2.4 GHz has longer range but lower capacity and more interference from "
                "Bluetooth, microwaves and neighbouring networks.",
                "Performance and reliability are limited compared with 5/6 GHz.",
                "Enable a 5 GHz SSID on the access point, ideally with band steering.",
            )

    def _check_signal(self, net: WirelessNetwork) -> None:
        if net.signal_dbm is None:
            self._add(
                "Signal strength not reported",
                Severity.UNKNOWN,
                "The scan did not report a signal level.",
                "Signal quality cannot be assessed.",
                "Unknown - not scored.",
                "Re-scan closer to the access point.",
                Verification.UNKNOWN,
            )
            return
        if net.signal_dbm < -80:
            self._add(
                "Very weak signal",
                Severity.LOW,
                f"Signal level {net.signal_dbm} dBm ({net.signal_percent}%).",
                "Clients at the edge of coverage negotiate low data rates and retransmit "
                "heavily.",
                "Poor reliability and higher exposure to rogue access points with a "
                "stronger signal at that location.",
                "Reposition the access point, add a second unit, or reduce the coverage area.",
            )

    def _check_hidden(self, net: WirelessNetwork) -> None:
        if not net.hidden:
            return
        self._add(
            "Hidden SSID",
            Severity.INFORMATIONAL,
            "The beacon has an empty SSID; the name is only sent in probe responses.",
            "Hiding the SSID does not prevent discovery: the name is revealed whenever a "
            "client associates.",
            "It offers no real security and can cause client roaming problems.",
            "Do not rely on SSID hiding; rely on WPA3/PMF and strong passphrases.",
        )

    def _check_router(self, router: dict[str, Any], net: WirelessNetwork) -> None:
        if not router:
            return
        if router.get("open_ports") and 80 in router["open_ports"] and 443 not in router["open_ports"]:
            self._add(
                "Router administration page served over plain HTTP",
                Severity.HIGH,
                f"Default gateway {router.get('gateway')} answers on TCP 80 without HTTPS "
                f"({router.get('page_title') or 'no title reported'}).",
                "The administrator login and session cookie cross the wireless link "
                "unencrypted.",
                "An attacker on the same network can capture administrator credentials "
                "and take over the router.",
                "Enable HTTPS administration on the router, or manage it from a wired "
                "connection.",
                Verification.VERIFIED,
                category="Router",
            )
        if router.get("vendor"):
            self._add(
                f"Router identified as {router['vendor']}",
                Severity.INFORMATIONAL,
                f"Administration page title: '{router.get('page_title')}'; Server header: "
                f"'{router.get('server_header')}'.",
                "Knowing the vendor allows the owner to check for current firmware.",
                "Outdated firmware is a common source of router compromise.",
                "Check the vendor's support page for firmware updates and apply them.",
                category="Router",
            )
        else:
            self._add(
                "Router model not identified",
                Severity.UNKNOWN,
                "The administration page did not return a recognisable title.",
                "Firmware currency cannot be checked without the model.",
                "Unknown - not scored.",
                "Read the model from the label on the router and check its firmware version.",
                Verification.UNKNOWN,
                category="Router",
            )

    def _check_environment(self, context: AuditContext) -> None:
        adapter = context.adapter
        if adapter is None:
            return
        if adapter.hard_blocked or adapter.soft_blocked:
            self._add(
                "Wireless radio is blocked",
                Severity.LOW,
                f"rfkill state: soft={adapter.soft_blocked}, hard={adapter.hard_blocked}.",
                "A blocked radio cannot transmit or receive; measurements taken while "
                "blocked are unreliable.",
                "Audit results may be incomplete.",
                "Unblock the radio with the Adapter Manager before auditing.",
                category="Adapter",
            )
        if adapter.driver_problem:
            self._add(
                "Adapter driver problem",
                Severity.UNKNOWN,
                adapter.driver_problem,
                "Driver information could not be read, so adapter capabilities are unverified.",
                "Unknown - not scored.",
                "Load the correct driver module and re-run the audit.",
                Verification.UNKNOWN,
                category="Adapter",
            )

    def _check_user_password(self, assessment: dict[str, Any]) -> None:
        score = int(assessment.get("score", 0))
        strength = assessment.get("strength", "")
        if score < 50:
            self._add(
                "Supplied Wi-Fi password is weak",
                Severity.HIGH,
                f"Local password assessment score {score}/100 ({strength}); "
                f"estimated offline resistance: {assessment.get('crack_time_estimate', 'unknown')}.",
                "A WPA2 handshake captured from the air can be attacked offline at high "
                "speed; a weak passphrase falls quickly.",
                "Anyone who records a handshake can recover the network passphrase.",
                "Replace it with a generated 20+ character password or a 5-word passphrase.",
            )
        elif score < 70:
            self._add(
                "Supplied Wi-Fi password could be stronger",
                Severity.MEDIUM,
                f"Local password assessment score {score}/100 ({strength}).",
                "Moderate passphrases survive casual guessing but not a focused offline attack.",
                "Recoverable with a targeted attack.",
                "Increase length and avoid dictionary words.",
            )
        else:
            self._add(
                "Supplied Wi-Fi password passes local assessment",
                Severity.INFORMATIONAL,
                f"Local password assessment score {score}/100 ({strength}).",
                "The passphrase shows no structural weakness in the local checks.",
                "No action required.",
                "Keep it unique to this network.",
            )

    # -- scoring -------------------------------------------------------
    @staticmethod
    def score(findings: list[Finding]) -> tuple[int, list[dict[str, Any]]]:
        breakdown: list[dict[str, Any]] = []
        deduction = 0
        for finding in findings:
            if finding.severity is Severity.UNKNOWN or not finding.verification.is_known:
                continue
            weight = SEVERITY_WEIGHTS.get(finding.severity, 0)
            if weight:
                deduction += weight
                breakdown.append(
                    {
                        "title": finding.title,
                        "severity": finding.severity.value,
                        "points": -weight,
                    }
                )
        total = max(0, min(100, 100 - deduction))
        return total, breakdown

    @staticmethod
    def grade(score: int) -> str:
        if score >= 90:
            return "A"
        if score >= 75:
            return "B"
        if score >= 60:
            return "C"
        if score >= 45:
            return "D"
        return "F"

    @staticmethod
    def _channel_load(net: WirelessNetwork, neighbours: list[WirelessNetwork]) -> int:
        if net.channel is None:
            return 0
        return sum(1 for n in neighbours if n.channel == net.channel and n.bssid != net.bssid)

    @staticmethod
    def checklist(findings: list[Finding]) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for finding in findings:
            if finding.severity in (Severity.INFORMATIONAL, Severity.UNKNOWN):
                continue
            if finding.recommendation in seen:
                continue
            seen.add(finding.recommendation)
            items.append(f"[{finding.severity.value}] {finding.recommendation}")
        if not items:
            items.append("No corrective actions were identified by this audit.")
        items.append("Re-run the audit after applying changes and compare the scores.")
        return items


def audit_summary(audit: AuditResult) -> str:
    counts = audit.severity_counts
    return (
        f"Score {audit.score}/100 (grade {audit.grade}) - "
        f"{counts['critical']} critical, {counts['high']} high, {counts['medium']} medium, "
        f"{counts['low']} low, {counts['informational']} informational, "
        f"{counts['unknown']} unknown"
    )


def compare_audits(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare two audit payloads for the Reports section."""
    prev_titles = {f["title"] for f in previous.get("findings", [])}
    curr_titles = {f["title"] for f in current.get("findings", [])}
    return {
        "previous_score": previous.get("score"),
        "current_score": current.get("score"),
        "delta": (current.get("score") or 0) - (previous.get("score") or 0),
        "resolved": sorted(prev_titles - curr_titles),
        "new": sorted(curr_titles - prev_titles),
        "unchanged": sorted(prev_titles & curr_titles),
    }


def neighbour_statistics(neighbours: list[WirelessNetwork]) -> dict[str, Any]:
    signals = [n.signal_dbm for n in neighbours if n.signal_dbm is not None]
    return {
        "count": len(neighbours),
        "median_signal": statistics.median(signals) if signals else None,
        "duplicate_ssids": sorted(
            {
                n.ssid
                for n in neighbours
                if n.ssid and sum(1 for m in neighbours if m.ssid == n.ssid) > 1
            }
        ),
    }
