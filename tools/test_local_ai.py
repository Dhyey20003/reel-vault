"""Local AI self-test: checks hardware, Ollama reachability, model presence, and a tiny JSON round-trip.

  python tools/test_local_ai.py [--url http://127.0.0.1:11434] [--model qwen2.5vl:7b] [--data-dir DIR]
Reads defaults from the ReelVault settings database when --url/--model are omitted. Sends no media.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from reelvault.config import Paths, default_data_dir  # noqa: E402
from reelvault.db import Database  # noqa: E402
from reelvault.services import local_ai  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"); ap.add_argument("--model"); ap.add_argument("--data-dir")
    a = ap.parse_args()
    paths = Paths(Path(a.data_dir) if a.data_dir else default_data_dir())
    url, model = a.url, a.model
    if (not url or not model) and paths.db_path.exists():
        db = Database(paths.db_path); db.migrate()
        url = url or db.get_setting("ollama_url"); model = model or db.get_setting("ollama_model"); db.close()
    url = url or "http://127.0.0.1:11434"; model = model or "qwen2.5vl:7b"
    hw = local_ai.hardware()
    rec = local_ai.recommend_model(hw.get("ram_gb"))
    print(f"Machine: {hw['chip']} · {hw['ram_gb']} GB RAM · {hw['disk_free_gb']} GB free · {hw['os']}")
    print(f"Recommended model: {rec['name']} ({rec['download_gb']} GB download; {rec['note']})")
    st = local_ai.ollama_status(url, model)
    print(f"Ollama at {url}: {'reachable' if st['reachable'] else 'NOT reachable'}; installed models: {', '.join(st['models']) or 'none'}")
    if st["error"]:
        print("[FAIL]", st["error"]); return 1
    try:
        p = local_ai.OllamaProvider(url, 120, 2048)
        raw = p._chat(model, [{"role": "user", "content": 'Reply with JSON {"ok": true, "hello": "<one word>"}'}],
                      {"type": "object", "properties": {"ok": {"type": "boolean"}, "hello": {"type": "string"}}, "required": ["ok"]})
        print("[OK] model replied:", raw.strip()[:120])
    except Exception as e:  # noqa: BLE001
        print("[FAIL]", e); return 1
    print("Local AI works. In ReelVault: open an idea > Analyze. Nothing is sent outside this machine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
