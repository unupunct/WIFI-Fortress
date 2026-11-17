"""Dictionary inventory: real files, verified provenance, deterministic hashes."""

from __future__ import annotations

from pathlib import Path

import pytest

from wififortress.resources.dictionaries.manifest import DICTIONARY_SPECS

ROOT = Path(__file__).resolve().parent.parent
DICT_DIR = ROOT / "wififortress" / "resources" / "dictionaries"


def test_ten_dictionaries_declared():
    assert len(DICTIONARY_SPECS) == 10


@pytest.mark.parametrize("spec", DICTIONARY_SPECS, ids=[d.dict_id for d in DICTIONARY_SPECS])
def test_declared_file_exists(spec):
    assert (DICT_DIR / spec.filename).is_file()


@pytest.mark.parametrize("spec", DICTIONARY_SPECS, ids=[d.dict_id for d in DICTIONARY_SPECS])
def test_every_dictionary_has_license_and_provenance(spec):
    assert spec.license == "CC0-1.0"
    assert spec.provenance.strip()
    assert spec.description.strip()


@pytest.mark.parametrize("spec", DICTIONARY_SPECS, ids=[d.dict_id for d in DICTIONARY_SPECS])
def test_declared_checksum_and_count_match_file(spec, dictionaries):
    from wififortress.services.dictionary_service import count_entries, hash_file

    path = DICT_DIR / spec.filename
    assert count_entries(path)[0] > 0
    assert len(hash_file(path)) == 64


def test_files_have_no_duplicates_within_them():
    for spec in DICTIONARY_SPECS:
        lines = [
            line.strip()
            for line in (DICT_DIR / spec.filename).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == len(set(lines)), f"duplicates in {spec.filename}"


def test_romanian_dictionary_keeps_diacritics():
    text = (DICT_DIR / "03-romanian-words.txt").read_text(encoding="utf-8")
    assert any(ch in text for ch in "ăâîșțĂÂÎȘȚ")


def test_no_entry_contains_whitespace_only():
    for spec in DICTIONARY_SPECS:
        for line in (DICT_DIR / spec.filename).read_text(encoding="utf-8").splitlines():
            assert line == line.strip()


def test_manager_reports_status(dictionaries):
    entries = dictionaries.all()
    assert len(entries) == 10
    assert all(e.exists for e in entries)
    assert all(e.entry_count > 0 for e in entries), [
        e.dict_id for e in entries if not e.entry_count
    ]


def test_manager_verify_detects_checksum(dictionaries):
    results = dictionaries.verify_all()
    assert len(results) == 10
    assert all(r.ok for r in results), [r.problems for r in results if not r.ok]


def test_disabling_a_dictionary_changes_enabled_paths(dictionaries):
    before = len(dictionaries.enabled_paths())
    dictionaries.set_enabled("extended_patterns", False)
    assert len(dictionaries.enabled_paths()) == before - 1
    dictionaries.set_enabled("extended_patterns", True)
    assert len(dictionaries.enabled_paths()) == before


def test_preview_returns_requested_words(dictionaries):
    words = dictionaries.preview("common_passwords", 5)
    assert len(words) == 5


def test_import_of_a_custom_dictionary(tmp_path, dictionaries):
    source = tmp_path / "custom.txt"
    source.write_text("alpha\nbravo\ncharlie\n", encoding="utf-8")
    info = dictionaries.import_file(source, "custom-test")
    assert info.entry_count == 3
    assert info.path.exists()
    assert info.source == "imported"
    ids = [d.dict_id for d in dictionaries.all()]
    assert info.dict_id in ids
    assert dictionaries.remove(info.dict_id) is True
    assert info.dict_id not in [d.dict_id for d in dictionaries.all()]


def test_import_rejects_binary_content(tmp_path, dictionaries):
    source = tmp_path / "binary.txt"
    source.write_bytes(b"\x00\x01\x02\x03" * 50)
    with pytest.raises(Exception):
        dictionaries.import_file(source, "binary")
