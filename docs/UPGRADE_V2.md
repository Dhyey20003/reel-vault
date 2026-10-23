# Upgrading ReelVault v1 to v2

v2 keeps your ideas, trips, notes, categories, attachments, downloads and pairing. It reuses your existing `.venv` and adds **no new Python packages**. New optional external tools: Ollama (local AI), whisper (local transcription).

## Steps (macOS)
1. Stop the running ReelVault (Ctrl+C in its terminal, or close the window).
2. Get the v2 code into the same folder (unzip `ReelVault_v2.0.0.zip` over it, or `git checkout reelvault-v2`).
3. `bash scripts/upgrade_v2.sh` — backs up `reelvault.db` (WAL-consistent, SQLite backup API) and `config.json` to `Data/backups/pre-v2-<stamp>.db`, then applies migrations 4 and 5 in transactions.
4. `bash scripts/run_server.sh` — the only downtime is this restart. Captures shared from the phone meanwhile stay queued on the phone and sync afterwards.
5. Open Settings once: pick **Advertised host** if the pairing QR shows the wrong address, and set up **Local AI** (`docs/LOCAL_AI.md`).

Windows: stop ReelVault, unzip, run `scripts\upgrade_v2.bat`, then `scripts\run_server.bat`.

## Rollback (tested)
A Git checkout alone does not roll back the database: v2 adds columns and tables that v1 ignores but v1's migration list would not know. Restore the backup:
```
bash scripts/rollback_v2.sh "~/Library/Application Support/ReelVault/Data/backups/pre-v2-<stamp>.db"
```
(or `python tools/upgrade_db.py rollback --backup <file>`), then switch the code back to v1 and start it. The tool refuses to run while the server holds the database, and saves the current v2 database to `backups/before-rollback-<stamp>.db` first. `tests/test_db_migrations.py::test_v1_database_upgrades_and_rolls_back` exercises exactly this path.

## Android
Install the v2 APK over v1 (same application ID `app.reelvault.capture`, versionCode 2, same debug signing). The Room database migrates 1 to 2 in place; queued captures are kept. Do not uninstall first.

## Developing safely next to a live install
Run a second server with its own data: `REELVAULT_DATA_DIR=/tmp/rvdev REELVAULT_MEDIA_DIR=/tmp/rvmedia python launcher/run_server.py --port 8790 --no-browser`. Copy a database with `python tools/upgrade_db.py backup` and point `--data-dir` at a folder containing the copy. Never run `migrate` against the live data folder while the server is running.
