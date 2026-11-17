"""Secret redaction for structured logs.

Every log record passes through :func:`redact_text`.  The redactor removes
values that look like Wi-Fi passwords, PSKs, pre-shared keys and generic
``key=value`` credentials so that a log file can be shared for support
without leaking secrets.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***REDACTED***"

# key=value / key: value pairs whose key names a secret.
_SECRET_KEY_RE = re.compile(
    r"(?i)\b("
    r"psk|passphrase|password|passwd|pwd|secret|token|api[_-]?key|"
    r"wpa[_-]?psk|wifi[_-]?password|auth[_-]?key|private[_-]?key"
    r")\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)

# ``psk=value`` lines as printed by NetworkManager keyfile tooling, and the
# space separated ``wpa-psk <value>`` form used in configuration files.
_KEYFILE_RE = re.compile(
    r"(?im)^(psk|password|wep-key[0-9]?)\s*=\s*(.+)$"
)
_SPACE_SECRET_RE = re.compile(
    r"(?i)\b(psk|passphrase|password|passwd|wpa-psk|wpa_psk|secret)"
    r"([ \t]+)(\"[^\"]*\"|'[^']*'|\S+)"
)

# A bare hex PSK (64 hex chars) or long base64-looking blob.
_HEX_PSK_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
# 8-63 printable characters that appear right after a quote in a secret context.
_QUOTED_SECRET_RE = re.compile(r"(?i)(psk\s*=\s*)\"[^\"]{8,64}\"")

# WPA handshake / PMKID hex blobs used by hcxdumptool output.
_HCXPcapng_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b(?=:\s*handshake)", re.IGNORECASE)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def redact_text(text: str) -> str:
    """Return ``text`` with secrets replaced by ``***REDACTED***``."""
    if not text:
        return text
    out = _KEYFILE_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    out = _SECRET_KEY_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", out)
    out = _SPACE_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
    out = _QUOTED_SECRET_RE.sub(lambda m: f"{m.group(1)}\"{REDACTED}\"", out)
    out = _HEX_PSK_RE.sub(REDACTED, out)
    out = _HCXPcapng_RE.sub(REDACTED, out)
    return out


def redact_value(value: Any) -> Any:
    """Recursively redact strings inside common containers."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_value(v) for v in value)
    return value


def strip_control_chars(text: str) -> str:
    """Remove control characters from untrusted tool output."""
    return _CONTROL_RE.sub("", text)


def mask_secret(secret: str, keep: int = 2) -> str:
    """Mask a secret for display: keep first/last character only."""
    if not secret:
        return ""
    if len(secret) <= keep * 2:
        return "*" * len(secret)
    return secret[:keep] + "*" * (len(secret) - keep * 2) + secret[-keep:]


_SECRET_KEY_NAMES = {
    "psk", "passphrase", "password", "passwd", "pwd", "secret", "token",
    "apikey", "api_key", "api-key", "wpa-psk", "wpa_psk", "wifi-password",
    "wifi_password", "auth-key", "auth_key", "private-key", "private_key",
    "wep-key", "wep_key", "credential", "credentials", "key",
}


def is_secret_key(key: str) -> bool:
    """Whether a mapping key names a secret and must not be persisted."""
    return key.strip().lower().replace(" ", "") in _SECRET_KEY_NAMES


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop secret keys and redact secret-looking values in a mapping."""
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        if is_secret_key(str(key)):
            continue
        out[key] = redact_value(value)
    return out


def sanitize_command(argv: list[str]) -> list[str]:
    """Return an argument list that is safe to log.

    Arguments are kept verbatim except where the previous argument names a
    secret (``--password hunter2``) or the argument itself is a ``key=value``
    secret; those values are replaced.
    """
    result: list[str] = []
    hide_next = False
    for arg in argv:
        if hide_next:
            result.append(REDACTED)
            hide_next = False
            continue
        if is_secret_key(arg):
            # A bare ``psk`` argument names a secret; the next one is its value.
            result.append(arg)
            hide_next = True
            continue
        if arg.startswith("-") and is_secret_key(arg.lstrip("-")):
            result.append(arg)
            hide_next = True
            continue
        result.append(redact_text(arg))
    return result
