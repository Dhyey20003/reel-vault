#!/usr/bin/env bash
# Installs Ollama on macOS (Homebrew) and pulls the recommended vision model for this Mac.
# Run:  bash scripts/local_ai/setup_ollama_mac.sh [model]
# Model downloads are several GB and are stored by Ollama under ~/.ollama (not inside ReelVault).
set -u
MODEL="${1:-}"
RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1000000000 ))
CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || uname -m)
FREE_GB=$(df -g "$HOME" | awk 'NR==2 {print $4}')
echo "This Mac: $CHIP, ${RAM_GB} GB RAM, ${FREE_GB} GB free in your home folder"
if [ -z "$MODEL" ]; then
  if [ "$RAM_GB" -ge 16 ]; then MODEL="qwen2.5vl:7b"; SIZE="about 6 GB"; elif [ "$RAM_GB" -ge 8 ]; then MODEL="gemma3:4b"; SIZE="about 3.3 GB"; else MODEL="qwen2.5vl:3b"; SIZE="about 3.2 GB"; fi
  echo "Recommended model for ${RAM_GB} GB RAM: $MODEL ($SIZE download)"
fi
if [ "${FREE_GB:-0}" -lt 12 ]; then echo "[WARN] Less than 12 GB free; model downloads plus playback copies may not fit."; fi
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "[1/3] Installing Ollama with Homebrew ..."; brew install ollama || { echo "[FAIL] brew install ollama failed"; exit 1; }
  else
    echo "[FAIL] Ollama is not installed and Homebrew is missing."
    echo "       Download the Ollama app from https://ollama.com/download/mac, open it once, then rerun this script."
    exit 1
  fi
else
  echo "[1/3] Ollama already installed: $(ollama --version 2>/dev/null | head -1)"
fi
echo "[2/3] Starting Ollama (if it is not already running) ..."
if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q '^ollama'; then brew services start ollama; else (nohup ollama serve >/tmp/ollama.log 2>&1 &); fi
  for i in 1 2 3 4 5 6 7 8 9 10; do sleep 1; curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; done
fi
curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || { echo "[FAIL] Ollama did not start. Open the Ollama app or run: ollama serve"; exit 1; }
echo "[3/3] Pulling $MODEL (this downloads once; keep the Mac awake) ..."
ollama pull "$MODEL" || { echo "[FAIL] ollama pull $MODEL failed. Check the model name at https://ollama.com/library"; exit 1; }
echo
echo "[OK] Local AI is ready. In ReelVault > Settings > Local AI set Model to: $MODEL   then click 'Test local AI'."
echo "     Ollama listens on 127.0.0.1:11434 only (not exposed to the network)."
