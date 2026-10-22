#!/usr/bin/env bash
# Convenience: runs setup.sh when needed, then run_server.sh.
cd "$(dirname "$0")/.." || exit 1
if [ ! -x ".venv/bin/python" ] || ! .venv/bin/python -c "import fastapi, uvicorn, segno, anthropic" >/dev/null 2>&1; then
  echo "Running setup first ..."
  bash scripts/setup.sh || exit 1
fi
bash scripts/run_server.sh "$@"
