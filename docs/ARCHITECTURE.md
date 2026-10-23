# Architecture

```
Phone (Android)                                PC (Windows)
+----------------------------+   WiFi/LAN      +------------------------------------------+
| Instagram -> Share sheet   |  HTTP + token   | FastAPI (uvicorn), 127.0.0.1:8765        |
|  -> ShareReceiverActivity  | --------------> |  /api/sync/*   token-gated sync API       |
|  -> Room queue (persist)   |                 |  /api/*        workspace API (web UI)     |
|  -> WorkManager SyncWorker |                 |  /             vanilla JS UI (local)      |
|  Inbox / Sync / Settings UI|                 | SQLite WAL (single source of truth)       |
+----------------------------+                 | Job runner: metadata, download, analysis  |
                                               +------------------------------------------+
```

## PC workspace

* `launcher/run_server.py`: entry point and PyInstaller target. Reads settings, prints LAN IP, starts uvicorn, opens the browser.
* `reelvault/app.py`: FastAPI factory. Private-network middleware, routers, static files.
* `reelvault/db.py`: SQLite connection management (WAL, foreign keys, busy timeout), one writer lock per process, **append-only migration list** recorded in `schema_migrations` and mirrored to `PRAGMA user_version`.
* `reelvault/repo.py`: data access (ideas, trips, categories, receipts, devices, attachments). Last-writer-wins on `updated_at`; the UI sends `expected_updated_at` and gets `409` if the row changed under it.
* `reelvault/workspace.py`: orchestrates background work through `services/jobs.py` (a small thread pool keyed by job type + idea so a job never runs twice at once).
* `reelvault/services/metadata.py`: `MetadataProvider` protocol with `ytdlp` and `oembed` implementations; `fetch_metadata` tries them in the configured order.
* `reelvault/services/downloader.py`: structured yt-dlp invocation, progress parsing, output verification.
* `reelvault/services/analysis.py`: `AnalysisProvider` protocol, `AnthropicProvider`, `CreativeBrief` schema (pydantic), Markdown rendering.
* `reelvault/services/export.py`, `resolve.py`, `reminders.py`, `frames.py`, `tools.py`.
* `reelvault/static/`: `index.html`, `app.js` (hash router, views, polling of in-flight jobs), `app.css`, `icon.svg`.

## Data model (PC, SQLite)

* `settings(key, value JSON)`: non-secret settings and the pairing token.
* `categories`, `ideas` (see `db.py` migration 1 for every column), `trips`, `idea_trips` (many-to-many), `download_jobs`, `analysis_jobs`, `attachments`, `devices`, `capture_receipts`, `schema_migrations`.
* `ideas.original_url` is always the URL as shared; `normalized_url` is the dedup key; `canonical_url` is filled by metadata when known.
* Soft delete via `deleted_at`.

## Sync protocol

`POST /api/sync/captures` with header `X-ReelVault-Token` and body:

```json
{"device_id": "uuid", "device_name": "Pixel 8", "captures": [
  {"capture_id": "uuid", "shared_text": "...", "url": "https://...", "captured_at": "2026-10-20T10:00:00Z"}]}
```

Response: one result per capture, `created` | `duplicate` | `invalid`, plus `idea_id`. Results are recorded in `capture_receipts`, so a retried `capture_id` (after a lost response) gets the same answer and never creates a second idea. Dedup is on the normalized URL across all non-deleted ideas; an intentional copy can be created from the PC with `allow_duplicate`.

`GET /api/sync/ping` is used by the phone's Test connection.

## Android

See `docs/ANDROID.md`. The pure-Kotlin `core` module mirrors the PC's URL normalization so both sides agree on the dedup key.

## Conflicts and offline

Only the phone writes captures; only the PC edits ideas. There is no two-way merge in v1, so conflicts cannot arise between devices. Within the PC, the detail page uses optimistic concurrency (`expected_updated_at`). Viewing synced ideas never needs the network; metadata, downloads and analysis are the only network users and all run in the background.
