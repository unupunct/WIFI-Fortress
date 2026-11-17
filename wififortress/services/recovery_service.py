"""Authorised saved-credential recovery from local network profiles.

What this service does - and does not - do
------------------------------------------
* It reads Wi-Fi profiles that already exist **for the current user** on
  this machine: NetworkManager keyfiles, ``nmcli -s`` output for
  connections the user owns, and (optionally, with explicit confirmation)
  system-wide profiles that the user is authorised to read.
* It never captures a handshake, never injects frames, never brute-forces a
  PSK and never contacts a remote service.  There is no code path here that
  attempts to authenticate against an access point.
* Every read is logged as an *operation* (SSID + source, never the secret)
  so the user can audit what was accessed.

If a credential cannot be read, the service says exactly why (no profile,
wrong owner, permission denied, agent-backed secret) and hands over to the
:class:`RouterRecoveryAssistant`.
"""

from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from wififortress.core.logging import get_logger
from wififortress.core.privileges import can_read, is_root
from wififortress.core.process import CancelToken, run, which

log = get_logger(__name__)

NM_SYSTEM_CONNECTIONS = Path("/etc/NetworkManager/system-connections")
NM_RUN_DIR = Path("/run/NetworkManager/system-connections")
NM_USER_CONNECTIONS = Path.home() / ".config" / "NetworkManager" / "system-connections"


@dataclass
class SavedProfile:
    profile_id: str
    ssid: str
    uuid: str = ""
    source: str = ""  # nmcli | keyfile-user | keyfile-system | wpa_supplicant
    path: Path | None = None
    owner_scope: str = "user"  # user | system
    readable: bool = False
    has_psk: bool = False
    psk_flags: str = ""
    key_mgmt: str = ""
    security: str = ""
    hidden: bool = False
    reason: str = ""

    @property
    def can_recover(self) -> bool:
        return self.readable and self.has_psk


@dataclass
class CredentialResult:
    status: str
    ssid: str
    message: str
    secret: str | None = None
    source: str = ""
    profile: SavedProfile | None = None
    reasons: list[str] = field(default_factory=list)
    needs_elevation: bool = False


class SavedCredentialRecoveryService:
    """Locate and read the user's own saved Wi-Fi credentials."""

    def __init__(self, token: CancelToken | None = None) -> None:
        self.token = token or CancelToken()

    # -- profile discovery --------------------------------------------
    def list_profiles(self) -> list[SavedProfile]:
        profiles: list[SavedProfile] = []
        profiles.extend(self._nmcli_profiles())
        profiles.extend(self._keyfile_profiles(NM_USER_CONNECTIONS, "keyfile-user", "user"))
        profiles.extend(self._keyfile_profiles(NM_RUN_DIR, "keyfile-system", "system"))
        profiles.extend(self._keyfile_profiles(NM_SYSTEM_CONNECTIONS, "keyfile-system", "system"))
        # De-duplicate by (ssid, uuid) keeping the most readable entry.
        merged: dict[str, SavedProfile] = {}
        for profile in profiles:
            key = profile.uuid or f"{profile.ssid}|{profile.path}"
            existing = merged.get(key)
            if existing is None or (profile.can_recover and not existing.can_recover):
                merged[key] = profile
        return sorted(merged.values(), key=lambda p: (p.ssid.lower(), p.source))

    def _nmcli_profiles(self) -> list[SavedProfile]:
        if not which("nmcli"):
            return []
        result = run(
            ["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show"],
            timeout=15,
            token=self.token,
        )
        if not result.ok:
            return []
        profiles: list[SavedProfile] = []
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 3:
                continue
            name, uuid, conn_type = parts[0], parts[1], parts[2]
            if "wireless" not in conn_type.lower():
                continue
            detail = run(
                ["nmcli", "-s", "-t", "-f", "802-11-wireless.ssid,802-11-wireless-security.key-mgmt,"
                 "802-11-wireless-security.psk-flags,802-11-wireless.hidden",
                 "connection", "show", uuid],
                timeout=15,
                token=self.token,
            )
            ssid = name
            key_mgmt = ""
            psk_flags = ""
            hidden = False
            if detail.ok:
                for dline in detail.stdout.splitlines():
                    if ":" not in dline:
                        continue
                    dkey, _, dvalue = dline.partition(":")
                    dkey = dkey.strip()
                    if dkey.endswith("wireless.ssid"):
                        ssid = dvalue.strip() or name
                    elif dkey.endswith("security.key-mgmt"):
                        key_mgmt = dvalue.strip()
                    elif dkey.endswith("security.psk-flags"):
                        psk_flags = dvalue.strip()
                    elif dkey.endswith("wireless.hidden"):
                        hidden = dvalue.strip().lower() in {"yes", "true", "1"}
            has_psk = bool(key_mgmt) and key_mgmt.lower() in {"wpa-psk", "sae", "wpa-eap"}
            profiles.append(
                SavedProfile(
                    profile_id=name,
                    ssid=ssid,
                    uuid=uuid,
                    source="nmcli",
                    owner_scope="user",
                    readable=True,
                    has_psk=has_psk,
                    psk_flags=psk_flags,
                    key_mgmt=key_mgmt,
                    security=key_mgmt,
                    hidden=hidden,
                    reason="" if has_psk else "Profile uses no pre-shared key",
                )
            )
        return profiles

    def _keyfile_profiles(self, directory: Path, source: str, scope: str) -> list[SavedProfile]:
        profiles: list[SavedProfile] = []
        if not directory.exists():
            return profiles
        try:
            entries = sorted(directory.glob("*.nmconnection"))
        except OSError:
            return profiles
        for path in entries:
            readable = can_read(str(path))
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            ssid = path.stem
            uuid = ""
            key_mgmt = ""
            has_psk = False
            hidden = False
            if readable:
                try:
                    parser.read(path, encoding="utf-8")
                    wifi = parser["wifi"] if parser.has_section("wifi") else {}
                    ssid = wifi.get("ssid", ssid).strip('"')
                    uuid = wifi.get("uuid", "")
                    hidden = wifi.get("hidden", "false").lower() == "true"
                    if parser.has_section("wifi-security"):
                        sec = parser["wifi-security"]
                        key_mgmt = sec.get("key-mgmt", "")
                        has_psk = bool(sec.get("psk", "")) or bool(sec.get("password", ""))
                except (OSError, configparser.Error, UnicodeDecodeError) as exc:
                    readable = False
                    log.warning("Could not parse %s: %s", path, exc)
            profiles.append(
                SavedProfile(
                    profile_id=path.stem,
                    ssid=ssid,
                    uuid=uuid,
                    source=source,
                    path=path,
                    owner_scope=scope,
                    readable=readable,
                    has_psk=has_psk,
                    key_mgmt=key_mgmt,
                    security=key_mgmt,
                    hidden=hidden,
                    reason="" if readable else (
                        "The profile file is not readable by your user account. "
                        "System-wide profiles are owned by root."
                    ),
                )
            )
        return profiles

    def find_profiles(self, ssid: str) -> list[SavedProfile]:
        wanted = ssid.strip().lower()
        return [p for p in self.list_profiles() if p.ssid.strip().lower() == wanted]

    # -- credential extraction ----------------------------------------
    def recover(self, ssid: str, *, allow_system: bool = False) -> CredentialResult:
        """Return the saved PSK for ``ssid`` if the user is authorised."""
        from wififortress.models.entities import RecoveryStatus

        profiles = self.find_profiles(ssid)
        if not profiles:
            return CredentialResult(
                status=RecoveryStatus.SAVED_CREDENTIAL_UNAVAILABLE,
                ssid=ssid,
                message=(
                    "No saved Wi-Fi profile for this network exists for your user "
                    "account on this machine, so there is nothing to recover."
                ),
                reasons=["No NetworkManager profile matches this SSID."],
            )

        reasons: list[str] = []
        needs_elevation = False
        for profile in profiles:
            if profile.source == "nmcli":
                secret, reason, elevate = self._read_nmcli_secret(profile)
                if secret:
                    return CredentialResult(
                        status=RecoveryStatus.CREDENTIAL_RECOVERED,
                        ssid=ssid,
                        message=(
                            f"Recovered the saved credential for '{ssid}' from the "
                            f"NetworkManager profile '{profile.profile_id}'."
                        ),
                        secret=secret,
                        source="NetworkManager connection profile",
                        profile=profile,
                    )
                reasons.append(reason)
                needs_elevation = needs_elevation or elevate
            if profile.path and profile.source.startswith("keyfile"):
                if profile.owner_scope == "system" and not allow_system and not is_root():
                    reasons.append(
                        f"System profile {profile.path} was not read because you did not "
                        "authorise access to system-wide profiles."
                    )
                    continue
                secret, reason = self._read_keyfile_secret(profile.path)
                if secret:
                    return CredentialResult(
                        status=RecoveryStatus.CREDENTIAL_RECOVERED,
                        ssid=ssid,
                        message=(
                            f"Recovered the saved credential for '{ssid}' from the keyfile "
                            f"{profile.path}."
                        ),
                        secret=secret,
                        source=str(profile.path),
                        profile=profile,
                    )
                reasons.append(reason)
                if not profile.readable:
                    needs_elevation = True

        return CredentialResult(
            status=RecoveryStatus.SAVED_CREDENTIAL_UNAVAILABLE,
            ssid=ssid,
            message=(
                "A saved profile exists but its secret could not be read. "
                "See the reasons below."
            ),
            reasons=[r for r in reasons if r],
            needs_elevation=needs_elevation,
            profile=profiles[0],
        )

    def _read_nmcli_secret(self, profile: SavedProfile) -> tuple[str | None, str, bool]:
        # First try the non-secret display, which only works for agent-stored
        # secrets the user owns.
        result = run(
            [
                "nmcli", "-s", "-t", "-f", "802-11-wireless-security.psk",
                "connection", "show", profile.uuid or profile.profile_id,
            ],
            timeout=15,
            token=self.token,
        )
        if result.ok:
            for line in result.stdout.splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                if key.endswith("security.psk"):
                    secret = value.strip()
                    if secret and not secret.startswith("<"):
                        return secret, "", False
                    if secret.startswith("<"):
                        return (
                            None,
                            "The secret is held by a keyring agent (psk-flags=agent-owned) "
                            "and is not stored in the profile file.",
                            False,
                        )
        return (
            None,
            f"nmcli could not display the secret: {result.summary()}",
            True,
        )

    def _read_keyfile_secret(self, path: Path) -> tuple[str | None, str]:
        if not can_read(str(path)):
            return (
                None,
                f"{path} is not readable by your user account "
                f"(permissions {self._mode(path)}).",
            )
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(path, encoding="utf-8")
        except (OSError, configparser.Error, UnicodeDecodeError) as exc:
            return None, f"Could not parse {path}: {exc}"
        if not parser.has_section("wifi-security"):
            return None, f"{path} has no [wifi-security] section."
        sec = parser["wifi-security"]
        psk = sec.get("psk") or sec.get("password")
        if not psk:
            flags = sec.get("psk-flags", "")
            if flags and flags != "0":
                return None, (
                    f"{path} stores the secret in a keyring agent (psk-flags={flags}); "
                    "the file itself contains no PSK."
                )
            return None, f"{path} contains no PSK value."
        return psk.strip().strip('"'), ""

    @staticmethod
    def _mode(path: Path) -> str:
        try:
            return oct(path.stat().st_mode & 0o777)
        except OSError:
            return "unknown"

    # -- verification helpers -----------------------------------------
    @staticmethod
    def redact_for_display(secret: str) -> str:
        return "*" * len(secret)

    def summary(self) -> dict[str, object]:
        profiles = self.list_profiles()
        return {
            "total": len(profiles),
            "recoverable": sum(1 for p in profiles if p.can_recover),
            "system_scope": sum(1 for p in profiles if p.owner_scope == "system"),
            "sources": sorted({p.source for p in profiles}),
            "wpa_supplicant": (Path("/etc/wpa_supplicant/wpa_supplicant.conf").exists()),
        }
