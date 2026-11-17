"""The public word list catalogue: verified links, safe downloads, no surprise data."""

from __future__ import annotations

import urllib.parse

import pytest

from wififortress.services.wordlist_catalog import (
    CATEGORIES,
    MAX_DOWNLOAD_BYTES,
    SOURCES,
    SOURCE_BY_ID,
    WordlistCatalogService,
)


def test_catalogue_is_populated_but_bounded():
    assert 20 <= len(SOURCES) <= 50
    assert len(SOURCE_BY_ID) == len(SOURCES)


def test_source_ids_are_unique():
    ids = [s.source_id for s in SOURCES]
    assert len(ids) == len(set(ids))


def test_every_source_has_a_real_url_and_homepage():
    for source in SOURCES:
        for url in (source.url, source.homepage):
            parsed = urllib.parse.urlparse(url)
            assert parsed.scheme in ("http", "https"), source.source_id
            assert parsed.netloc, source.source_id


def test_every_source_declares_category_and_licence():
    for source in SOURCES:
        assert source.category in CATEGORIES, source.source_id
        assert source.licence, source.source_id
        assert source.name, source.source_id


def test_downloadable_entries_point_at_raw_text():
    downloadable = [s for s in SOURCES if s.is_file]
    assert len(downloadable) >= 15
    for source in downloadable:
        assert source.is_file


def test_the_requested_sources_are_present():
    urls = " ".join(s.url + " " + s.homepage for s in SOURCES)
    assert "223fcb59b3072884dd0f" in urls          # the gist
    assert "kkrypt0nn/wordlists" in urls
    assert "danielmiessler/SecLists" in urls
    assert "amitlttwo/All-Wordlists" in urls
    assert "00xZEROx00/kali-wordlists" in urls


def test_wifi_lists_are_flagged():
    wifi = [s for s in SOURCES if s.wifi_focused]
    assert wifi
    assert all(s.category == "Wi-Fi (WPA)" for s in wifi)


def test_filenames_are_safe():
    for source in SOURCES:
        name = source.filename
        assert "/" not in name and "\\" not in name
        assert not name.startswith(".")


def test_size_limit_is_sane():
    assert MAX_DOWNLOAD_BYTES >= 64 * 1024 * 1024


def test_project_pages_are_refused_as_downloads(tmp_path):
    service = WordlistCatalogService()
    page = next(s for s in SOURCES if not s.is_file)
    result = service.download(page)
    assert result.ok is False
    assert "project page" in result.message


def test_existing_returns_none_before_download():
    service = WordlistCatalogService()
    source = SOURCES[0]
    assert service.existing(source) is None


def test_clear_cache_removes_downloads(tmp_path):
    service = WordlistCatalogService()
    junk = service.download_dir / "leftover.txt"
    junk.write_text("x", encoding="utf-8")
    removed = service.clear_cache()
    assert removed >= 1
    assert not junk.exists()


def test_dictionary_licence_and_provenance_survive_a_restart(tmp_path, monkeypatch):
    """A downloaded list must keep its upstream licence, not become 'user-supplied'."""
    from wififortress.core.database import Database
    from wififortress.services.dictionary_service import DictionaryManagerService

    monkeypatch.setenv("WIFI_FORTRESS_DATA_DIR", str(tmp_path / "data"))
    from wififortress.core import paths

    for fn in ("data_dir", "config_dir", "cache_dir", "dictionaries_dir"):
        getattr(paths, fn).cache_clear()

    db = Database(tmp_path / "wf.db")
    manager = DictionaryManagerService(db)
    sample = tmp_path / "sample-wpa.txt"
    sample.write_text("\n".join(f"passphrase{i}" for i in range(50)), encoding="utf-8")

    info = manager.import_file(
        sample,
        name="SecLists test list",
        licence="MIT",
        provenance="Downloaded from https://example.invalid/list.txt",
    )
    assert info.license == "MIT"

    reopened = DictionaryManagerService(Database(tmp_path / "wf.db"))
    reloaded = reopened.get(info.dict_id)
    assert reloaded is not None
    assert reloaded.license == "MIT"
    assert "example.invalid" in reloaded.provenance
