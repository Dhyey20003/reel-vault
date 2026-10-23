#!/usr/bin/env bash
# Checks that Ollama is running, lists installed models, and runs ReelVault's local AI self-test.
cd "$(dirname "$0")/../.." || exit 1
URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
echo "Ollama endpoint: $URL"
if curl -s "$URL/api/tags" >/dev/null 2>&1; then
  echo "[OK] Ollama is reachable. Installed models:"; curl -s "$URL/api/tags" | .venv/bin/python -c 'import sys,json; [print("   -", m["name"], round(m.get("size",0)/1e9,1), "GB") for m in json.load(sys.stdin).get("models",[])]'
else
  echo "[FAIL] Ollama is not reachable. Start it with:  ollama serve   (or open the Ollama app)"; exit 1
fi
echo "Running ReelVault self-test (no media is sent) ..."
.venv/bin/python tools/test_local_ai.py "$@"
