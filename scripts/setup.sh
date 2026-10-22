#!/usr/bin/env bash
# ===========================================================================
# ReelVault setup for macOS (and Linux). Idempotent: safe to run again.
#  1. finds Python 3.12 or 3.13
#  2. creates .venv
#  3. installs pinned dependencies from wheelhouse/ (offline) or PyPI (fallback)
#  4. initializes the SQLite database and data folders
# Run:  bash scripts/setup.sh
# ===========================================================================
set -u
cd "$(dirname "$0")/.." || exit 1
source scripts/_find_python.sh
if [ -z "$PYEXE" ]; then
  echo
  echo "[FAIL] Python 3.12 or 3.13 was not found."
  echo "       Install it with:  brew install python@3.13   (Homebrew, https://brew.sh)"
  echo "       or download the macOS installer from https://www.python.org/downloads/macos/"
  echo "       Then run: bash scripts/setup.sh"
  exit 1
fi
echo "[1/4] Using Python $PYVER ($PYEXE)"
if [ -x ".venv/bin/python" ]; then
  echo "[2/4] .venv already exists"
else
  echo "[2/4] Creating the private Python environment in .venv ..."
  "$PYEXE" -m venv .venv || { echo "[FAIL] Could not create .venv"; exit 1; }
fi
WHEELS="wheelhouse/py${PYVER/./}"
if ls "$WHEELS"/fastapi-*.whl >/dev/null 2>&1; then
  echo "[3/4] Installing components OFFLINE from $WHEELS ..."
  .venv/bin/python -m pip install --no-index --find-links "$WHEELS" -r requirements.txt
else
  echo "[3/4] No wheelhouse for Python $PYVER. Installing from PyPI, internet needed ..."
  .venv/bin/python -m pip install -r requirements.txt
fi
if [ $? -ne 0 ]; then
  echo "[FAIL] Dependency installation failed. See the messages above."
  echo "       If a wheel for your Mac (Intel vs Apple Silicon) is missing, run with internet:  .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
.venv/bin/python -c "import fastapi, uvicorn, segno, anthropic; print('      components OK')" || { echo "[FAIL] Import check failed. Delete .venv and run setup again."; exit 1; }
echo "[4/4] Initializing database and data folders ..."
.venv/bin/python -c "from reelvault.workspace import Workspace; from reelvault.config import default_data_dir; w=Workspace(default_data_dir()); print('      data folder:', w.paths.data_dir); print('      schema version:', w.db.current_version()); w.close()" || { echo "[FAIL] Database initialization failed."; exit 1; }
echo
echo "[OK] Setup finished."
echo "     Next: bash scripts/run_server.sh"
echo "     Optional: brew install yt-dlp ffmpeg   (for reference downloads)"
