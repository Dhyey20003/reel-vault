# ReelVault

Capture Instagram Reels on your Android phone with one tap, sync them over your home WiFi to a workspace on your computer (Windows or macOS), and organize, annotate, download references, analyze and track each idea from **To Make** to **Published**.

**On a Mac? Start with [Quick start on macOS](#quick-start-on-macos).** The Windows steps use the `.bat` scripts; the macOS steps use the matching `.sh` scripts in the same `scripts/` folder.

Two parts, two processes, no mandatory cloud:

| Part | Tech | What it does |
|---|---|---|
| **PC workspace** (`reelvault/`, `launcher/`) | Python 3.12/3.13, FastAPI, SQLite (WAL), vanilla JS UI, all assets local | The main app. Runs at `http://127.0.0.1:8765/`. Also exposes the token-gated LAN sync API the phone calls. Packaged to `dist\ReelVault.exe` (Windows) or `dist/ReelVault` (macOS) with PyInstaller. |
| **Android capture app** (`android/`) | Kotlin, Jetpack Compose, Room, WorkManager | A share target. Saves the Reel link locally first, then syncs to the PC when reachable. Inbox, sync status and settings only. |

## Quick start on macOS

Prerequisites: Python 3.12 or 3.13 (`brew install python@3.13`, or the installer from python.org). The `wheelhouse/` folder contains macOS wheels for both Apple Silicon and Intel, so setup works offline.

1. Unzip `ReelVault_v1.0.0.zip`, for example to `~/ReelVault`.
2. Open Terminal, go there and run setup once:

```
cd ~/ReelVault
bash scripts/setup.sh
```

3. Start the workspace (Ctrl+C stops it):

```
bash scripts/run_server.sh
```

   It prints the data folder, `http://127.0.0.1:8765/` and your LAN IP, and opens the browser. `bash scripts/run_all.sh` does setup if needed and then starts.
4. In the browser go to **Settings**, tick **LAN access**, click **Save settings**, stop the server (Ctrl+C) and run `bash scripts/run_server.sh` again. The terminal now prints `LAN access: ENABLED -> phone uses host 192.168.x.x port 8765`. If macOS asks whether Python may accept incoming network connections, click **Allow**.
5. Build the APK with `bash scripts/build_apk.sh`. It needs JDK 17 (`brew install --cask temurin@17`) and the Android SDK (install Android Studio once, or `brew install --cask android-commandlinetools` plus the `sdkmanager` line the script prints). Then install `dist/ReelVault.apk` on the phone (AirDrop or USB, then open it, or `adb install -r dist/ReelVault.apk`).
6. Pair and share exactly as in steps 6 and 7 of the Windows run order below.

Standalone binary without Python: `bash scripts/build_pc_app.sh` produces `dist/ReelVault`. Gatekeeper may block the unsigned binary; right-click > Open the first time.

macOS folders: data in `~/Library/Application Support/ReelVault/Data`, downloaded references in `~/Movies/ReelVault` (configurable). Optional tools: `brew install yt-dlp ffmpeg`. The AI key goes in the environment (`export REELVAULT_AI_API_KEY=...` before `run_server.sh`) or in `~/Library/Application Support/ReelVault/Data/config.json`.

## Prerequisites (Windows)

* **PC app**: Windows 10/11 64-bit and Python 3.12 or 3.13 from python.org (tick "Add python.exe to PATH"). Nothing else: the `wheelhouse/` folder holds every pinned dependency for offline install.
* **Building the APK**: JDK 17+ and the Android SDK (platform 35, build-tools 35). `scripts\build_apk.bat` (Windows) or `bash scripts/build_apk.sh` (macOS) checks for both and tells you exactly what to install if missing. The first build downloads Gradle and libraries once.
* **Optional**: `yt-dlp` and `ffmpeg` on PATH (or their paths set in Settings) for "Download Reference" and frame extraction. `winget install yt-dlp` and `winget install Gyan.FFmpeg`.
* **Optional**: an Anthropic API key for "Analyze Reel". See [AI analysis](#ai-analysis-optional).

## Run order on Windows (first time)

1. Unzip `ReelVault_v1.0.0.zip` to a folder without spaces if possible, for example `C:\ReelVault`.
2. Double-click `scripts\setup.bat` once. It creates `.venv`, installs from `wheelhouse\` offline and initializes the database in `%LOCALAPPDATA%\ReelVault\Data`.
3. Double-click `scripts\run_server.bat`. It prints the localhost URL and your LAN IP:port and opens the browser.
4. In the browser go to **Settings**, tick **LAN access**, click **Save settings**, then close the server window and run `run_server.bat` again. The console now prints `LAN access: ENABLED -> phone uses host 192.168.x.x port 8765`.
5. Build the APK with `scripts\build_apk.bat` (or use a prebuilt `dist\ReelVault.apk` if one is included) and install it on the phone (copy over USB and open it, or `adb install -r dist\ReelVault.apk`). Allow installs from unknown sources when asked.
6. On the phone open ReelVault > **Settings** > **Scan pairing QR** and scan the QR shown under PC Settings > Pair your phone (or type host, port and token). Tap **Test connection**, then **Save**.
7. In Instagram, open a Reel, tap **Share**, choose **Save to ReelVault**. You stay in Instagram. Within seconds the idea appears in the PC **Inbox**.

`scripts\run_all.bat` runs setup if needed and then starts the server.

## Finding the PC's LAN IP

`run_server.bat` / `run_server.sh` prints it. On Windows you can also run `ipconfig` and look for the IPv4 address of your WiFi adapter; on macOS use System Settings > Wi-Fi > Details, or `ipconfig getifaddr en0` in Terminal (usually `192.168.x.x` or `10.x.x.x`). The phone and the PC must be on the same WiFi network. If a corporate or guest WiFi isolates clients, sync will not work; use your home network or a phone hotspot that both devices join.

## Enabling LAN access

Localhost only is the default. In **Settings > Server** tick **LAN access**, save, and restart ReelVault. The server then binds to all interfaces, but a middleware rejects every client whose address is not loopback, RFC1918 private, link-local or CGNAT. Windows Firewall will ask to allow Python (or ReelVault.exe) on **private** networks the first time; allow it. Do not allow it on public networks. On macOS the firewall prompt asks whether Python may accept incoming connections; allow it.

## Pairing

The PC generates a random pairing token on first run (Settings > Pair your phone shows it and a QR code `reelvault://pair?host=...&port=...&token=...`). Every sync request must carry the token in the `X-ReelVault-Token` header; wrong or missing tokens get `401`. **Generate new token** invalidates the old one; re-pair the phone afterwards. The phone stores the token in EncryptedSharedPreferences (Android Keystore) and excludes it from backups.

v1 uses plain HTTP on the private LAN. This is documented in `docs/SECURITY.md`; HTTPS with a self-signed certificate is a planned option.

## Daily use on the PC

* **Inbox**: everything synced that is not yet assigned to a trip. Thumbnail, title and creator appear when metadata could be fetched; otherwise the link is kept and marked *metadata unavailable* so you can type a title and retry later.
* **All Ideas**: search (titles, captions, notes, creators) and filter by status, priority, category, trip, capture date and download state. Grid/list toggle keeps the filters.
* **Trips & Projects**: lightweight collections (Udaipur, Kedarnath, Tungnath, Future Travel Vlogs, General Reel Inspiration, ...). Assign one idea to one or many trips from its detail page. Each trip has notes, a checklist, a high-priority list, suggestions (never auto-assigned), **Build shot list** (Markdown or plain text) and **Export trip folder** (metadata + copies of local references under `Data\exports\`).
* **Priority** and **Published** views.
* **Idea detail**: every field is editable and persisted (title, creator, canonical URL, caption, notes, category, priority, status, trips, shooting/editing notes, transcript, finished video link, follow-up date). Actions: retry metadata, download reference, open in player, reveal in Explorer, upload screenshots, analyze, export brief.
* **Statuses** are exactly To Make, In Progress, Published. **Priorities** default to Low, Normal, High (editable in Settings). **Categories** default to Travel, Cinematic, Storytelling, Comedy, Fitness, Transitions, Other, with add, rename and delete-with-reassign.

## Metadata retrieval

Best effort, asynchronous, never blocking, provider-based (`reelvault/services/metadata.py`):

* `ytdlp`: `yt-dlp --dump-single-json --skip-download` when yt-dlp is installed.
* `oembed`: public oEmbed endpoints (YouTube, Vimeo, TikTok). Instagram's official oEmbed needs a Facebook Graph app token; paste one in Settings if you have it.

Only documented endpoints are used; nothing logs in or bypasses access controls, and calls are rate limited. Failures mark the idea *unavailable* with the reason, keep the link, and allow manual edits and retry.

## Download Reference (optional)

Needs yt-dlp (ffmpeg recommended). Files go to `%USERPROFILE%\Videos\ReelVault\<Trip or General>\` (configurable). yt-dlp is invoked with an argument list, never a shell string. States: not downloaded, queued, downloading (with progress), downloaded, failed. A file is marked downloaded only when it exists on disk; **Verify** resets the state if the file disappears. Not every Reel is downloadable; on failure the link is kept and *Open original* always works.

## AI analysis (optional)

"Analyze Reel" is on demand only and calls the Anthropic Claude API (`claude-opus-5-5` by default, changeable in Settings). Configure a key **outside** the app:

* environment variable `REELVAULT_AI_API_KEY` (or `ANTHROPIC_API_KEY`), or
* a file `%LOCALAPPDATA%\ReelVault\Data\config.json` containing `{"ai_api_key": "sk-ant-..."}`.

Without a key the UI explains this and everything else keeps working. Inputs: caption/metadata, your notes, transcript, up to N frames extracted from a downloaded reference (needs ffmpeg), and screenshots you upload. The brief (core idea, hook, structure, shot list, camera, editing, sound, production requirements, recreation plan, notes) is validated against a schema, saved, editable in place and exportable as Markdown. "Observed facts" are kept separate from suggestions and the UI states exactly which inputs the model was given; the model never watches the video itself.

## DaVinci Resolve

References are organized by trip on disk so the Resolve media pool can import a folder. "Open in player" and "Reveal in Explorer" work from the detail page. If Resolve's scripting module is installed (detected, not assumed), a trip page can import its references into a Resolve bin; otherwise the button is disabled with an explanation. ReelVault never moves, renames, deletes or overwrites footage.

## Reminders (optional)

Off by default. When enabled, High-priority ideas whose follow-up date has arrived show a banner in the UI (and a browser notification if you allowed it). A quiet period prevents repeats and an unchanged idea is not reminded twice.

## Building the standalone app

* Windows: `scripts\build_pc_exe.bat` produces `dist\ReelVault.exe`, a single-file console app. Run it on any Windows 10/11 64-bit PC; no Python needed. The exe is unsigned, so SmartScreen may warn on first run.
* macOS: `bash scripts/build_pc_app.sh` produces `dist/ReelVault` for the Mac it was built on (Apple Silicon or Intel). Gatekeeper may block it the first time; right-click > Open.

Data stays in the per-user data folder listed below.

## Data

```
Windows: %LOCALAPPDATA%\ReelVault\Data\      macOS: ~/Library/Application Support/ReelVault/Data/
  reelvault.db      SQLite (WAL), versioned schema with migrations
  thumbnails\       fetched thumbnails
  attachments\      screenshots you upload
  exports\          trip exports and shot lists
  backups\          "Backup DB now" copies
  logs\             reelvault.log
  config.json       optional, holds the AI key (never in git, never in the exe)
Windows: %USERPROFILE%\Videos\ReelVault\   macOS: ~/Movies/ReelVault/   downloaded references (configurable)
```

## Development (any OS)

```
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python launcher/run_server.py --data-dir ./devdata --no-browser
python -m pytest                       # 43 backend tests
cd android && ./gradlew -Preelvault.coreOnly=true :core:test   # pure-Kotlin tests without the Android SDK
cd android && ./gradlew :app:testDebugUnitTest :app:assembleDebug  # needs Android SDK
```

More: `docs/ARCHITECTURE.md`, `docs/ANDROID.md`, `docs/SECURITY.md`, `docs/CLOUD_SYNC.md`, `docs/WINDOWS_MANUAL_CHECKLIST.md`, `docs/TEST_RESULTS.md`, `docs/LIMITATIONS.md`.

## License

MIT. Third-party components keep their own licenses (see `THIRD_PARTY_LICENSES.md`).
