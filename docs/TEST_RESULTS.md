# Test results (v2.0.0; environment: Linux container, Python 3.13, ffmpeg 6.1, JDK 21, Gradle 8.14.3, Chromium via Playwright)

## Automated, run here
| Area | Command | Result |
|---|---|---|
| Backend (v1 + v2) | `python -m pytest` | **66 passed** |
| Schema upgrade and rollback | `test_db_migrations.py::test_v1_database_upgrades_and_rolls_back` | v1 (schema 3) DB with data → migrate (backup written) → data intact with new columns → rollback tool restores schema 3 |
| Sync idempotency | `test_sync_api.py` | retried capture_id replays the same answer; normalized-URL dedup; invalid items do not break a batch |
| Download validation | `test_v2.py` | real ffmpeg files: audio-only marked failed with file kept and surfaced in Repair; valid video → ok, cover generated, range request 206; file removed → not playable; non-browser codec gets playback copy, original kept |
| Media route safety | `test_v2.py::test_media_route_cannot_serve_arbitrary_files` | non-video/invalid rows 409, unknown ids 404, path traversal blocked |
| Import, bulk links, tags, timed notes, trip quick-add, multi-trip | `test_v2.py` | pass |
| Manual edits survive metadata refresh | `test_v2.py`, `test_workspace_api.py` | pass |
| URL variants (Instagram reel/reels/p/tv, YouTube watch/shorts/youtu.be, tracking params) | `test_urlnorm.py`, `test_v2.py` | pass |
| Local AI | `test_v2.py` | status/test fail gracefully without Ollama; public endpoints refused; provider parses schema output; every request goes to the configured localhost URL only; cloud provider refused unless opted in |
| Pipeline resume, pause, disk guard; analysis cache key; cancel flags; diagnostics redaction; pairing warnings and advertised host | `test_v2.py` | pass |
| Android `core` | `./gradlew -Preelvault.coreOnly=true :core:test` | **9 passed** |
| Web UI (Playwright, Chromium) | `scratch ui2.mjs` against a test server on port 8790 with its own data dir | import real WebM → playable with cover; detail: duration loaded, seek, A–B loop keeps playback inside the range, timestamped note added, title/tags saved, cover from frame; filter and position kept after closing detail; quick trip add; feed mode: one active video, j/k navigation; trip gallery; Adapt-for-trip job fails gracefully without Ollama; repair page; settings Test local AI shows the reason; bulk add outcomes; non-playable media route 409; **0 page errors** |

Note: Playwright's Chromium lacks H.264, so the browser test used VP9/WebM; H.264 MP4 playback is covered by the ffprobe/route tests and works in regular browsers.

## Not run here (blockers)
| Item | Why | How to run |
|---|---|---|
| Android `app` compile, 10 JVM unit tests (`CaptureRepositoryTest`), 2 instrumented tests, APK build | Google's Maven/SDK hosts are blocked in this environment | `scripts\build_apk.bat` / `bash scripts/build_apk.sh`, then `cd android && ./gradlew :app:testDebugUnitTest connectedDebugAndroidTest` |
| Instagram share → "Save to ReelVault" direct-share placement, background sync behaviour, APK upgrade over v1 keeping the queue | needs a physical phone | `docs/WINDOWS_MANUAL_CHECKLIST.md` section Phone |
| Ollama analysis quality/performance on a Mac | no Mac, no models here | `bash scripts/local_ai/check_ollama.sh`, then Analyze on one idea |
| Windows `.bat` scripts, macOS `.sh` scripts on a real Mac | `.sh` scripts executed on Linux only | run them |
| PyInstaller exe/binary | not rebuilt here for v2 (spec unchanged apart from new static files, which are included by folder) | `scripts\build_pc_exe.bat` / `bash scripts/build_pc_app.sh` |
