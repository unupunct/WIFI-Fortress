"""Dictionary Manager service.

Manages the ten bundled resources plus user imports:

* discovery and integrity verification (SHA-256, entry counts)
* enable/disable, ordering, preview
* streaming import with duplicate detection and UTF-8 validation
* restore of bundled files from the installation resources
* never loads a whole file into memory for counting
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from wififortress.core.database import Database, utc_now_iso
from wififortress.core.logging import get_logger
from wififortress.core.paths import bundled_dictionaries_dir, dictionaries_dir
from wififortress.resources.dictionaries.manifest import DICTIONARY_SPECS, SPEC_BY_ID

log = get_logger(__name__)

CHUNK = 64 * 1024
MAX_IMPORT_BYTES = 256 * 1024 * 1024


@dataclass
class DictionaryInfo:
    dict_id: str
    name: str
    path: Path
    source: str  # "bundled" | "imported"
    license: str
    description: str
    purpose: str
    provenance: str = ""
    enabled: bool = True
    position: int = 0
    entry_count: int = 0
    size_bytes: int = 0
    sha256: str = ""
    exists: bool = True
    integrity_ok: bool | None = None
    duplicate_entries: int = 0
    imported_at: str = ""
    problem: str = ""

    @property
    def is_bundled(self) -> bool:
        return self.source == "bundled"

    @property
    def size_label(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


@dataclass
class IntegrityReport:
    dict_id: str
    ok: bool
    entry_count: int
    size_bytes: int
    sha256: str
    duplicates: int
    problems: list[str] = field(default_factory=list)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_entries(
    path: Path,
    on_progress: Callable[[int], None] | None = None,
    track_duplicates: bool = False,
) -> tuple[int, int]:
    """Stream a dictionary file and count entries.

    Returns ``(entry_count, duplicate_count)``.  Comments (``#``) and blank
    lines are ignored.  Duplicate detection is case-insensitive and only
    performed when requested, because it needs a set in memory.
    """
    count = 0
    duplicates = 0
    seen: set[int] = set() if track_duplicates else None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            count += 1
            if seen is not None:
                key = hash(entry.lower()) & 0xFFFFFFFFFFFF
                if key in seen:
                    duplicates += 1
                else:
                    seen.add(key)
            if on_progress and count % 50000 == 0:
                on_progress(count)
    return count, duplicates


def preview_entries(path: Path, limit: int = 200) -> list[str]:
    out: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            out.append(entry)
            if len(out) >= limit:
                break
    return out


def iter_entries(path: Path) -> Iterator[str]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            entry = line.strip()
            if entry and not entry.startswith("#"):
                yield entry


class DictionaryManagerService:
    def __init__(self, db: Database | None = None, user_dir: Path | None = None) -> None:
        self.db = db or Database()
        self.user_dir = user_dir or dictionaries_dir()
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self._cache: list[DictionaryInfo] = []
        self.sync()

    # -- discovery -----------------------------------------------------
    def sync(self) -> list[DictionaryInfo]:
        """Merge bundled specs, the database and the user directory."""
        rows = {row["dict_id"]: row for row in self.db.dictionaries()}
        infos: list[DictionaryInfo] = []

        for index, spec in enumerate(DICTIONARY_SPECS):
            bundled = bundled_dictionaries_dir() / spec.filename
            row = rows.get(spec.dict_id)
            path = Path(row["path"]) if row and row["path"] else bundled
            info = DictionaryInfo(
                dict_id=spec.dict_id,
                name=spec.name,
                path=path,
                source="bundled",
                license=spec.license,
                description=spec.description,
                purpose=spec.purpose,
                provenance=spec.provenance,
                enabled=bool(row["enabled"]) if row else True,
                position=row["position"] if row else index,
                entry_count=row["entry_count"] if row else 0,
                size_bytes=row["size_bytes"] if row else 0,
                sha256=row["sha256"] if row else "",
                imported_at=row["imported_at"] if row else "",
            )
            self._refresh_file_state(info)
            infos.append(info)

        known = {spec.dict_id for spec in DICTIONARY_SPECS}
        for row in rows.values():
            if row["dict_id"] in known:
                continue
            info = DictionaryInfo(
                dict_id=row["dict_id"],
                name=row["name"],
                path=Path(row["path"]),
                source=row["source"],
                license=row["license"],
                description="Imported dictionary",
                purpose="User-supplied word list for local comparison.",
                provenance="Imported by the user.",
                enabled=bool(row["enabled"]),
                position=row["position"],
                entry_count=row["entry_count"],
                size_bytes=row["size_bytes"],
                sha256=row["sha256"],
                imported_at=row["imported_at"],
            )
            self._refresh_file_state(info)
            infos.append(info)

        infos.sort(key=lambda i: (i.position, i.name))
        self._cache = infos
        return infos

    def _refresh_file_state(self, info: DictionaryInfo) -> None:
        # Counts and hashes are filled in by sync()/verify(); the per-file
        # state here only tracks existence and size so listing stays fast.
        if not info.path.exists():
            info.exists = False
            info.integrity_ok = False
            info.problem = "File is missing"
            return
        try:
            info.size_bytes = info.path.stat().st_size
        except OSError as exc:
            info.problem = str(exc)
            info.integrity_ok = False
            return
        if info.entry_count <= 0:
            # First listing of this file: count it once, then persist.
            count, duplicates = count_entries(info.path, track_duplicates=True)
            info.entry_count = count
            info.duplicate_entries = duplicates
            if not info.sha256:
                try:
                    info.sha256 = hash_file(info.path)
                except OSError:
                    info.sha256 = ""

    def all(self) -> list[DictionaryInfo]:
        return list(self._cache)

    def enabled(self) -> list[DictionaryInfo]:
        return [i for i in self._cache if i.enabled and i.exists]

    def get(self, dict_id: str) -> DictionaryInfo | None:
        for info in self._cache:
            if info.dict_id == dict_id:
                return info
        return None

    def enabled_paths(self) -> list[Path]:
        return [i.path for i in self.enabled()]

    # -- verification --------------------------------------------------
    def verify(
        self, dict_id: str, progress: Callable[[int], None] | None = None
    ) -> IntegrityReport:
        info = self.get(dict_id)
        if info is None:
            raise KeyError(f"Unknown dictionary: {dict_id}")
        problems: list[str] = []
        if not info.path.exists():
            return IntegrityReport(dict_id, False, 0, 0, "", 0, ["File is missing"])
        count, duplicates = count_entries(info.path, progress, track_duplicates=True)
        try:
            digest = hash_file(info.path)
        except OSError as exc:
            digest = ""
            problems.append(f"Cannot hash file: {exc}")
        if count == 0:
            problems.append("File contains no usable entries")
        if duplicates:
            problems.append(f"{duplicates} duplicate entries")
        # UTF-8 validity: decoding with strict errors.
        try:
            with info.path.open("r", encoding="utf-8", errors="strict") as handle:
                for _ in handle:
                    pass
        except UnicodeDecodeError as exc:
            problems.append(f"Invalid UTF-8 at byte {exc.start}")
        expected = info.entry_count
        if expected and expected != count:
            problems.append(f"Entry count changed: {expected} recorded, {count} found")
        ok = not any("missing" in p.lower() or "no usable" in p.lower() or "UTF-8" in p for p in problems)
        info.entry_count = count
        info.duplicate_entries = duplicates
        info.sha256 = digest
        info.integrity_ok = ok
        info.problem = "; ".join(problems)
        self._persist(info)
        return IntegrityReport(dict_id, ok, count, info.size_bytes, digest, duplicates, problems)

    def verify_all(self, progress: Callable[[str, int], None] | None = None) -> list[IntegrityReport]:
        reports = []
        for info in self._cache:
            if not info.exists:
                reports.append(
                    IntegrityReport(info.dict_id, False, 0, 0, "", 0, ["File is missing"])
                )
                continue
            reports.append(self.verify(info.dict_id))
            if progress:
                progress(info.dict_id, len(reports))
        return reports

    # -- mutation ------------------------------------------------------
    def set_enabled(self, dict_id: str, enabled: bool) -> None:
        info = self.get(dict_id)
        if info is None:
            return
        info.enabled = enabled
        self._persist(info)

    def move(self, dict_id: str, delta: int) -> list[DictionaryInfo]:
        infos = self.sync()
        index = next((i for i, d in enumerate(infos) if d.dict_id == dict_id), -1)
        if index < 0:
            return infos
        target = max(0, min(len(infos) - 1, index + delta))
        if target == index:
            return infos
        infos.insert(target, infos.pop(index))
        for position, info in enumerate(infos):
            info.position = position
            self._persist(info)
        return self.sync()

    def import_file(
        self,
        source: Path,
        name: str | None = None,
        progress: Callable[[int], None] | None = None,
    ) -> DictionaryInfo:
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(str(source))
        size = source.stat().st_size
        if size == 0:
            raise ValueError("The selected file is empty")
        if b"\x00" in source.read_bytes()[:65536]:
            raise ValueError("The selected file looks binary, not a text word list")
        if size > MAX_IMPORT_BYTES:
            raise ValueError(
                f"File is too large ({size} bytes); the limit is {MAX_IMPORT_BYTES} bytes"
            )
        dict_id = f"import_{hashlib.sha1(str(source.resolve()).encode()).hexdigest()[:12]}"
        safe_name = "".join(
            c for c in (name or source.stem) if c.isalnum() or c in " -_"
        ).strip() or "imported"
        target = self.user_dir / f"import-{safe_name}.txt"
        shutil.copyfile(source, target)
        count, duplicates = count_entries(target, progress, track_duplicates=True)
        if count == 0:
            target.unlink(missing_ok=True)
            raise ValueError("No usable entries found (blank lines and '#' comments are ignored)")
        info = DictionaryInfo(
            dict_id=dict_id,
            name=safe_name,
            path=target,
            source="imported",
            license="User-supplied (not verified)",
            description=f"Imported from {source.name}",
            purpose="User-supplied word list for local comparison.",
            provenance=f"Imported from {source.name}",
            enabled=True,
            position=len(self._cache),
            entry_count=count,
            size_bytes=target.stat().st_size,
            sha256=hash_file(target),
            duplicate_entries=duplicates,
            imported_at=utc_now_iso(),
        )
        self._persist(info)
        self.sync()
        log.info("Imported dictionary %s (%d entries)", safe_name, count)
        return info

    def remove(self, dict_id: str) -> bool:
        info = self.get(dict_id)
        if info is None or info.is_bundled:
            return False
        try:
            info.path.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not delete %s: %s", info.path, exc)
        self.db.delete_dictionary(dict_id)
        self.sync()
        return True

    def restore_bundled(self, dict_id: str | None = None) -> list[str]:
        """Restore bundled files from the installed resources."""
        restored: list[str] = []
        specs = [SPEC_BY_ID[dict_id]] if dict_id else list(DICTIONARY_SPECS)
        for spec in specs:
            src = bundled_dictionaries_dir() / spec.filename
            if not src.exists():
                log.warning("Bundled dictionary missing from installation: %s", src)
                continue
            info = self.get(spec.dict_id)
            if info is None:
                continue
            dest = info.path
            if dest != src:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
            count, duplicates = count_entries(dest, track_duplicates=True)
            info.entry_count = count
            info.duplicate_entries = duplicates
            info.size_bytes = dest.stat().st_size
            info.sha256 = hash_file(dest)
            info.integrity_ok = True
            info.problem = ""
            self._persist(info)
            restored.append(spec.dict_id)
        self.sync()
        return restored

    def preview(self, dict_id: str, limit: int = 200) -> list[str]:
        info = self.get(dict_id)
        if info is None or not info.path.exists():
            return []
        return preview_entries(info.path, limit)

    def _persist(self, info: DictionaryInfo) -> None:
        self.db.upsert_dictionary(
            {
                "dict_id": info.dict_id,
                "name": info.name,
                "path": str(info.path),
                "source": info.source,
                "license": info.license,
                "entry_count": info.entry_count,
                "size_bytes": info.size_bytes,
                "sha256": info.sha256,
                "enabled": info.enabled,
                "position": info.position,
                "imported_at": info.imported_at,
            }
        )


def disk_space_report(path: Path) -> tuple[int, int]:
    """Return (free_bytes, total_bytes) for the filesystem holding ``path``."""
    usage = shutil.disk_usage(str(path))
    return usage.free, usage.total
