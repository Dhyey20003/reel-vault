"""SQLite access and versioned schema migrations.

Every migration is applied inside a transaction and recorded in
``schema_migrations``. ``PRAGMA user_version`` mirrors the latest version so
external tools can read it. Migrations are append-only: never edit an entry
that has shipped; add a new one.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import DEFAULT_CATEGORIES, SETTING_DEFAULTS


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def new_id() -> str:
    return uuid.uuid4().hex


Migration = tuple[int, str, Callable[[sqlite3.Connection], None] | str]

MIGRATIONS: list[Migration] = [
    (1, "initial schema", """
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE ideas (
            id TEXT PRIMARY KEY,
            original_url TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            canonical_url TEXT,
            shared_text TEXT,
            title TEXT NOT NULL DEFAULT '',
            creator TEXT NOT NULL DEFAULT '',
            caption TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            shooting_notes TEXT NOT NULL DEFAULT '',
            editing_notes TEXT NOT NULL DEFAULT '',
            transcript TEXT NOT NULL DEFAULT '',
            category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
            priority TEXT NOT NULL DEFAULT 'Normal',
            status TEXT NOT NULL DEFAULT 'To Make',
            source TEXT NOT NULL DEFAULT 'manual',
            device_id TEXT,
            captured_at TEXT NOT NULL,
            metadata_status TEXT NOT NULL DEFAULT 'pending',
            metadata_error TEXT,
            metadata_provider TEXT,
            metadata_json TEXT,
            thumbnail_path TEXT,
            thumbnail_url TEXT,
            download_status TEXT NOT NULL DEFAULT 'not_downloaded',
            download_error TEXT,
            local_path TEXT,
            analysis_status TEXT NOT NULL DEFAULT 'none',
            analysis_json TEXT,
            analysis_error TEXT,
            finished_video_url TEXT NOT NULL DEFAULT '',
            follow_up_date TEXT,
            reminded_at TEXT,
            reminded_for_updated_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE INDEX idx_ideas_normalized ON ideas(normalized_url);
        CREATE INDEX idx_ideas_status ON ideas(status);
        CREATE INDEX idx_ideas_updated ON ideas(updated_at);
        CREATE TABLE capture_receipts (
            capture_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            idea_id TEXT,
            result TEXT NOT NULL,
            received_at TEXT NOT NULL
        );
        CREATE TABLE devices (
            device_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            captures_received INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE trips (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            start_date TEXT,
            end_date TEXT,
            notes TEXT NOT NULL DEFAULT '',
            checklist_json TEXT NOT NULL DEFAULT '[]',
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE idea_trips (
            idea_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            added_at TEXT NOT NULL,
            PRIMARY KEY (idea_id, trip_id)
        );
        CREATE TABLE download_jobs (
            id TEXT PRIMARY KEY,
            idea_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0,
            output_path TEXT,
            error TEXT,
            log TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        );
        CREATE INDEX idx_download_jobs_idea ON download_jobs(idea_id, created_at);
        CREATE TABLE analysis_jobs (
            id TEXT PRIMARY KEY,
            idea_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            inputs_json TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        );
        CREATE INDEX idx_analysis_jobs_idea ON analysis_jobs(idea_id, created_at);
        CREATE TABLE attachments (
            id TEXT PRIMARY KEY,
            idea_id TEXT NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """),
    (2, "seed default categories and pairing token", lambda conn: _seed_defaults(conn)),
    (3, "ideas: duplicate_of column for intentionally saved copies", """
        ALTER TABLE ideas ADD COLUMN duplicate_of TEXT;
    """),
]


def _seed_defaults(conn: sqlite3.Connection) -> None:
    now = utcnow()
    for i, name in enumerate(DEFAULT_CATEGORIES):
        conn.execute(
            "INSERT OR IGNORE INTO categories(id, name, sort_order, created_at, updated_at) VALUES (?,?,?,?,?)",
            (new_id(), name, i, now, now),
        )
    conn.execute(
        "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?,?,?)",
        ("pairing_token", json.dumps(secrets.token_urlsafe(24)), now),
    )


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._local = threading.local()

    # -- connections -----------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Serialized write transaction (one writer at a time inside the process)."""
        conn = self.connection()
        with self._lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- migrations ------------------------------------------------------
    def current_version(self) -> int:
        conn = self.connection()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not row:
            return 0
        v = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        return int(v or 0)

    def migrate(self) -> list[int]:
        applied: list[int] = []
        conn = self.connection()
        with self._lock:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            current = self.current_version()
            for version, name, action in MIGRATIONS:
                if version <= current:
                    continue
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if callable(action):
                        action(conn)
                    else:
                        for stmt in _split_sql(action):
                            conn.execute(stmt)
                    conn.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
                        (version, name, utcnow()),
                    )
                    conn.execute(f"PRAGMA user_version={version}")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                conn.execute("COMMIT")
                applied.append(version)
        return applied

    # -- settings --------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.connection().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return SETTING_DEFAULTS.get(key, default)
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value), utcnow()),
            )

    def all_settings(self) -> dict[str, Any]:
        out = dict(SETTING_DEFAULTS)
        for row in self.connection().execute("SELECT key, value FROM settings"):
            if row["key"] == "pairing_token":
                continue
            try:
                out[row["key"]] = json.loads(row["value"])
            except ValueError:
                pass
        return out

    def pairing_token(self) -> str:
        tok = self.get_setting("pairing_token")
        if not tok:
            tok = secrets.token_urlsafe(24)
            self.set_setting("pairing_token", tok)
        return tok

    def rotate_pairing_token(self) -> str:
        tok = secrets.token_urlsafe(24)
        self.set_setting("pairing_token", tok)
        return tok


def _split_sql(script: str) -> list[str]:
    stmts: list[str] = []
    buf: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmts.append("\n".join(buf))
            buf = []
    if buf:
        stmts.append("\n".join(buf))
    return stmts
