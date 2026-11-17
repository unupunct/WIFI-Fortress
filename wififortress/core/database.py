"""SQLite persistence for history, audits and dictionary metadata.

The database is deliberately simple: one connection per thread, WAL mode,
foreign keys on.  Nothing secret is ever stored - no passwords, no PSKs.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from wififortress.core.logging import get_logger
from wififortress.core.paths import database_path

log = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    interface TEXT,
    network_count INTEGER DEFAULT 0,
    source TEXT
);

CREATE TABLE IF NOT EXISTS networks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER REFERENCES scans(id) ON DELETE CASCADE,
    ssid TEXT NOT NULL,
    bssid TEXT NOT NULL,
    channel INTEGER,
    frequency INTEGER,
    band TEXT,
    signal INTEGER,
    security TEXT,
    encryption TEXT,
    authentication TEXT,
    hidden INTEGER DEFAULT 0,
    seen_at TEXT NOT NULL,
    raw TEXT
);
CREATE INDEX IF NOT EXISTS idx_networks_scan ON networks(scan_id);
CREATE INDEX IF NOT EXISTS idx_networks_bssid ON networks(bssid);

CREATE TABLE IF NOT EXISTS audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    ssid TEXT NOT NULL,
    bssid TEXT,
    interface TEXT,
    score INTEGER,
    grade TEXT,
    findings_total INTEGER DEFAULT 0,
    critical INTEGER DEFAULT 0,
    high INTEGER DEFAULT 0,
    medium INTEGER DEFAULT 0,
    low INTEGER DEFAULT 0,
    informational INTEGER DEFAULT 0,
    unknown INTEGER DEFAULT 0,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    ssid TEXT,
    score INTEGER,
    path TEXT NOT NULL,
    format TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    sha256 TEXT
);

CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS dictionaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dict_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    source TEXT NOT NULL,
    license TEXT NOT NULL,
    entry_count INTEGER DEFAULT 0,
    size_bytes INTEGER DEFAULT 0,
    sha256 TEXT,
    enabled INTEGER DEFAULT 1,
    position INTEGER DEFAULT 0,
    imported_at TEXT
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or database_path()
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_schema()

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self.connection()
        with self._lock:
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    def _init_schema(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self.cursor() as cur:
            cur.executescript(SCHEMA)
            cur.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('version', '1')"
            )

    # -- scans ---------------------------------------------------------
    def start_scan(self, interface: str, source: str) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO scans(started_at, interface, source) VALUES (?,?,?)",
                (utc_now_iso(), interface, source),
            )
            return int(cur.lastrowid)

    def finish_scan(self, scan_id: int, network_count: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                "UPDATE scans SET finished_at=?, network_count=? WHERE id=?",
                (utc_now_iso(), network_count, scan_id),
            )

    def add_networks(self, scan_id: int, networks: list[dict[str, Any]]) -> None:
        if not networks:
            return
        rows = [
            (
                scan_id,
                n.get("ssid", ""),
                n.get("bssid", ""),
                n.get("channel"),
                n.get("frequency"),
                n.get("band"),
                n.get("signal"),
                n.get("security"),
                n.get("encryption"),
                n.get("authentication"),
                1 if n.get("hidden") else 0,
                n.get("seen_at") or utc_now_iso(),
                json.dumps(n, ensure_ascii=False),
            )
            for n in networks
        ]
        with self.cursor() as cur:
            cur.executemany(
                "INSERT INTO networks(scan_id, ssid, bssid, channel, frequency, band,"
                " signal, security, encryption, authentication, hidden, seen_at, raw)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )

    def recent_scans(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,))
            return cur.fetchall()

    def network_history(self, bssid: str, limit: int = 50) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM networks WHERE bssid=? ORDER BY id DESC LIMIT ?",
                (bssid, limit),
            )
            return cur.fetchall()

    def distinct_networks(self, limit: int = 200) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT bssid, ssid, MAX(id) AS last_id, COUNT(*) AS sightings,"
                " MAX(seen_at) AS last_seen, MAX(signal) AS best_signal"
                " FROM networks GROUP BY bssid ORDER BY last_id DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    # -- audits --------------------------------------------------------
    def save_audit(self, audit: dict[str, Any]) -> int:
        counts = audit.get("severity_counts", {})
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO audits(created_at, ssid, bssid, interface, score, grade,"
                " findings_total, critical, high, medium, low, informational, unknown,"
                " payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    audit.get("created_at") or utc_now_iso(),
                    audit.get("ssid", ""),
                    audit.get("bssid", ""),
                    audit.get("interface", ""),
                    audit.get("score"),
                    audit.get("grade", ""),
                    len(audit.get("findings", [])),
                    counts.get("critical", 0),
                    counts.get("high", 0),
                    counts.get("medium", 0),
                    counts.get("low", 0),
                    counts.get("informational", 0),
                    counts.get("unknown", 0),
                    json.dumps(audit, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid)

    def audits(self, limit: int = 50) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM audits ORDER BY id DESC LIMIT ?", (limit,))
            return cur.fetchall()

    def audit(self, audit_id: int) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute("SELECT payload FROM audits WHERE id=?", (audit_id,))
            row = cur.fetchone()
            return json.loads(row["payload"]) if row else None

    def delete_audit(self, audit_id: int) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM audits WHERE id=?", (audit_id,))

    # -- reports -------------------------------------------------------
    def add_report(self, record: dict[str, Any]) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO reports(created_at, kind, title, ssid, score, path, format,"
                " size_bytes, sha256) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    record.get("created_at") or utc_now_iso(),
                    record.get("kind", "audit"),
                    record.get("title", ""),
                    record.get("ssid", ""),
                    record.get("score"),
                    record.get("path", ""),
                    record.get("format", "pdf"),
                    record.get("size_bytes", 0),
                    record.get("sha256", ""),
                ),
            )
            return int(cur.lastrowid)

    def reports(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM reports ORDER BY id DESC LIMIT ?", (limit,))
            return cur.fetchall()

    def delete_report(self, report_id: int) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM reports WHERE id=?", (report_id,))

    # -- operations ----------------------------------------------------
    def log_operation(
        self, category: str, title: str, status: str, detail: str = ""
    ) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO operations(created_at, category, title, status, detail)"
                " VALUES (?,?,?,?,?)",
                (utc_now_iso(), category, title, status, detail),
            )
            cur.execute(
                "DELETE FROM operations WHERE id NOT IN"
                " (SELECT id FROM operations ORDER BY id DESC LIMIT 500)"
            )

    def operations(self, limit: int = 30) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM operations ORDER BY id DESC LIMIT ?", (limit,))
            return cur.fetchall()

    # -- dictionaries --------------------------------------------------
    def upsert_dictionary(self, record: dict[str, Any]) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO dictionaries(dict_id, name, path, source, license,"
                " entry_count, size_bytes, sha256, enabled, position, imported_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(dict_id) DO UPDATE SET name=excluded.name,"
                " path=excluded.path, source=excluded.source, license=excluded.license,"
                " entry_count=excluded.entry_count, size_bytes=excluded.size_bytes,"
                " sha256=excluded.sha256, enabled=excluded.enabled,"
                " position=excluded.position",
                (
                    record["dict_id"],
                    record["name"],
                    record["path"],
                    record["source"],
                    record["license"],
                    record.get("entry_count", 0),
                    record.get("size_bytes", 0),
                    record.get("sha256", ""),
                    1 if record.get("enabled", True) else 0,
                    record.get("position", 0),
                    record.get("imported_at") or utc_now_iso(),
                ),
            )

    def dictionaries(self) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM dictionaries ORDER BY position, id")
            return cur.fetchall()

    def delete_dictionary(self, dict_id: str) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM dictionaries WHERE dict_id=?", (dict_id,))
