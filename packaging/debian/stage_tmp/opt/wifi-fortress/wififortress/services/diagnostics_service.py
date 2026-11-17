"""Connection diagnostics.

Runs a fixed sequence of read-only checks and reports each with a status,
an explanation and a suggested fix:

1. wireless interface present and up
2. IP address / prefix
3. default gateway
4. gateway reachability (ARP/neighbour table + TCP probe)
5. DNS resolution of a well-known name
6. internet connectivity (HTTPS to a public endpoint)
7. latency (ICMP, or TCP fallback)
8. packet loss (ICMP sample)
9. DNS servers configured
10. NetworkManager service state
11. driver availability and firmware messages
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from wififortress.core.logging import get_logger
from wififortress.core.process import CancelToken, run, which
from wififortress.models.entities import DiagnosticCheck

log = get_logger(__name__)

DNS_TEST_NAME = "deb.debian.org"
INTERNET_TEST_HOST = ("deb.debian.org", 443)


@dataclass
class DiagnosticReport:
    interface: str
    checks: list[DiagnosticCheck] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "ok")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def overall(self) -> str:
        if any(c.status == "fail" for c in self.checks):
            return "fail"
        if any(c.status == "warn" for c in self.checks):
            return "warn"
        return "ok"


class WirelessDiagnosticsService:
    def __init__(self, token: CancelToken | None = None) -> None:
        self.token = token or CancelToken()

    def run_all(
        self, interface: str, progress: Callable[[DiagnosticCheck], None] | None = None
    ) -> DiagnosticReport:
        report = DiagnosticReport(interface=interface)
        steps: list[tuple[str, Callable[[], DiagnosticCheck]]] = [
            ("interface", lambda: self.check_interface(interface)),
            ("ip", lambda: self.check_ip_address(interface)),
            ("gateway", self.check_gateway),
            ("gateway_reach", self.check_gateway_reachable),
            ("dns", self.check_dns_resolution),
            ("internet", self.check_internet),
            ("latency", self.check_latency),
            ("loss", self.check_packet_loss),
            ("dns_config", self.check_dns_servers),
            ("networkmanager", self.check_networkmanager),
            ("driver", lambda: self.check_driver(interface)),
        ]
        for key, step in steps:
            if self.token.cancelled:
                report.checks.append(
                    DiagnosticCheck(key, key, "skip", "Cancelled before this check ran.")
                )
                continue
            try:
                check = step()
            except Exception as exc:  # pragma: no cover - defensive
                check = DiagnosticCheck(
                    key, key, "fail", f"Check raised an error: {exc}", "Report this as a bug."
                )
            report.checks.append(check)
            if progress:
                progress(check)
        report.finished_at = time.time()
        return report

    # -- individual checks ---------------------------------------------
    def check_interface(self, interface: str) -> DiagnosticCheck:
        sys_dir = Path("/sys/class/net") / interface
        if not sys_dir.exists():
            return DiagnosticCheck(
                "interface",
                "Wireless interface",
                "fail",
                f"Interface {interface} does not exist.",
                "Select a valid adapter in the Adapter Manager, or reconnect the device.",
            )
        state = "unknown"
        try:
            state = (sys_dir / "operstate").read_text().strip()
        except OSError:
            pass
        is_wireless = (sys_dir / "wireless").exists() or (sys_dir / "phy80211").exists()
        if state == "up":
            return DiagnosticCheck(
                "interface", "Wireless interface", "ok",
                f"{interface} is up ({state}); wireless={is_wireless}.", "",
                {"operstate": state, "wireless": is_wireless},
            )
        return DiagnosticCheck(
            "interface",
            "Wireless interface",
            "warn",
            f"{interface} exists but its state is '{state}'.",
            f"Bring the interface up: sudo ip link set {interface} up",
            {"operstate": state, "wireless": is_wireless},
        )

    def check_ip_address(self, interface: str) -> DiagnosticCheck:
        if not which("ip"):
            return DiagnosticCheck("ip", "IP configuration", "skip", "iproute2 is not installed.",
                                   "sudo apt install iproute2")
        result = run(["ip", "-4", "addr", "show", "dev", interface], timeout=10, token=self.token)
        if not result.ok:
            return DiagnosticCheck("ip", "IP configuration", "fail", result.summary(),
                                   "Reinstall iproute2.")
        match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", result.stdout)
        if not match:
            return DiagnosticCheck(
                "ip", "IP configuration", "fail",
                f"No IPv4 address on {interface}.",
                "Renew the DHCP lease: sudo nmcli device reapply " + interface,
            )
        address, prefix = match.groups()
        return DiagnosticCheck(
            "ip", "IP configuration", "ok", f"{address}/{prefix}", "",
            {"address": address, "prefix": int(prefix)},
        )

    def check_gateway(self) -> DiagnosticCheck:
        if not which("ip"):
            return DiagnosticCheck("gateway", "Default gateway", "skip", "iproute2 missing.",
                                   "sudo apt install iproute2")
        result = run(["ip", "route", "show", "default"], timeout=10, token=self.token)
        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
        if not match:
            return DiagnosticCheck(
                "gateway", "Default gateway", "fail", "No default route.",
                "Connect to a network: nmcli device wifi connect <SSID>",
            )
        return DiagnosticCheck(
            "gateway", "Default gateway", "ok", f"Gateway {match.group(1)}", "",
            {"gateway": match.group(1)},
        )

    def check_gateway_reachable(self) -> DiagnosticCheck:
        gateway = ""
        result = run(["ip", "route", "show", "default"], timeout=10, token=self.token)
        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
        if match:
            gateway = match.group(1)
        if not gateway:
            return DiagnosticCheck("gateway_reach", "Gateway reachability", "skip",
                                   "No gateway to test.")
        neigh = run(["ip", "neigh", "show", gateway], timeout=10, token=self.token)
        has_mac = bool(re.search(r"lladdr ([0-9a-f:]{17})", neigh.stdout))
        reachable = False
        try:
            with socket.create_connection((gateway, 80), timeout=1.5):
                reachable = True
        except OSError:
            try:
                with socket.create_connection((gateway, 443), timeout=1.5):
                    reachable = True
            except OSError:
                reachable = False
        if reachable or has_mac:
            return DiagnosticCheck(
                "gateway_reach", "Gateway reachability", "ok",
                f"Gateway {gateway} answered" + (" (TCP)" if reachable else " (ARP entry present)"),
                "", {"gateway": gateway, "tcp": reachable, "arp": has_mac},
            )
        return DiagnosticCheck(
            "gateway_reach", "Gateway reachability", "fail",
            f"Gateway {gateway} did not answer and has no neighbour entry.",
            "Check the Wi-Fi signal and the router; try reconnecting.",
            {"gateway": gateway},
        )

    def check_dns_resolution(self) -> DiagnosticCheck:
        start = time.monotonic()
        try:
            infos = socket.getaddrinfo(DNS_TEST_NAME, 443, socket.AF_INET)
            elapsed = (time.monotonic() - start) * 1000
            address = infos[0][4][0] if infos else ""
            return DiagnosticCheck(
                "dns", "DNS resolution", "ok",
                f"{DNS_TEST_NAME} resolved to {address} in {elapsed:.0f} ms", "",
                {"address": address, "ms": round(elapsed, 1)},
            )
        except socket.gaierror as exc:
            return DiagnosticCheck(
                "dns", "DNS resolution", "fail", f"Could not resolve {DNS_TEST_NAME}: {exc}",
                "Check /etc/resolv.conf or set a DNS server: "
                "nmcli connection modify <name> ipv4.dns 9.9.9.9",
            )

    def check_internet(self) -> DiagnosticCheck:
        start = time.monotonic()
        try:
            with socket.create_connection(INTERNET_TEST_HOST, timeout=4):
                elapsed = (time.monotonic() - start) * 1000
                return DiagnosticCheck(
                    "internet", "Internet connectivity", "ok",
                    f"TCP connection to {INTERNET_TEST_HOST[0]}:{INTERNET_TEST_HOST[1]} "
                    f"in {elapsed:.0f} ms", "",
                    {"ms": round(elapsed, 1)},
                )
        except OSError as exc:
            return DiagnosticCheck(
                "internet", "Internet connectivity", "fail",
                f"Could not reach {INTERNET_TEST_HOST[0]}: {exc}",
                "The local network works but the internet does not; check the router's "
                "WAN connection or the captive portal.",
            )

    def _ping(self, host: str, count: int = 4) -> tuple[bool, str]:
        if not which("ping"):
            return False, "ping is not installed"
        result = run(["ping", "-c", str(count), "-W", "2", host], timeout=count * 3 + 5,
                     token=self.token)
        return result.ok, result.stdout + result.stderr

    def check_latency(self) -> DiagnosticCheck:
        gateway = ""
        result = run(["ip", "route", "show", "default"], timeout=10, token=self.token)
        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
        if match:
            gateway = match.group(1)
        target = gateway or DNS_TEST_NAME
        ok, output = self._ping(target, 4)
        stats = re.search(r"(\d+) packets transmitted, (\d+) received.*?min/avg/max[^=]*= ([\d.]+)/([\d.]+)/([\d.]+)", output)
        if not ok and not stats:
            return DiagnosticCheck(
                "latency", "Latency", "warn",
                f"Latency to {target} could not be measured (ICMP may be filtered).",
                "This is often normal; gateway reachability and DNS results matter more.",
            )
        if stats:
            avg = float(stats.group(4))
            status = "ok" if avg < 100 else "warn"
            fix = "" if status == "ok" else "High latency: check for channel congestion or a distant access point."
            return DiagnosticCheck(
                "latency", "Latency", status,
                f"{stats.group(1)} sent, {stats.group(2)} received; "
                f"min/avg/max = {stats.group(3)}/{stats.group(4)}/{stats.group(5)} ms to {target}",
                fix, {"avg_ms": avg},
            )
        return DiagnosticCheck("latency", "Latency", "warn", "No statistics parsed.", "")

    def check_packet_loss(self) -> DiagnosticCheck:
        gateway = ""
        result = run(["ip", "route", "show", "default"], timeout=10, token=self.token)
        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
        if match:
            gateway = match.group(1)
        if not gateway:
            return DiagnosticCheck("loss", "Packet loss", "skip", "No gateway to test.")
        ok, output = self._ping(gateway, 10)
        stats = re.search(r"(\d+) packets transmitted, (\d+) received, ([\d.]+)% packet loss", output)
        if not stats:
            return DiagnosticCheck("loss", "Packet loss", "warn",
                                   "Packet loss could not be measured (ICMP filtered).")
        loss = float(stats.group(3))
        status = "ok" if loss == 0 else ("warn" if loss < 10 else "fail")
        fix = "" if loss == 0 else "Packet loss to the gateway suggests weak signal or interference."
        return DiagnosticCheck(
            "loss", "Packet loss", status,
            f"{stats.group(1)} sent, {stats.group(2)} received, {loss:.0f}% loss",
            fix, {"loss_percent": loss},
        )

    def check_dns_servers(self) -> DiagnosticCheck:
        servers: list[str] = []
        resolv = Path("/etc/resolv.conf")
        if resolv.exists():
            try:
                for line in resolv.read_text().splitlines():
                    if line.strip().startswith("nameserver"):
                        servers.append(line.split()[1])
            except OSError:
                pass
        if not servers:
            return DiagnosticCheck(
                "dns_config", "DNS servers", "fail", "No nameserver is configured.",
                "Set DNS on the connection: nmcli connection modify <name> ipv4.dns 9.9.9.9",
            )
        return DiagnosticCheck(
            "dns_config", "DNS servers", "ok", ", ".join(servers), "", {"servers": servers}
        )

    def check_networkmanager(self) -> DiagnosticCheck:
        if which("systemctl"):
            result = run(["systemctl", "is-active", "NetworkManager"], timeout=10, token=self.token)
            state = result.stdout.strip()
            if state == "active":
                return DiagnosticCheck("networkmanager", "NetworkManager", "ok", "active", "")
            return DiagnosticCheck(
                "networkmanager", "NetworkManager", "fail",
                f"NetworkManager is '{state or 'unknown'}'.",
                "Start it: sudo systemctl start NetworkManager",
            )
        if which("nmcli"):
            result = run(["nmcli", "general", "status"], timeout=10, token=self.token)
            if result.ok:
                return DiagnosticCheck("networkmanager", "NetworkManager", "ok",
                                       result.stdout.strip().splitlines()[0], "")
        return DiagnosticCheck(
            "networkmanager", "NetworkManager", "skip",
            "NetworkManager is not installed or systemctl is unavailable.",
            "Install it if you rely on saved profiles: sudo apt install network-manager",
        )

    def check_driver(self, interface: str) -> DiagnosticCheck:
        driver_link = Path("/sys/class/net") / interface / "device" / "driver"
        if not driver_link.exists():
            return DiagnosticCheck(
                "driver", "Driver availability", "warn",
                "No driver link in sysfs for this interface.",
                "The interface may be a virtual device, or the driver is not loaded.",
            )
        try:
            driver = driver_link.resolve().name
        except OSError:
            driver = "unknown"
        firmware_issue = ""
        if Path("/var/log/syslog").exists():
            try:
                text = Path("/var/log/syslog").read_text(errors="replace")[-20000:]
                if re.search(rf"{re.escape(driver)}.*(firmware).*(fail|error)", text, re.I):
                    firmware_issue = "Firmware load errors appear in /var/log/syslog."
            except OSError:
                pass
        if firmware_issue:
            return DiagnosticCheck(
                "driver", "Driver availability", "warn", f"Driver {driver} loaded. {firmware_issue}",
                "Install the matching firmware package, e.g. sudo apt install firmware-<vendor>",
                {"driver": driver},
            )
        return DiagnosticCheck(
            "driver", "Driver availability", "ok", f"Driver {driver} is bound to {interface}.",
            "", {"driver": driver},
        )
