#!/usr/bin/env bash
# Builds a standalone macOS (or Linux) binary dist/ReelVault with PyInstaller.
# Run:  bash scripts/build_pc_app.sh
cd "$(dirname "$0")/.." || exit 1
[ -x ".venv/bin/python" ] || { echo "[FAIL] .venv not found. Run: bash scripts/setup.sh"; exit 1; }
PYVER=$(.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])')
WHEELS="wheelhouse/py${PYVER/./}"
echo "[1/3] Installing build tools ..."
if ls "$WHEELS"/pyinstaller-*.whl >/dev/null 2>&1; then
  .venv/bin/python -m pip install --no-index --find-links "$WHEELS" -r requirements-build.txt || { echo "[FAIL] Could not install PyInstaller"; exit 1; }
else
  .venv/bin/python -m pip install -r requirements-build.txt || { echo "[FAIL] Could not install PyInstaller"; exit 1; }
fi
echo "[2/3] Building with PyInstaller, this takes a minute ..."
.venv/bin/python -m PyInstaller reelvault.spec --noconfirm --clean || { echo "[FAIL] PyInstaller failed. See the messages above."; exit 1; }
echo "[3/3] Verifying ..."
[ -x "dist/ReelVault" ] || { echo "[FAIL] dist/ReelVault was not produced"; exit 1; }
if dist/ReelVault --help >/dev/null 2>&1; then echo "      binary responds OK"; else echo "[WARN] The binary did not respond to --help; try running it manually."; fi
echo
echo "[OK] Built dist/ReelVault"
echo "     Run it with:  ./dist/ReelVault     (no Python needed). Data stays in ~/Library/Application Support/ReelVault/Data."
echo "     macOS Gatekeeper may block an unsigned binary: right-click > Open the first time, or run  xattr -d com.apple.quarantine dist/ReelVault"
