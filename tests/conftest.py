"""Shared pytest fixtures.

Every test runs against temporary data/config directories so the real user
profile is never touched.  Tests that need a specific platform state use the
``linux`` / ``requires_iw`` markers and skip otherwise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Point every writable path at a temp directory for each test."""
    monkeypatch.setenv("WIFI_FORTRESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WIFI_FORTRESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("WIFI_FORTRESS_CACHE_DIR", str(tmp_path / "cache"))
    # Cached path helpers must be recomputed after the environment changes.
    from wififortress.core import paths

    for fn in (
        paths.data_dir,
        paths.config_dir,
        paths.cache_dir,
        paths.log_dir,
        paths.reports_dir,
        paths.dictionaries_dir,
        paths.database_path,
        paths.settings_path,
    ):
        fn.cache_clear()
    yield tmp_path
    for fn in (
        paths.data_dir,
        paths.config_dir,
        paths.cache_dir,
        paths.log_dir,
        paths.reports_dir,
        paths.dictionaries_dir,
        paths.database_path,
        paths.settings_path,
    ):
        fn.cache_clear()


@pytest.fixture
def iw_scan_text() -> str:
    return (FIXTURES / "iw_scan_mixed.txt").read_text(encoding="utf-8")


@pytest.fixture
def nmcli_scan_text() -> str:
    return (FIXTURES / "nmcli_scan.txt").read_text(encoding="utf-8")


@pytest.fixture
def database():
    from wififortress.core.database import Database

    return Database()


@pytest.fixture
def settings():
    from wififortress.services.settings_service import SettingsService

    return SettingsService()


@pytest.fixture
def dictionaries(database):
    from wififortress.services.dictionary_service import DictionaryManagerService

    return DictionaryManagerService(db=database)


@pytest.fixture
def assessment(dictionaries):
    from wififortress.services.password_service import DictionarySet, PasswordAssessmentService

    word_set = DictionarySet.from_files(dictionaries.enabled_paths())
    return PasswordAssessmentService(word_set)


@pytest.fixture
def networks(iw_scan_text):
    from wififortress.services.discovery_service import WirelessDiscoveryService

    return WirelessDiscoveryService().parse_iw_scan(iw_scan_text)


@pytest.fixture
def linux_only():
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux-specific behaviour")
