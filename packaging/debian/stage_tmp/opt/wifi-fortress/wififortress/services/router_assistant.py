"""Router recovery assistant.

When a saved credential cannot be read, this service helps the user regain
access the legitimate way: through the router's own administration page or
a documented factory reset.

It identifies the default gateway (from the routing table), probes the
router's HTTP/HTTPS ports, reads the page title (which often names the
vendor) and returns step-by-step guidance.  It never submits credentials,
never sends a password and never performs a reset itself.
"""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass, field
from pathlib import Path

from wififortress.core.logging import get_logger
from wififortress.core.process import CancelToken, run, which

log = get_logger(__name__)

# Vendor fingerprints are matched against the page title/headers only.
VENDOR_FINGERPRINTS: list[tuple[str, str]] = [
    (r"fritz", "AVM FRITZ!Box"),
    (r"tp-?link", "TP-Link"),
    (r"archer", "TP-Link Archer"),
    (r"asus", "ASUS"),
    (r"netgear", "NETGEAR"),
    (r"linksys", "Linksys"),
    (r"d-?link", "D-Link"),
    (r"huawei", "Huawei"),
    (r"zte", "ZTE"),
    (r"mikrotik", "MikroTik"),
    (r"ubiquiti|unifi", "Ubiquiti"),
    (r"cisco", "Cisco"),
    (r"technicolor", "Technicolor"),
    (r"sagemcom", "Sagemcom"),
    (r"zyxel", "Zyxel"),
    (r"tenda", "Tenda"),
    (r"mercusys", "Mercusys"),
    (r"keenetic", "Keenetic"),
    (r"openwrt", "OpenWrt"),
    (r"dd-wrt", "DD-WRT"),
    (r"tomato", "Tomato"),
    (r"arris", "ARRIS"),
    (r"orange", "Orange Livebox"),
    (r"vodafone", "Vodafone Station"),
    (r"digi", "Digi Router"),
    (r"eero", "eero"),
    (r"google wifi|nest wifi", "Google Nest WiFi"),
    (r"synology", "Synology"),
    (r"trendnet", "TRENDnet"),
]


@dataclass
class RouterInfo:
    gateway: str = ""
    interface: str = ""
    gateway_mac: str = ""
    reachable: bool = False
    open_ports: list[int] = field(default_factory=list)
    http_url: str = ""
    https_url: str = ""
    page_title: str = ""
    vendor: str = ""
    server_header: str = ""
    model_hint: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def admin_url(self) -> str:
        if self.https_url:
            return self.https_url
        return self.http_url or (f"http://{self.gateway}" if self.gateway else "")

    @property
    def identified(self) -> bool:
        return bool(self.vendor or self.page_title)


class RouterRecoveryAssistant:
    def __init__(self, token: CancelToken | None = None) -> None:
        self.token = token or CancelToken()

    # -- discovery -----------------------------------------------------
    def default_gateway(self, interface: str | None = None) -> tuple[str, str]:
        """Return (gateway_ip, interface) from the routing table."""
        if which("ip"):
            argv = ["ip", "route", "show", "default"]
            result = run(argv, timeout=10, token=self.token)
            if result.ok:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if "via" in parts and "dev" in parts:
                        gateway = parts[parts.index("via") + 1]
                        dev = parts[parts.index("dev") + 1]
                        if interface is None or dev == interface:
                            return gateway, dev
        if which("route"):
            result = run(["route", "-n"], timeout=10, token=self.token)
            if result.ok:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 8 and parts[0] == "0.0.0.0":
                        return parts[1], parts[7]
        return "", ""

    def arp_lookup(self, ip: str) -> str:
        if not ip:
            return ""
        if which("ip"):
            result = run(["ip", "neigh", "show", ip], timeout=10, token=self.token)
            if result.ok:
                match = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", result.stdout)
                if match:
                    return match.group(1).lower()
        proc = Path("/proc/net/arp")
        if proc.exists():
            try:
                for line in proc.read_text().splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 4 and parts[0] == ip:
                        return parts[3].lower()
            except OSError:
                pass
        return ""

    def probe(self, gateway: str, timeout: float = 3.0) -> RouterInfo:
        info = RouterInfo(gateway=gateway)
        if not gateway:
            info.notes.append("No default gateway was found; connect to the network first.")
            return info
        # ICMP may be filtered; a TCP probe is the real signal.
        for port in (80, 443, 8080, 8443):
            if self.token.cancelled:
                break
            if self._tcp_open(gateway, port, timeout):
                info.open_ports.append(port)
        info.reachable = bool(info.open_ports)
        if 443 in info.open_ports:
            info.https_url = f"https://{gateway}/"
        if 80 in info.open_ports:
            info.http_url = f"http://{gateway}/"
        elif 8080 in info.open_ports:
            info.http_url = f"http://{gateway}:8080/"
        if not info.reachable:
            info.notes.append(
                "The gateway does not answer on common administration ports. "
                "It may be a modem in bridge mode, or the administration page may "
                "be disabled on the WAN side."
            )
            return info

        title, server = self._fetch_title(info.http_url or info.https_url)
        info.page_title = title
        info.server_header = server
        blob = f"{title} {server}".lower()
        for pattern, vendor in VENDOR_FINGERPRINTS:
            if re.search(pattern, blob):
                info.vendor = vendor
                break
        if not info.vendor:
            info.notes.append(
                "The administration page did not identify the router vendor; "
                "check the label on the device."
            )
        return info

    def _tcp_open(self, host: str, port: int, timeout: float) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _fetch_title(self, url: str) -> tuple[str, str]:
        """Fetch just enough of a page to read the title and Server header."""
        if not url:
            return "", ""
        if which("curl"):
            result = run(
                [
                    "curl", "-sS", "-k", "--max-time", "6", "-D", "-",
                    "--range", "0-8192", url,
                ],
                timeout=12,
                token=self.token,
            )
            if result.ok or result.stdout:
                return self._extract_title(result.stdout), self._extract_server(result.stdout)
        import urllib.error
        import urllib.request

        try:
            request = urllib.request.Request(url, headers={"User-Agent": "WiFiFortress/1.0"})
            context = None
            if url.startswith("https"):
                import ssl

                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(request, timeout=6, context=context) as response:  # noqa: S310
                body = response.read(8192).decode("utf-8", errors="replace")
                server = response.headers.get("Server", "")
                return self._extract_title(body), server
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.debug("Router page fetch failed: %s", exc)
            return "", ""

    @staticmethod
    def _extract_title(text: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if not match:
            return ""
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        return title[:120]

    @staticmethod
    def _extract_server(text: str) -> str:
        for line in text.splitlines():
            if line.lower().startswith("server:"):
                return line.split(":", 1)[1].strip()[:120]
        return ""

    # -- guidance ------------------------------------------------------
    def guidance(self, info: RouterInfo, ssid: str = "") -> list[str]:
        steps: list[str] = []
        if info.gateway:
            steps.append(
                f"Default gateway: {info.gateway}. Open the administration page at "
                f"{info.admin_url or 'http://' + info.gateway} in a web browser."
            )
        else:
            steps.append(
                "Find the default gateway: run 'ip route show default' in a terminal, "
                "or check the Wi-Fi settings page of this computer."
            )
        if info.vendor:
            steps.append(
                f"The router appears to be a {info.vendor} device. Look for the "
                "administrator credentials printed on the label on the back of the router."
            )
        steps.extend(
            [
                "Sign in with the router's administrator account (not the Wi-Fi password).",
                "Open the Wireless / Wi-Fi settings section of the administration page.",
                "Locate the security or wireless password field and set a new passphrase "
                "of at least 16 characters; use WPA2-PSK (AES) or WPA3 if offered.",
                "Save the settings and reconnect every device with the new passphrase.",
                "Record the new passphrase in a password manager rather than on paper.",
            ]
        )
        if info.open_ports and 80 in info.open_ports:
            steps.append(
                "This router still serves plain HTTP. If it offers HTTPS, prefer it, "
                "and never use the administrator page on a public network."
            )
        return steps

    def reset_guidance(self) -> list[str]:
        return [
            "A factory reset erases every setting: the Wi-Fi name and password, the "
            "administrator password, port forwarding, DHCP reservations, VPN settings "
            "and any ISP configuration stored on the device.",
            "With some ISP-supplied routers a reset also removes the credentials that "
            "authenticate you to the provider, which can leave you without internet "
            "until support re-provisions the device.",
            "Before resetting, note down any settings you need to restore.",
            "Hold the recessed Reset button for about 10 seconds with the router powered on "
            "until the status LEDs blink, then wait for it to restart (1-2 minutes).",
            "After the reset, connect to the default Wi-Fi name printed on the label and "
            "complete the setup wizard, choosing a strong new password.",
            "If the router was supplied by your ISP and the reset leaves it without "
            "internet access, contact the provider before doing anything else.",
        ]

    def change_password_guidance(self) -> list[str]:
        return [
            "Sign in to the router's administration page as an administrator.",
            "Go to Wireless -> Security (the exact wording differs per vendor).",
            "Choose WPA2-PSK (AES) or WPA3-Personal as the security mode.",
            "Enter a new passphrase of at least 16 random characters, or a four- to "
            "six-word passphrase; generate one in the Password Laboratory.",
            "Save/Apply. The router restarts its wireless service and existing devices "
            "must reconnect with the new passphrase.",
            "If the router has a separate administrator password, change that too and "
            "store both in a password manager.",
        ]
