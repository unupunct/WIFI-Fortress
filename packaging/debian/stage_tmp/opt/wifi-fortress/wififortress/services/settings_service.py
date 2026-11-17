"""Settings service: JSON-backed user preferences.

The settings file lives in ``~/.config/wifi-fortress/settings.json``.  Writes
are atomic (temp file + replace) and the schema is versioned so that future
releases can migrate old files.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from wififortress.core.logging import get_logger
from wififortress.core.paths import settings_path

log = get_logger(__name__)

SCHEMA_VERSION = 1


@dataclass
class Settings:
    schema_version: int = SCHEMA_VERSION
    ui_mode: str = "quick"  # "quick" | "advanced"
    theme: str = "parrot-dark"
    active_interface: str = ""
    scan_refresh_seconds: int = 0  # 0 = manual refresh only
    scan_duration_seconds: int = 10
    remember_window: bool = True
    window_width: int = 1440
    window_height: int = 900
    last_section: str = "dashboard"
    last_report_dir: str = ""
    enabled_dictionaries: list[str] = field(default_factory=list)
    dictionary_order: list[str] = field(default_factory=list)
    password_min_length: int = 20
    password_use_upper: bool = True
    password_use_lower: bool = True
    password_use_digits: bool = True
    password_use_symbols: bool = True
    password_exclude_ambiguous: bool = True
    passphrase_words: int = 5
    passphrase_separator: str = "-"
    audit_store_history: bool = True
    onboarding_seen: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        clean["schema_version"] = SCHEMA_VERSION
        return cls(**clean)


class SettingsService:
    """Load, mutate and persist :class:`Settings`."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or settings_path()
        self.settings = Settings()
        self.load()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Settings:
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.settings = Settings.from_dict(raw)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read settings (%s); using defaults", exc)
            self.settings = Settings()
        return self.settings

    def save(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.settings.to_dict(), handle, indent=2, sort_keys=True)
            os.replace(tmp, self._path)
            return True
        except OSError as exc:
            log.error("Could not save settings: %s", exc)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self.settings, key, default)

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        if not hasattr(self.settings, key):
            raise KeyError(f"Unknown setting: {key}")
        setattr(self.settings, key, value)
        if save:
            self.save()

    def update(self, **values: Any) -> None:
        for key, value in values.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        self.save()

    @property
    def is_advanced(self) -> bool:
        return self.settings.ui_mode == "advanced"
