#!/usr/bin/env bash
# Starts Ollama in the background on macOS if it is not running (bound to localhost only).
if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then echo "Ollama already running"; exit 0; fi
if command -v brew >/dev/null 2>&1 && brew list ollama >/dev/null 2>&1; then brew services start ollama && echo "Started via Homebrew services"; exit 0; fi
command -v ollama >/dev/null 2>&1 || { echo "[FAIL] ollama not installed; run scripts/local_ai/setup_ollama_mac.sh"; exit 1; }
(nohup ollama serve >/tmp/ollama.log 2>&1 &) && sleep 2 && echo "Started: ollama serve (log: /tmp/ollama.log)"
