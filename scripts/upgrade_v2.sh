#!/usr/bin/env bash
# Upgrades an existing ReelVault v1 installation to v2 (macOS/Linux). Reuses the existing .venv.
#  1. stops nothing by itself: STOP the running ReelVault first (Ctrl+C in its terminal).
#  2. backs up the database (SQLite backup API, WAL-safe) and config.json into Data/backups
#  3. applies versioned migrations (4 and 5)
#  4. verifies the dependency set (no new packages are required for v2)
# Rollback: bash scripts/rollback_v2.sh <backup file>
set -u
cd "$(dirname "$0")/.." || exit 1
[ -x ".venv/bin/python" ] || { echo "[FAIL] .venv not found; run scripts/setup.sh for a fresh install"; exit 1; }
.venv/bin/python -c "import fastapi, uvicorn, segno, anthropic" 2>/dev/null || { echo "[FAIL] the venv is missing packages; run scripts/setup.sh"; exit 1; }
echo "[1/3] Backup + migrate"
.venv/bin/python tools/upgrade_db.py migrate "$@" || exit 1
echo "[2/3] Dependency check: OK (v2 adds no new Python packages; yt-dlp/ffmpeg/Ollama are optional external tools)"
echo "[3/3] Done. Start ReelVault again: bash scripts/run_server.sh"
echo "      Downtime: only the restart itself (a few seconds). Phone captures made meanwhile stay queued on the phone."
