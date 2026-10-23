# Local AI (Ollama) for ReelVault v2

Analysis runs on your own machine through [Ollama](https://ollama.com). No content leaves the computer; the cloud provider is off unless you explicitly opt in. The Ollama runtime and the model files are separate installs that ReelVault does not bundle. Local inference uses disk (models: 3 to 6 GB each), memory (the model is loaded into RAM while analyzing) and electricity.

## Hardware check first
ReelVault reads the real chip, RAM and free disk at runtime (Settings > Local AI, or `python tools/test_local_ai.py`). It recommends a model from that, never from an assumption:

| RAM | Model | Download | Notes |
|---|---|---|---|
| 16 GB or more | `qwen2.5vl:7b` | about 6 GB | best quality for frames + text |
| 8 to 16 GB | `gemma3:4b` | about 3.3 GB | lighter vision model |
| 8 GB | `qwen2.5vl:3b` | about 3.2 GB | smallest |

Any vision-capable model installed in Ollama can be typed into Settings > Local AI > Model.

## Beginner setup on a Mac (ReelVault and Ollama on the same Mac)
1. `bash scripts/local_ai/setup_ollama_mac.sh` — installs Ollama with Homebrew (or tells you to download the app), starts it, and pulls the recommended model. Keep the Mac awake during the download.
2. Optional transcription: `brew install whisper-cpp` (ReelVault finds `whisper-cli` on PATH; otherwise set its path in Settings). Also needs ffmpeg: `brew install ffmpeg`.
3. `bash scripts/local_ai/check_ollama.sh` — confirms Ollama is reachable, lists models, and runs a tiny JSON round-trip.
4. In ReelVault > Settings > Local AI: Provider = Ollama, Model = the one you pulled, click **Test local AI**. The status badge turns green.
5. Open an idea that has a downloaded or imported video, click **Analyze**. Progress shows "extracting frames", "transcribing audio locally", "asking ollama". The brief states which inputs were analysed.

Ollama listens on `127.0.0.1:11434` only by default; it is not exposed to your network.

## What the analysis actually sees
* Up to N sampled still frames (default 8; Settings > Frames per video), chosen at scene changes when ffmpeg finds them, otherwise evenly spaced, with timestamps.
* The transcript: yours if you typed one, else whisper's if installed; the UI says which.
* Title, caption, your notes, uploaded screenshots.
It never sees the full video or hears the audio. The brief separates **observed facts**, **uncertain interpretations** and **suggestions**, and is told not to guess camera models, settings or sound details without evidence. Output is validated against a schema; malformed JSON gets one repair attempt, then the job fails with the reason and can be retried.

## Caching and queue
Results are cached on a key of media fingerprint + title/caption/notes/transcript + screenshots + model + frame/transcribe settings. Re-running with nothing changed keeps the brief ("Re-analyze" forces it). Jobs run in a background queue with progress, **Cancel**, and resume after a restart (interrupted jobs are re-queued when the pipeline is on). Only one Ollama request runs at a time.

## Configuration (Settings > Local AI, example in `samples/local_ai_config.example.json`)
`ollama_url`, `ollama_model`, `ollama_timeout` (seconds), `ollama_num_ctx` (context tokens; lower it on 8 GB machines), `ai_max_frames`, `ai_transcribe`, `whisper_path`. Resource limits for Ollama itself go in its environment: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_KEEP_ALIVE=5m`.

## Windows ReelVault + Mac Ollama (private network only)
1. On the Mac, start Ollama bound to the LAN **but only your subnet**: `OLLAMA_HOST=0.0.0.0:11434 ollama serve` and restrict the macOS firewall to your private network, or better, keep Ollama on localhost and open an SSH tunnel from the PC: `ssh -N -L 11434:127.0.0.1:11434 you@mac.local`, then use `http://127.0.0.1:11434` on the PC.
2. In ReelVault on Windows set `ollama_url` to `http://<mac LAN IP>:11434` (tunnel: localhost). ReelVault refuses any Ollama URL that is not localhost or a private address.
3. Ollama has no authentication; never expose it beyond your private network or a tunnel.

## Troubleshooting
* "Ollama is not reachable": start it (`ollama serve` or the app); check the URL in Settings.
* "Model ... is not installed": `ollama pull <model>` (exact name including the tag).
* Timeouts: lower frames or context, pick a smaller model, close other heavy apps.
* "did not match the brief schema" repeatedly: the model is too small for JSON; try `qwen2.5vl:7b`.
* Slow first run: the model loads into memory once per session.

## Uninstall / rollback
`ollama rm <model>` removes a model; `brew uninstall ollama` (or delete the app) removes the runtime; `rm -rf ~/.ollama` removes all models. ReelVault keeps working without local AI (Analyze is disabled with an explanation).
