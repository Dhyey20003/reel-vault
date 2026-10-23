"""Backup + migrate (or rollback) the ReelVault database.

  python tools/upgrade_db.py backup   [--data-dir DIR]        -> backups/pre-v2-<stamp>.db (+ config.json copy)
  python tools/upgrade_db.py migrate  [--data-dir DIR]        -> backup first, then apply pending migrations
  python tools/upgrade_db.py rollback --backup FILE [--data-dir DIR] -> restore that backup (stops if server is running)
  python tools/upgrade_db.py status   [--data-dir DIR]

Run with the server STOPPED for migrate/rollback. Backups are consistent even while running (SQLite backup API).
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from reelvault.config import Paths, default_data_dir  # noqa: E402
from reelvault.db import MIGRATIONS, Database  # noqa: E402


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def do_backup(paths: Paths, label: str = "pre-v2") -> Path:
    db = Database(paths.db_path)
    dest = paths.backups / f"{label}-{stamp()}.db"
    db.backup_to(dest)
    db.close()
    if paths.config_file.exists():
        shutil.copy2(paths.config_file, paths.backups / f"config-{stamp()}.json")
    print(f"[OK] backup written: {dest}")
    return dest


def do_migrate(paths: Paths) -> None:
    if not paths.db_path.exists():
        print("[INFO] no database yet; it will be created on first start"); return
    do_backup(paths)
    db = Database(paths.db_path)
    before = db.current_version()
    applied = db.migrate()
    print(f"[OK] schema {before} -> {db.current_version()} (applied {applied or 'nothing'})")
    db.close()


def do_rollback(paths: Paths, backup: Path) -> None:
    if not backup.exists():
        sys.exit(f"[FAIL] backup not found: {backup}")
    try:
        sqlite3.connect(f"file:{backup}?mode=ro", uri=True).execute("PRAGMA schema_version").fetchone()
    except sqlite3.Error as e:
        sys.exit(f"[FAIL] backup is not a readable SQLite file: {e}")
    # Refuse if a live connection holds the WAL (server running).
    try:
        con = sqlite3.connect(str(paths.db_path), timeout=1)
        con.execute("BEGIN IMMEDIATE"); con.execute("ROLLBACK"); con.close()
    except sqlite3.OperationalError:
        sys.exit("[FAIL] the database is locked; stop ReelVault first")
    safety = paths.backups / f"before-rollback-{stamp()}.db"
    if paths.db_path.exists():
        Database(paths.db_path).backup_to(safety)
        print(f"[OK] current database saved to {safety}")
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(paths.db_path) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy2(backup, paths.db_path)
    v = Database(paths.db_path).current_version()
    print(f"[OK] restored {backup} (schema version {v}). Start the matching ReelVault version.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["backup", "migrate", "rollback", "status"])
    ap.add_argument("--data-dir")
    ap.add_argument("--backup")
    a = ap.parse_args()
    paths = Paths(Path(a.data_dir) if a.data_dir else default_data_dir())
    paths.ensure()
    if a.action == "backup":
        do_backup(paths)
    elif a.action == "migrate":
        do_migrate(paths)
    elif a.action == "rollback":
        if not a.backup:
            sys.exit("--backup FILE is required")
        do_rollback(paths, Path(a.backup))
    else:
        v = Database(paths.db_path).current_version() if paths.db_path.exists() else 0
        print(f"data dir: {paths.data_dir}\nschema version: {v} (latest {MIGRATIONS[-1][0]})")


if __name__ == "__main__":
    main()
