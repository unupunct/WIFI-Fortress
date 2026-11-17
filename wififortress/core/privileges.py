"""Privilege handling.

WiFi Fortress never runs its GUI as root.  Operations that genuinely need
elevation (setting an interface down/up, changing regulatory settings,
reading root-only keyfiles) request it per operation through ``pkexec`` or
``sudo`` - whichever the desktop provides - and nothing else.

The application refuses to start as root unless explicitly overridden, and
it reports the exact permission problem instead of failing silently.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from wififortress.core.process import CommandResult, run, which


class PrivilegeError(RuntimeError):
    """Raised when an operation needs elevation that is not available."""


@dataclass(frozen=True)
class ElevationInfo:
    available: bool
    method: str  # "pkexec", "sudo", or "none"
    path: str = ""
    reason: str = ""

    @property
    def label(self) -> str:
        if not self.available:
            return "Elevation unavailable"
        return f"Elevation via {self.method}"


def is_root() -> bool:
    if os.name != "posix":
        return False
    try:
        return os.geteuid() == 0
    except AttributeError:  # pragma: no cover
        return False


def detect_elevation() -> ElevationInfo:
    """Find a non-interactive-capable elevation helper."""
    if is_root():
        return ElevationInfo(True, "root", reason="Running as root")
    pkexec = which("pkexec")
    if pkexec:
        return ElevationInfo(True, "pkexec", pkexec)
    sudo = which("sudo")
    if sudo:
        # ``sudo -n true`` tells us whether a cached credential exists.
        probe = run([sudo, "-n", "true"], timeout=3)
        if probe.ok:
            return ElevationInfo(True, "sudo", sudo)
        return ElevationInfo(
            False,
            "sudo",
            sudo,
            reason="sudo is installed but no cached credential; "
            "a password prompt cannot be shown from the GUI.",
        )
    return ElevationInfo(False, "none", reason="Neither pkexec nor sudo is installed.")


def elevation_argv(argv: list[str], info: ElevationInfo | None = None) -> list[str]:
    """Wrap ``argv`` so it runs elevated."""
    info = info or detect_elevation()
    if is_root():
        return list(argv)
    if not info.available:
        raise PrivilegeError(info.reason or "No elevation method available")
    if info.method == "pkexec":
        # --disable-internal-agent keeps the desktop agent in charge of the
        # password dialog so the GUI is never blocked by a terminal prompt.
        return [info.path, "--disable-internal-agent", *argv]
    if info.method == "sudo":
        return [info.path, "-n", *argv]
    return list(argv)


def run_elevated(argv: list[str], *, timeout: float = 30.0) -> CommandResult:
    """Run a single command with elevation.  Raises PrivilegeError if none."""
    info = detect_elevation()
    if not info.available:
        raise PrivilegeError(
            f"{info.reason} Install polkit (pkexec) or configure passwordless "
            "sudo for the required commands to use this feature."
        )
    return run(elevation_argv(argv, info), timeout=timeout)


def can_read(path: str) -> bool:
    try:
        return os.access(path, os.R_OK)
    except OSError:  # pragma: no cover
        return False


def permission_hint(path: str) -> str:
    """Human explanation of why a path cannot be read."""
    if can_read(path):
        return ""
    if is_root():
        return f"{path} is not readable even as root; check the file mode."
    return (
        f"{path} is not readable by the current user. Wi-Fi Fortress only reads "
        "profiles that your own user account is authorised for; for system-wide "
        "profiles an administrator must grant access."
    )
