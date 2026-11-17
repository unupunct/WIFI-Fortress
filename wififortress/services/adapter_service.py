"""Adapter discovery and management.

Sources, in order of preference:

1. ``iw dev`` / ``iw phy`` / ``iw list`` - authoritative nl80211 view of
   interface state, supported frequencies and interface modes.
2. ``ip -details link show`` - driver name and bus information.
3. ``/sys/class/net/<iface>/`` - MAC address, operational state, driver link.
4. ``ethtool -i`` and ``ethtool -k`` - driver version and feature flags.
5. ``rfkill list`` - radio soft/hard block state.
6. ``nmcli`` - whether the interface is currently connected and to which SSID.
7. ``/sys/class/net/<iface>/device/{vendor,device}`` plus the PCI/USB ID
   databases (``pci.ids``, ``usb.ids``) for manufacturer and model.

Nothing is guessed: a capability is only reported as supported when the
kernel or a tool actually advertises it.  Otherwise the state is
"Not verified".
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from wififortress.core.logging import get_logger
from wififortress.core.process import CancelToken, run, which
from wififortress.models.entities import AdapterInfo, CapabilityState

log = get_logger(__name__)

SYS_NET = Path("/sys/class/net")
PCI_IDS = Path("/usr/share/misc/pci.ids")
PCI_IDS_ALT = Path("/usr/share/hwdata/pci.ids")
USB_IDS = Path("/usr/share/misc/usb.ids")
USB_IDS_ALT = Path("/usr/share/hwdata/usb.ids")


@dataclass
class AdapterDiscoveryResult:
    adapters: list[AdapterInfo]
    tools_available: dict[str, bool]
    notes: list[str]
    is_linux: bool


class IdDatabase:
    """Minimal reader for the pci.ids / usb.ids vendor databases."""

    def __init__(self, paths: list[Path]) -> None:
        self._vendors: dict[str, str] = {}
        self._devices: dict[tuple[str, str], str] = {}
        self._loaded_from: Path | None = None
        for path in paths:
            if path.exists():
                try:
                    self._load(path)
                    self._loaded_from = path
                    break
                except OSError as exc:  # pragma: no cover
                    log.warning("Cannot read id database %s: %s", path, exc)

    def _load(self, path: Path) -> None:
        current_vendor = ""
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip() or line.startswith("#"):
                    continue
                if not line.startswith("\t"):
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        current_vendor = parts[0].lower()
                        self._vendors[current_vendor] = parts[1].strip()
                elif line.startswith("\t\t"):
                    continue
                else:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and current_vendor:
                        self._devices[(current_vendor, parts[0].lower())] = parts[1].strip()

    @property
    def loaded(self) -> bool:
        return self._loaded_from is not None

    @property
    def source(self) -> str:
        return str(self._loaded_from) if self._loaded_from else "not installed"

    def vendor(self, vendor_id: str) -> str:
        return self._vendors.get(vendor_id.lower(), "")

    def device(self, vendor_id: str, device_id: str) -> str:
        return self._devices.get((vendor_id.lower(), device_id.lower()), "")


class AdapterService:
    """Discover and manage wireless adapters."""

    def __init__(self, token: CancelToken | None = None) -> None:
        self.token = token or CancelToken()
        self._pci_ids = IdDatabase([PCI_IDS, PCI_IDS_ALT])
        self._usb_ids = IdDatabase([USB_IDS, USB_IDS_ALT])
        self._last_phy_map: dict[str, str] = {}

    # -- discovery -----------------------------------------------------
    @property
    def is_linux(self) -> bool:
        return os.name == "posix" and Path("/proc/net").exists()

    def tools(self) -> dict[str, bool]:
        return {
            name: which(name) is not None
            for name in ("iw", "ip", "rfkill", "nmcli", "ethtool", "modinfo")
        }

    def discover(self) -> AdapterDiscoveryResult:
        notes: list[str] = []
        tools = self.tools()
        if not self.is_linux:
            return AdapterDiscoveryResult(
                [], tools, ["Adapter discovery requires Linux (Parrot OS)."], False
            )
        if not tools["iw"]:
            notes.append(
                "iw is not installed: adapter capabilities cannot be verified. "
                "Install it with: sudo apt install iw"
            )

        interfaces = self._wireless_interfaces(tools, notes)
        phy_info = self._parse_iw_dev() if tools["iw"] else {}
        phy_caps = self._parse_iw_list() if tools["iw"] else {}
        rfkill = self._parse_rfkill() if tools["rfkill"] else {}
        nm_state = self._nmcli_state() if tools["nmcli"] else {}

        adapters: list[AdapterInfo] = []
        for iface in interfaces:
            if self.token.cancelled:
                break
            adapter = self._build_adapter(iface, phy_info, phy_caps, rfkill, nm_state, tools)
            adapters.append(adapter)
        adapters.sort(key=lambda a: a.interface)
        if not adapters:
            notes.append(
                "No wireless interfaces were found. Check that the adapter is "
                "connected and that its driver is loaded (dmesg | grep -i firmware)."
            )
        return AdapterDiscoveryResult(adapters, tools, notes, True)

    def _wireless_interfaces(self, tools: dict[str, bool], notes: list[str]) -> list[str]:
        found: list[str] = []
        if tools["iw"]:
            result = run(["iw", "dev"], timeout=10, token=self.token)
            if result.ok:
                found.extend(re.findall(r"^\s*Interface (\S+)", result.stdout, re.M))
            elif result.returncode == 127:
                notes.append("iw is not installed.")
            else:
                notes.append(f"iw dev failed: {result.summary()}")
        if SYS_NET.exists():
            for entry in sorted(SYS_NET.iterdir()):
                name = entry.name
                if name == "lo":
                    continue
                if (entry / "wireless").exists() or (entry / "phy80211").exists():
                    if name not in found:
                        found.append(name)
        if tools["nmcli"]:
            result = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"], timeout=10, token=self.token)
            if result.ok:
                for line in result.stdout.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2 and parts[1].strip() == "wifi":
                        if parts[0].strip() not in found:
                            found.append(parts[0].strip())
        return found

    def _parse_iw_dev(self) -> dict[str, dict[str, str]]:
        result = run(["iw", "dev"], timeout=10, token=self.token)
        if not result.ok:
            return {}
        info: dict[str, dict[str, str]] = {}
        current = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Interface "):
                current = stripped.split(None, 1)[1]
                info[current] = {}
                continue
            if current is None:
                continue
            if stripped.startswith("wiphy "):
                info[current]["phy"] = f"phy{stripped.split()[1]}"
            elif stripped.startswith("addr "):
                info[current]["mac"] = stripped.split()[1]
            elif stripped.startswith("ssid "):
                info[current]["ssid"] = stripped.split(None, 1)[1]
            elif stripped.startswith("type "):
                info[current]["type"] = stripped.split(None, 1)[1]
            elif stripped.startswith("channel "):
                info[current]["channel"] = stripped.split(None, 1)[1]
        for iface, data in info.items():
            if "phy" in data:
                self._last_phy_map[data["phy"]] = iface
        return info

    def _parse_iw_list(self) -> dict[str, dict]:
        """Parse ``iw list`` into per-phy capability dictionaries."""
        result = run(["iw", "list"], timeout=20, token=self.token)
        if not result.ok:
            return {}
        phy_caps: dict[str, dict] = {}
        current_phy = None
        current_band = None
        in_iface_modes = False
        for raw in result.stdout.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if stripped.startswith("Wiphy "):
                current_phy = f"phy{stripped.split()[1]}"
                phy_caps[current_phy] = {
                    "bands": {},
                    "modes": [],
                    "frequencies": [],
                    "monitor_supported": False,
                    "monitor_evidence": [],
                    "vendor": "",
                }
                in_iface_modes = False
                continue
            if current_phy is None:
                continue
            caps = phy_caps[current_phy]
            if stripped.startswith("Supported interface modes"):
                in_iface_modes = True
                continue
            if in_iface_modes:
                if stripped.startswith("* "):
                    mode = stripped[2:].strip()
                    caps["modes"].append(mode)
                    if "monitor" in mode.lower():
                        caps["monitor_supported"] = True
                        caps["monitor_evidence"].append("iw list: supported interface mode 'monitor'")
                    continue
                in_iface_modes = False
            band_match = re.match(r"Band (\d+):", stripped)
            if band_match:
                current_band = f"Band {band_match.group(1)}"
                caps["bands"][current_band] = {"frequencies": []}
                continue
            freq_match = re.match(r"\* (\d{4,5})(?:\.\d+)? MHz \[(\d+)\]", stripped)
            if freq_match and current_band:
                freq = int(freq_match.group(1))
                channel = int(freq_match.group(2))
                caps["frequencies"].append(freq)
                caps["bands"][current_band]["frequencies"].append((freq, channel))
                continue
            if stripped.startswith("Device supports") and "monitor" in stripped.lower():
                caps["monitor_evidence"].append(f"iw list: {stripped}")
            if stripped.startswith("vendor:"):
                caps["vendor"] = stripped.split(":", 1)[1].strip()
        return phy_caps

    def _parse_rfkill(self) -> dict[str, dict[str, bool]]:
        result = run(["rfkill", "list"], timeout=10, token=self.token)
        state: dict[str, dict[str, bool]] = {}
        if not result.ok:
            return state
        current = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("Soft", "Hard")):
                # A new device block starts.
                current = stripped
                state.setdefault(current, {"soft": False, "hard": False})
                continue
            if current and stripped.startswith("Soft blocked:"):
                state[current]["soft"] = stripped.endswith("yes")
            elif current and stripped.startswith("Hard blocked:"):
                state[current]["hard"] = stripped.endswith("yes")
        return state

    def _nmcli_state(self) -> dict[str, dict[str, str]]:
        result = run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"],
            timeout=10,
            token=self.token,
        )
        state: dict[str, dict[str, str]] = {}
        if not result.ok:
            return state
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 4 and parts[1] == "wifi":
                state[parts[0]] = {
                    "state": parts[2],
                    "connection": parts[3],
                }
        return state

    def _build_adapter(
        self,
        iface: str,
        phy_info: dict[str, dict[str, str]],
        phy_caps: dict[str, dict],
        rfkill: dict[str, dict[str, bool]],
        nm_state: dict[str, dict[str, str]],
        tools: dict[str, bool],
    ) -> AdapterInfo:
        adapter = AdapterInfo(interface=iface)
        dev_info = phy_info.get(iface, {})
        adapter.mac = dev_info.get("mac", "")
        adapter.phy = dev_info.get("phy", "")
        caps = phy_caps.get(adapter.phy, {}) if adapter.phy else {}

        # sysfs basics
        sys_dir = SYS_NET / iface
        if sys_dir.exists():
            try:
                adapter.state = (sys_dir / "operstate").read_text().strip()
            except OSError:
                pass
            try:
                flags = (sys_dir / "flags").read_text().strip()
                adapter.is_up = "UP" in flags
            except OSError:
                pass
            if not adapter.mac:
                try:
                    adapter.mac = (sys_dir / "address").read_text().strip()
                except OSError:
                    pass
            driver_link = sys_dir / "device" / "driver"
            if driver_link.exists():
                try:
                    adapter.driver = driver_link.resolve().name
                except OSError:
                    pass
            adapter.vendor, adapter.model, adapter.chipset, adapter.bus = self._device_ids(
                sys_dir / "device"
            )

        # driver version / problem
        if adapter.driver and tools["modinfo"]:
            mod = run(["modinfo", adapter.driver], timeout=10, token=self.token)
            if mod.ok:
                for line in mod.stdout.splitlines():
                    if line.startswith("version:"):
                        adapter.driver_version = line.split(":", 1)[1].strip()
                    elif line.startswith("firmware:"):
                        adapter.extra.setdefault("firmware", []).append(
                            line.split(":", 1)[1].strip()
                        )
            else:
                adapter.driver_problem = (
                    f"modinfo could not read module {adapter.driver}: {mod.summary()}"
                )
        if not adapter.driver:
            adapter.driver_problem = (
                "No driver is bound to this interface. The adapter may be in use by "
                "another driver, or the module failed to load."
            )

        if tools["ethtool"]:
            eth = run(["ethtool", "-i", iface], timeout=10, token=self.token)
            if eth.ok:
                for line in eth.stdout.splitlines():
                    key, _, value = line.partition(":")
                    key = key.strip()
                    if key == "driver" and not adapter.driver:
                        adapter.driver = value.strip()
                    elif key == "version" and not adapter.driver_version:
                        adapter.driver_version = value.strip()
                    elif key == "bus-info":
                        adapter.bus = value.strip() or adapter.bus

        # rfkill
        for key, blocked in rfkill.items():
            if iface in key:
                adapter.soft_blocked = blocked.get("soft", False)
                adapter.hard_blocked = blocked.get("hard", False)

        # NetworkManager connection state
        nm = nm_state.get(iface)
        if nm:
            adapter.is_connected = nm.get("state", "") == "connected"
            adapter.connection_ssid = nm.get("connection", "")
            adapter.extra["nm_state"] = nm.get("state", "")
        elif dev_info.get("ssid"):
            adapter.is_connected = True
            adapter.connection_ssid = dev_info["ssid"]

        # capabilities from iw list
        if caps:
            adapter.frequencies = sorted(set(caps.get("frequencies", [])))
            adapter.interface_modes = list(caps.get("modes", []))
            bands = []
            for band_name, band_data in caps.get("bands", {}).items():
                freqs = [f for f, _ in band_data.get("frequencies", [])]
                if any(2400 <= f < 2500 for f in freqs):
                    bands.append("2.4 GHz")
                if any(4900 <= f < 5925 for f in freqs):
                    bands.append("5 GHz")
                if any(5925 <= f < 7125 for f in freqs):
                    bands.append("6 GHz")
            adapter.bands = sorted(set(bands), key=["2.4 GHz", "5 GHz", "6 GHz"].index)
            if caps.get("monitor_supported"):
                adapter.monitor_mode = CapabilityState.SUPPORTED
                adapter.monitor_evidence = "; ".join(caps.get("monitor_evidence", []))
            else:
                adapter.monitor_mode = CapabilityState.UNSUPPORTED
                adapter.monitor_evidence = (
                    "iw list did not advertise a monitor interface mode for this phy"
                )
            ap_modes = [m for m in adapter.interface_modes if "AP" in m]
            adapter.ap_mode = (
                CapabilityState.SUPPORTED if ap_modes else CapabilityState.UNSUPPORTED
            )
            # Packet injection is never advertised by nl80211; it depends on the
            # out-of-tree driver (e.g. patched Atheros). We report it as unknown.
            adapter.packet_injection = CapabilityState.UNKNOWN
            adapter.standards = self._standards_from_modes(adapter.interface_modes, caps)
        else:
            adapter.monitor_mode = CapabilityState.UNKNOWN
            adapter.monitor_evidence = (
                "Capabilities not verified: iw list returned no data for this phy."
            )
            adapter.ap_mode = CapabilityState.UNKNOWN
            adapter.packet_injection = CapabilityState.UNKNOWN

        adapter.is_virtual = adapter.interface.startswith(("wlan1", "p2p", "veth")) and not adapter.bus
        return adapter

    @staticmethod
    def _standards_from_modes(modes: list[str], caps: dict) -> list[str]:
        standards = []
        has_5 = any(4900 <= f < 5925 for f in caps.get("frequencies", []))
        has_6 = any(5925 <= f < 7125 for f in caps.get("frequencies", []))
        # nl80211 does not report 802.11 revisions directly; bands imply them.
        standards.append("802.11b/g (2.4 GHz)")
        if has_5:
            standards.append("802.11a/n/ac (5 GHz)")
        if has_6:
            standards.append("802.11ax (6 GHz)")
        return standards

    def _device_ids(self, device_dir: Path) -> tuple[str, str, str, str]:
        """Resolve vendor/model/chipset/bus from sysfs + id databases."""
        vendor = ""
        model = ""
        chipset = ""
        bus = ""
        if not device_dir.exists():
            return vendor, model, chipset, bus
        try:
            real = device_dir.resolve()
        except OSError:
            return vendor, model, chipset, bus
        bus = "PCI" if "pci" in str(real) else "USB" if "usb" in str(real) else ""

        def read(name: str) -> str:
            try:
                return (device_dir / name).read_text().strip()
            except OSError:
                return ""

        vid = read("vendor").lower()
        did = read("device").lower()
        vid = vid[2:] if vid.startswith("0x") else vid
        did = did[2:] if did.startswith("0x") else did
        db = self._usb_ids if bus == "USB" else self._pci_ids
        if vid:
            vendor = db.vendor(vid) or f"vendor {vid}"
        if did:
            model = db.device(vid, did) or f"device {did}"
        chipset = model
        if not db.loaded:
            vendor = vendor or (f"vendor {vid}" if vid else "")
        return vendor, model, chipset, bus

    # -- management ----------------------------------------------------
    def set_interface_up(self, interface: str, up: bool, *, elevated: bool = False):
        """Bring an interface up or down.  Returns a CommandResult."""
        from wififortress.core.privileges import run_elevated

        argv = ["ip", "link", "set", "dev", interface, "up" if up else "down"]
        if elevated:
            return run_elevated(argv, timeout=15)
        return run(argv, timeout=15, token=self.token)

    def set_rfkill(self, interface: str, unblock: bool):
        from wififortress.core.privileges import run_elevated

        action = "unblock" if unblock else "block"
        return run_elevated(["rfkill", action, "wlan"], timeout=15)

    def restore_state(self, adapter: AdapterInfo, was_up: bool) -> str:
        """Restore the operational state recorded before an operation."""
        if adapter.is_up == was_up:
            return "Interface state unchanged."
        result = self.set_interface_up(adapter.interface, was_up, elevated=True)
        if result.ok:
            return f"Interface {adapter.interface} restored to {'up' if was_up else 'down'}."
        return f"Could not restore interface state: {result.summary()}"

    def permission_report(self) -> dict[str, str]:
        """Explain what the current user can and cannot do."""
        report: dict[str, str] = {}
        report["read"] = "Adapter information is readable by any local user."
        if os.name == "posix":
            try:
                uid = os.geteuid()
            except AttributeError:  # pragma: no cover
                uid = -1
            report["euid"] = str(uid)
            report["elevation"] = (
                "Changing interface state requires root; WiFi Fortress asks for "
                "elevation per operation via pkexec."
            )
        return report
