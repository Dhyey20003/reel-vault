#!/usr/bin/env bash
# Starts the ReelVault workspace, prints the localhost URL and the LAN IP:port, opens the browser.
# Run:  bash scripts/run_server.sh        (Ctrl+C to stop)
cd "$(dirname "$0")/.." || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "[FAIL] .venv not found. Run: bash scripts/setup.sh"
  exit 1
fi
echo "Starting ReelVault ... (press Ctrl+C to stop)"
.venv/bin/python launcher/run_server.py "$@"
RC=$?
if [ $RC -ne 0 ]; then
  echo
  echo "[FAIL] ReelVault stopped with exit code $RC. See ~/Library/Application Support/ReelVault/Data/logs/reelvault.log"
fi
exit $RC
