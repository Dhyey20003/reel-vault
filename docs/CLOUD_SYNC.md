# Adding a cloud sync backend later

v1 ships one sync implementation: the LAN HTTP backend (`reelvault/api/sync.py` on the PC, `SyncClient` + `SyncWorker` on Android). The design keeps the pieces that would change behind small seams:

**Android.** `SyncWorker` only depends on `SyncClient.sendCaptures(deviceId, deviceName, List<CaptureDto>)` returning `Outcome<List<CaptureResult>>`. A cloud implementation (for example a Supabase Edge Function or a table insert via PostgREST) implements the same method: build the batch with `SyncProtocol.batchJson`, post it, map the reply to `CaptureResult`. Choose the implementation from `Prefs` (a `sync_backend` key) and nothing else in the app changes. The queue, dedup and retry logic are backend-agnostic.

**PC.** `Repo.receive_captures()` is the single entry point that turns captures into ideas with receipts. A cloud puller would be a background job (`services/jobs.py`) that fetches new captures from the cloud table and calls the same function; ideas synced that way are indistinguishable from LAN ones. If PC-side edits should flow back to a cloud, add an `updated_at`-based outbox on `ideas`; the schema already has stable ids and timestamps.

**Auth.** The LAN token stays local. A cloud backend would use its own per-user credentials, entered in the app and in the PC settings; never embed project keys in the APK or exe. Treat any publishable key the same as a secret in this app and keep it in `config.json`.

**Conflict policy.** Keep last-writer-wins on `updated_at` for the metadata fields and never let the cloud overwrite `original_url`.
