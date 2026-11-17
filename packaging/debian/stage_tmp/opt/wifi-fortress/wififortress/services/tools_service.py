"""Integration with the wireless utilities shipped by Parrot OS.

Each entry describes how to detect the tool, read its version, which
dependencies it needs and what the application may use it for.  Several
tools are listed for information only (hcxdumptool, the aircrack-ng attack
binaries): WiFi Fortress never launches them, and the UI says so.

Only documented interfaces are used, always with an argument list and no
shell.  Version detection runs a fixed, hard-coded argv per tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from wififortress.core.logging import get_logger
from wififortress.core.process import CancelToken, run, which
from wififortress.models.entities import ToolInfo

log = get_logger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    key: str
    name: str
    package: str
    description: str
    purpose: str
    version_argv: tuple[str, ...] = ()
    version_pattern: str = ""
    dependencies: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    restricted: bool = False
    restriction_note: str = ""
    install_hint: str = ""
    related_binaries: tuple[str, ...] = ()


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        key="iw",
        name="iw",
        package="iw",
        description="nl80211 wireless configuration and information utility.",
        purpose=(
            "Adapter capability discovery (iw list), interface state (iw dev) and "
            "network scanning (iw dev <iface> scan)."
        ),
        version_argv=("iw", "version"),
        dependencies=("libnl-3",),
        capabilities=("Interface inventory", "Capability report", "Active scan"),
        install_hint="sudo apt install iw",
    ),
    ToolSpec(
        key="iproute2",
        name="iproute2 (ip)",
        package="iproute2",
        description="Network interface, address and routing management.",
        purpose="Bring interfaces up/down and read the default gateway for diagnostics.",
        version_argv=("ip", "-V"),
        dependencies=(),
        capabilities=("Link state", "Addressing", "Routing table"),
        install_hint="sudo apt install iproute2",
    ),
    ToolSpec(
        key="networkmanager",
        name="NetworkManager (nmcli)",
        package="network-manager",
        description="Connection manager and profile store.",
        purpose=(
            "Read the user's own saved wireless profiles and their connection state; "
            "used by the Wi-Fi Recovery module."
        ),
        version_argv=("nmcli", "--version"),
        dependencies=("dbus",),
        capabilities=("Saved profiles", "Connection state", "Fallback scan list"),
        install_hint="sudo apt install network-manager",
    ),
    ToolSpec(
        key="rfkill",
        name="rfkill",
        package="rfkill",
        description="Radio block state management.",
        purpose="Report and change soft/hard block state of the wireless radio.",
        version_argv=("rfkill", "--version"),
        dependencies=(),
        capabilities=("Radio status", "Soft unblock"),
        install_hint="sudo apt install rfkill",
    ),
    ToolSpec(
        key="ethtool",
        name="ethtool",
        package="ethtool",
        description="Driver and feature information for network interfaces.",
        purpose="Driver name, version and bus information for the Adapter Manager.",
        version_argv=("ethtool", "--version"),
        dependencies=(),
        capabilities=("Driver info", "Bus info"),
        install_hint="sudo apt install ethtool",
    ),
    ToolSpec(
        key="wavemon",
        name="wavemon",
        package="wavemon",
        description="Curses-based wireless signal monitor.",
        purpose="Optional: signal history monitoring in a terminal.",
        version_argv=("wavemon", "-v"),
        dependencies=("libncurses",),
        capabilities=("Signal history",),
        install_hint="sudo apt install wavemon",
    ),
    ToolSpec(
        key="aircrack-ng",
        name="Aircrack-ng suite",
        package="aircrack-ng",
        description="Wireless auditing tool suite (monitor mode capture and analysis).",
        purpose=(
            "Detected for information: WiFi Fortress uses only the passive capture and "
            "analysis binaries (airodump-ng, airdecap-ng) to verify findings on your own "
            "network. Automated handshake capture workflows are not provided."
        ),
        version_argv=("aircrack-ng", "--help"),
        version_pattern=r"Aircrack-ng\s+([0-9][^\s\-]*)",
        dependencies=("libssl", "libnl-3"),
        capabilities=("Installation check", "Version", "Passive capture tooling"),
        restricted=True,
        restriction_note=(
            "No automated deauthentication, handshake capture, WPS brute force or "
            "password cracking workflow is exposed. Use these tools manually and only "
            "on networks you are authorised to test."
        ),
        install_hint="sudo apt install aircrack-ng",
        related_binaries=("airmon-ng", "airodump-ng", "airdecap-ng", "aireplay-ng"),
    ),
    ToolSpec(
        key="kismet",
        name="Kismet",
        package="kismet",
        description="Wireless detector, sniffer and intrusion detection system.",
        purpose=(
            "Detected for information: Kismet can be started manually for passive "
            "discovery and monitoring; WiFi Fortress does not drive it."
        ),
        version_argv=("kismet", "--version"),
        dependencies=("libpcap", "libnl-3"),
        capabilities=("Installation check", "Version"),
        restricted=True,
        restriction_note="Started manually only; no automatic launch from the application.",
        install_hint="sudo apt install kismet",
    ),
    ToolSpec(
        key="wireshark",
        name="Wireshark",
        package="wireshark",
        description="Graphical packet analyser.",
        purpose="Opened manually on capture files you produce; not launched automatically.",
        version_argv=("wireshark", "--version"),
        dependencies=("qt6", "libpcap"),
        capabilities=("Installation check", "Version"),
        install_hint="sudo apt install wireshark",
    ),
    ToolSpec(
        key="tshark",
        name="tshark",
        package="tshark",
        description="Command-line packet analyser.",
        purpose=(
            "Optional: summarise capture files. WiFi Fortress only runs fixed, "
            "documented tshark invocations against a file you select."
        ),
        version_argv=("tshark", "--version"),
        dependencies=("libpcap",),
        capabilities=("Capture summaries",),
        install_hint="sudo apt install tshark",
    ),
    ToolSpec(
        key="hcxdumptool",
        name="hcxdumptool",
        package="hcxdumptool",
        description="Tool for capturing PMKID/handshake material from the air.",
        purpose=(
            "Installation and compatibility information only. WiFi Fortress never "
            "invokes it."
        ),
        version_argv=("hcxdumptool", "--version"),
        dependencies=("libssl",),
        capabilities=("Installation check", "Version"),
        restricted=True,
        restriction_note=(
            "This tool captures authentication material. WiFi Fortress does not launch "
            "it under any circumstances."
        ),
        install_hint="sudo apt install hcxdumptool",
    ),
)


class WirelessToolIntegrationService:
    def __init__(self, token: CancelToken | None = None) -> None:
        self.token = token or CancelToken()
        self._cache: dict[str, ToolInfo] = {}

    def _spec_primary_binary(self, spec: ToolSpec) -> str:
        return spec.version_argv[0] if spec.version_argv else spec.key

    @staticmethod
    def binary_status(binary: str) -> tuple[bool, str]:
        """Whether one binary is installed, and its resolved path."""
        path = which(binary)
        return bool(path), path or ""

    def check(self, spec: ToolSpec) -> ToolInfo:
        binary = self._spec_primary_binary(spec)
        path = which(binary)
        info = ToolInfo(
            key=spec.key,
            name=spec.name,
            package=spec.package,
            description=spec.description,
            purpose=spec.purpose,
            installed=bool(path),
            path=path or "",
            version_command=list(spec.version_argv),
            dependencies=list(spec.dependencies),
            missing_dependencies=[d for d in spec.dependencies if not self._dependency_present(d)],
            capabilities=list(spec.capabilities),
            restricted=spec.restricted,
            restriction_note=spec.restriction_note,
            install_hint=spec.install_hint,
        )
        if path and spec.version_argv:
            result = run(list(spec.version_argv), timeout=10, token=self.token)
            text = f"{result.stdout}\n{result.stderr}"
            if spec.version_pattern:
                match = re.search(spec.version_pattern, text)
                info.version = match.group(1).strip() if match else ""
            else:
                info.version = self._extract_version(text)
            if not info.version and not result.ok:
                info.diagnostics = f"Version probe failed: {result.summary()}"
        elif not path:
            info.diagnostics = f"{binary} is not installed."
        if spec.related_binaries:
            found = [b for b in spec.related_binaries if which(b)]
            info.diagnostics = (
                ("Related binaries present: " + ", ".join(found))
                if found
                else "No related binaries found on PATH."
            )
        return info

    @staticmethod
    def _extract_version(text: str) -> str:
        match = re.search(r"(\d+\.\d+(?:\.\d+)?(?:[-~][A-Za-z0-9.]+)?)", text)
        return match.group(1) if match else ""

    @staticmethod
    def _dependency_present(name: str) -> bool:
        """Best-effort dependency check using ldconfig and dpkg."""
        candidates = [Path(f"/usr/lib/x86_64-linux-gnu/{name}.so"), Path(f"/lib/x86_64-linux-gnu/{name}.so")]
        if any(p.exists() for p in candidates):
            return True
        if which("ldconfig"):
            result = run(["ldconfig", "-p"], timeout=10)
            if result.ok and name.lower() in result.stdout.lower():
                return True
        if which("dpkg"):
            result = run(["dpkg", "-s", name], timeout=10)
            if result.ok:
                return True
        return False

    def discover_all(self) -> list[ToolInfo]:
        infos = [self.check(spec) for spec in TOOL_SPECS]
        self._cache = {info.key: info for info in infos}
        return infos

    def get(self, key: str) -> ToolInfo | None:
        if key not in self._cache:
            spec = next((s for s in TOOL_SPECS if s.key == key), None)
            if spec is None:
                return None
            self._cache[key] = self.check(spec)
        return self._cache.get(key)

    def spec(self, key: str) -> ToolSpec | None:
        return next((s for s in TOOL_SPECS if s.key == key), None)

    def summary(self) -> dict[str, int]:
        infos = list(self._cache.values()) or self.discover_all()
        return {
            "total": len(infos),
            "installed": sum(1 for i in infos if i.installed),
            "missing": sum(1 for i in infos if not i.installed),
            "restricted": sum(1 for i in infos if i.restricted),
        }

    def install_guidance(self) -> list[str]:
        missing = [i for i in (self._cache.values() or self.discover_all()) if not i.installed]
        return [f"sudo apt install {i.package}    # {i.name}" for i in missing]

    # -- the only permitted invocations --------------------------------
    def tshark_summary(self, capture: Path) -> str:
        """Summarise a capture file with a fixed tshark invocation."""
        if not which("tshark"):
            raise FileNotFoundError("tshark is not installed")
        if not capture.exists():
            raise FileNotFoundError(str(capture))
        result = run(
            ["tshark", "-r", str(capture), "-q", "-z", "io,phs"],
            timeout=120,
            token=self.token,
        )
        if not result.ok:
            raise RuntimeError(result.summary())
        return result.stdout

    def airodump_passive(
        self, interface: str, output_prefix: Path, seconds: int = 30
    ) -> str:
        """Passive discovery only: no deauthentication, no injection.

        Runs ``airodump-ng`` for a fixed number of seconds and returns the CSV
        path it produced.  The caller must have put the interface into monitor
        mode itself; WiFi Fortress never toggles monitor mode automatically.
        """
        if not which("airodump-ng"):
            raise FileNotFoundError("airodump-ng is not installed")
        result = run(
            [
                "timeout", str(int(seconds)),
                "airodump-ng", "--output-format", "csv",
                "--write", str(output_prefix), interface,
            ],
            timeout=seconds + 20,
            token=self.token,
        )
        csv_path = output_prefix.with_suffix(".csv")
        if not csv_path.exists():
            raise RuntimeError(result.summary() or "airodump-ng produced no output")
        return str(csv_path)
