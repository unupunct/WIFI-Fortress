"""Safe subprocess execution.

Every external command in WiFi Fortress goes through :func:`run` or
:class:`CommandRunner`.  The rules enforced here:

* Commands are always argument **lists**; nothing is passed through a shell.
* Arguments are validated and control characters are rejected.
* Untrusted values (SSIDs, BSSIDs, interface names) are only ever passed as a
  single argument and are additionally sanitised for interface names.
* A timeout is mandatory, output is decoded defensively and truncated.
* Cancellation is cooperative through :class:`CancelToken`.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from wififortress.core.redaction import redact_text, strip_control_chars

DEFAULT_TIMEOUT = 30.0
MAX_OUTPUT_BYTES = 4 * 1024 * 1024

_IFACE_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,32}$")
_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_SAFE_ARG_RE = re.compile(r"^[^\x00-\x1f\x7f]*$")


class CommandError(RuntimeError):
    """Raised for invalid command construction."""


class CancelledError(RuntimeError):
    """Raised when an operation is cancelled by the user."""


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    timed_out: bool = False
    cancelled: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.cancelled

    @property
    def command_line(self) -> str:
        return " ".join(self.argv)

    def first_line(self) -> str:
        for stream in (self.stderr, self.stdout):
            for line in stream.splitlines():
                line = line.strip()
                if line:
                    return line
        return ""

    def summary(self, limit: int = 400) -> str:
        text = self.first_line() or f"exit code {self.returncode}"
        return text[:limit]


class CancelToken:
    """Cooperative cancellation flag shared with worker threads."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError("Operation cancelled")


def validate_interface_name(name: str) -> str:
    """Validate a wireless interface name (e.g. ``wlan0``, ``wlx0011...``)."""
    if not name or not _IFACE_RE.match(name):
        raise CommandError(f"Invalid interface name: {name!r}")
    return name


def validate_mac(mac: str) -> str:
    if not _MAC_RE.match(mac or ""):
        raise CommandError(f"Invalid MAC address: {mac!r}")
    return mac


_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,253})[A-Za-z0-9]$")
_IPV6_RE = re.compile(r"^[0-9A-Fa-f:]{2,45}$")


def validate_target(target: str) -> str:
    """Validate a host name or IP address used as a command argument."""
    if not target or len(target) > 255:
        raise CommandError(f"Invalid target: {target!r}")
    if not (_HOST_RE.match(target) or _IPV6_RE.match(target)):
        raise CommandError(f"Invalid target: {target!r}")
    return target


def validate_argv(argv: Sequence[str]) -> list[str]:
    """Reject control characters and empty programs."""
    if not argv:
        raise CommandError("Empty command")
    cleaned: list[str] = []
    for arg in argv:
        if not isinstance(arg, str):
            raise CommandError(f"Non-string argument: {arg!r}")
        if not _SAFE_ARG_RE.match(arg):
            raise CommandError(f"Argument contains control characters: {arg!r}")
        cleaned.append(arg)
    return cleaned


def which(program: str) -> str | None:
    """Return the resolved path of ``program`` or ``None``."""
    return shutil.which(program)


def program_available(program: str) -> bool:
    return which(program) is not None


def run(
    argv: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    token: CancelToken | None = None,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    check_available: bool = True,
) -> CommandResult:
    """Run a command safely and return a :class:`CommandResult`.

    Never raises for a failing program: the failure is reported in the
    result.  ``CommandError`` is raised only for invalid construction.
    """
    args = validate_argv(argv)
    if check_available and not which(args[0]):
        return CommandResult(
            argv=args,
            returncode=127,
            error=f"Program not found: {args[0]}",
            stderr=f"{args[0]}: command not found",
        )
    if token and token.cancelled:
        return CommandResult(argv=args, returncode=-1, cancelled=True)

    run_env = os.environ.copy()
    run_env.setdefault("LC_ALL", "C.UTF-8")
    run_env.setdefault("LANG", "C.UTF-8")
    if env:
        run_env.update(env)

    started = time.monotonic()
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "stdin": subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        "env": run_env,
        "cwd": cwd,
        "shell": False,
        "text": False,
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:  # pragma: no cover - Windows dev hosts
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.Popen(args, **kwargs)  # noqa: S603 - list argv, no shell
    except OSError as exc:
        return CommandResult(
            argv=args, returncode=126, error=str(exc), duration=time.monotonic() - started
        )

    timed_out = False
    cancelled = False
    stdout_b = b""
    stderr_b = b""
    try:
        while True:
            if token and token.cancelled:
                cancelled = True
                _terminate(proc)
                break
            try:
                stdout_b, stderr_b = proc.communicate(
                    input=input_text.encode("utf-8") if input_text is not None else None,
                    timeout=0.25,
                )
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - started > timeout:
                    timed_out = True
                    _terminate(proc)
                    stdout_b, stderr_b = proc.communicate()
                    break
    except Exception as exc:  # pragma: no cover - defensive
        _terminate(proc)
        return CommandResult(
            argv=args,
            returncode=proc.returncode or -1,
            error=str(exc),
            duration=time.monotonic() - started,
        )

    duration = time.monotonic() - started
    stdout = _decode(stdout_b)
    stderr = _decode(stderr_b)
    error = None
    if timed_out:
        error = f"Timed out after {timeout:.0f}s"
    elif cancelled:
        error = "Cancelled"
    return CommandResult(
        argv=args,
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
        duration=duration,
        timed_out=timed_out,
        cancelled=cancelled,
        error=error,
    )


def _terminate(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:  # pragma: no cover
            proc.terminate()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=2)
    except Exception:  # pragma: no cover
        try:
            proc.kill()
        except Exception:
            pass


def _decode(raw: bytes) -> str:
    if not raw:
        return ""
    if len(raw) > MAX_OUTPUT_BYTES:
        raw = raw[:MAX_OUTPUT_BYTES]
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        text = raw.decode("utf-8", errors="replace")
    return strip_control_chars(redact_text(text))


def run_sequence(
    commands: Iterable[Sequence[str]],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    token: CancelToken | None = None,
) -> list[CommandResult]:
    """Run several commands, stopping at the first cancellation."""
    results: list[CommandResult] = []
    for argv in commands:
        if token and token.cancelled:
            break
        results.append(run(argv, timeout=timeout, token=token))
    return results


@dataclass
class CommandRunner:
    """Thin object wrapper used by services that need a shared token."""

    token: CancelToken = field(default_factory=CancelToken)
    timeout: float = DEFAULT_TIMEOUT

    def run(self, argv: Sequence[str], **kwargs) -> CommandResult:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("token", self.token)
        return run(argv, **kwargs)
