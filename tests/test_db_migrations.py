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
    assert db.migrate() == [3]
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
