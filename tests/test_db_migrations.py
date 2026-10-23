from pathlib import Path
import sqlite3

from reelvault.db import MIGRATIONS, Database


def test_fresh_db_applies_all_migrations(tmp_path):
    db = Database(tmp_path / "x.db")
    applied = db.migrate()
    assert applied == [m[0] for m in MIGRATIONS]
    assert db.current_version() == MIGRATIONS[-1][0]
    assert db.connection().execute("PRAGMA user_version").fetchone()[0] == MIGRATIONS[-1][0]
    assert db.connection().execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    # second run is a no-op
    assert db.migrate() == []
    db.close()


def test_incremental_migration_from_older_version(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    conn = db.connection()
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    # Apply only migration 1 and 2 by hand through the real runner, then pretend v3 is new.
    from reelvault.db import _split_sql, utcnow
    conn.execute("BEGIN")
    for stmt in _split_sql(MIGRATIONS[0][2]):
        conn.execute(stmt)
    conn.execute("INSERT INTO schema_migrations VALUES (1, 'initial', ?)", (utcnow(),))
    conn.execute("COMMIT")
    MIGRATIONS[1][2](conn)
    conn.execute("INSERT INTO schema_migrations VALUES (2, 'seed', ?)", (utcnow(),))
    assert db.current_version() == 2
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ideas)")}
    assert "duplicate_of" not in cols
    assert db.migrate() == [m[0] for m in MIGRATIONS if m[0] >= 3]
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ideas)")}
    assert "duplicate_of" in cols
    db.close()


def test_defaults_seeded(tmp_path):
    db = Database(tmp_path / "x.db")
    db.migrate()
    names = [r[0] for r in db.connection().execute("SELECT name FROM categories ORDER BY sort_order")]
    assert names[:3] == ["Travel", "Cinematic", "Storytelling"]
    assert len(db.pairing_token()) >= 20
    old = db.pairing_token()
    assert db.rotate_pairing_token() != old
    db.close()


def test_settings_roundtrip(tmp_path):
    db = Database(tmp_path / "x.db")
    db.migrate()
    assert db.get_setting("lan_enabled") is False
    db.set_setting("lan_enabled", True)
    db.set_setting("priorities", ["A", "B"])
    assert db.get_setting("lan_enabled") is True
    assert db.get_setting("priorities") == ["A", "B"]
    assert "pairing_token" not in db.all_settings()
    db.close()


def test_v1_database_upgrades_and_rolls_back(tmp_path):
    """Build a real v1 (schema 3) database with data, migrate to latest, verify data, roll back."""
    from reelvault.db import _split_sql, utcnow
    import subprocess, sys
    data = tmp_path / "data"; data.mkdir()
    db = Database(data / "reelvault.db")
    conn = db.connection()
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    for version, name, action in MIGRATIONS[:3]:
        conn.execute("BEGIN")
        if callable(action):
            action(conn)
        else:
            for stmt in _split_sql(action):
                conn.execute(stmt)
        conn.execute("INSERT INTO schema_migrations VALUES (?,?,?)", (version, name, utcnow()))
        conn.execute("COMMIT")
    conn.execute("INSERT INTO ideas(id, original_url, normalized_url, title, captured_at, created_at, updated_at) VALUES ('i1','https://a/b','https://a/b','keep me',?,?,?)", (utcnow(),)*3)
    conn.execute("INSERT INTO trips(id, name, created_at, updated_at) VALUES ('t1','Udaipur',?,?)", (utcnow(),)*2)
    conn.execute("INSERT INTO idea_trips VALUES ('i1','t1',?)", (utcnow(),))
    db.close()
    tool = str(Path(__file__).resolve().parent.parent / "tools" / "upgrade_db.py")
    out = subprocess.run([sys.executable, tool, "migrate", "--data-dir", str(data)], capture_output=True, text=True)
    assert "schema 3 ->" in out.stdout, out.stdout + out.stderr
    db = Database(data / "reelvault.db")
    assert db.current_version() == MIGRATIONS[-1][0]
    row = db.connection().execute("SELECT title, tags_json, pipeline_stage FROM ideas WHERE id='i1'").fetchone()
    assert row["title"] == "keep me" and row["tags_json"] == "[]" and row["pipeline_stage"] == "idle"
    assert db.connection().execute("SELECT COUNT(*) FROM idea_trips").fetchone()[0] == 1
    db.close()
    backup = next((data / "backups").glob("pre-v2-*.db"))
    out = subprocess.run([sys.executable, tool, "rollback", "--data-dir", str(data), "--backup", str(backup)], capture_output=True, text=True)
    assert "restored" in out.stdout, out.stdout + out.stderr
    db = Database(data / "reelvault.db")
    assert db.current_version() == 3
    assert db.connection().execute("SELECT title FROM ideas WHERE id='i1'").fetchone()[0] == "keep me"
    db.close()
