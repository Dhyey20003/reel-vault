# Changelog

## 2.0.0 (branch `reelvault-v2`)
**Desktop gallery**
- New visual system; Grid and vertical Feed modes with keyboard navigation (j/k, arrows); only the active video plays, neighbours preload metadata, others pause.
- In-app player: seek, volume, speed, repeat, fullscreen, A–B loop (persisted), timestamped notes that jump to the moment.
- Detail sheet keeps list filters and scroll position; author, dates, source and technical metadata moved into an expandable section.
- Add menu: bulk link entry with per-item outcomes; drag-and-drop or file import of local videos (originals preserved, content-hash dedup).
- Quick "+ Trip" from cards, feed and detail with recent trips, inline creation and bulk assignment; multi-trip membership kept.
- Creative tags with filter and suggestions; "Adapt for my trip" generates an editable shot list/plan separating observed reference details from proposals.
- Repair centre: connection status, unsynced devices, failed/audio-only downloads, missing files/thumbnails, missing tools, local AI errors, targeted retries, redacted diagnostics download.

**Media and downloads**
- yt-dlp now requests video+audio (merged via ffmpeg) with combined-format fallback; never audio-only.
- ffprobe validation before "downloaded": audio-only and invalid files are marked failed with the file kept; silent videos accepted.
- Browser-playable copies (H.264/AAC MP4) created only when needed; originals untouched; range-capable media route serves only files recorded on the idea.
- Generated cover frames when no artwork, cover-frame selection, custom cover upload. Quality limit and free-disk guard.
- Cancellation for downloads and analyses; interrupted jobs resume after restart.

**Local AI**
- Ollama provider (local-first default); hardware-aware model recommendation; scene-aware frame sampling; optional local whisper transcription; schema validation with one repair attempt; result cache; cloud provider now explicit opt-in.
- Setup/check/start scripts, config example, self-test tool, `docs/LOCAL_AI.md`.

**Pipeline**
- Optional capture → download → thumbnail → analysis automation with pause/resume, disk check, per-idea stage persisted.

**Android**
- Sharing Shortcut "Save to ReelVault" for the share sheet's direct-share row; paste-link fallback with clipboard button.
- Captures acknowledged per item; partial batches and lost responses handled; transient failures retried forever on a slow schedule (never abandoned); permanent failures explained; retry after token/host change; optional sync on WiFi without internet.
- QR pairing fills fields, validates the connection, and explains failures (malformed code, token rejected, LAN off/firewall, wrong network); PC side lists all adapters and lets you choose the advertised address.
- Refreshed Compose UI with source badges, status dots, last successful sync.
- Room schema 2 (migration from 1 keeps the queue). Application ID and signing unchanged.

**Data**
- Migrations 4–5; `tools/upgrade_db.py` backup/migrate/rollback with a tested v1→v2→v1 path.
