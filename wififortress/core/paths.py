"""Filesystem locations used by WiFi Fortress.

All paths are resolved once and cached.  The application never writes into
its own installation directory; user data lives under the XDG data
directory (``~/.local/share/wifi-fortress`` by default).
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from wififortress import APP_SLUG


def _xdg_dir(env_var: str, default: str) -> Path:
    raw = os.environ.get(env_var, "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / default


@lru_cache(maxsize=1)
def package_dir() -> Path:
    """Directory of the installed ``wififortress`` package."""
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def resources_dir() -> Path:
    """Bundled read-only resources (dictionaries, icons, assets)."""
    return package_dir() / "resources"


@lru_cache(maxsize=1)
def bundled_dictionaries_dir() -> Path:
    return resources_dir() / "dictionaries"


@lru_cache(maxsize=1)
def icons_dir() -> Path:
    return resources_dir() / "icons"


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """Writable application data directory."""
    override = os.environ.get("WIFI_FORTRESS_DATA_DIR", "").strip()
    path = Path(override).expanduser() if override else _xdg_dir(
        "XDG_DATA_HOME", ".local/share"
    ) / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def config_dir() -> Path:
    override = os.environ.get("WIFI_FORTRESS_CONFIG_DIR", "").strip()
    path = Path(override).expanduser() if override else _xdg_dir(
        "XDG_CONFIG_HOME", ".config"
    ) / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def cache_dir() -> Path:
    override = os.environ.get("WIFI_FORTRESS_CACHE_DIR", "").strip()
    path = Path(override).expanduser() if override else _xdg_dir(
        "XDG_CACHE_HOME", ".cache"
    ) / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def reports_dir() -> Path:
    path = data_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def dictionaries_dir() -> Path:
    """User dictionary directory (imports and restored copies)."""
    path = data_dir() / "dictionaries"
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def database_path() -> Path:
    return data_dir() / "wififortress.db"


@lru_cache(maxsize=1)
def settings_path() -> Path:
    return config_dir() / "settings.json"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def open_in_file_manager(path: Path) -> bool:
    """Open a directory in the desktop file manager. Returns success."""
    try:
        if sys.platform.startswith("linux"):
            import subprocess

            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            import subprocess

            subprocess.Popen(
                ["open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
    except Exception:  # pragma: no cover - desktop dependent
        return False
    return False
