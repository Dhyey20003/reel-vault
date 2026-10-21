# Android capture app

Package `app.reelvault.capture`, minSdk 26, targetSdk 35. Modules: `core` (pure Kotlin, unit-tested on the JVM) and `app`.

## Invisible capture

`ShareReceiverActivity` is registered for `ACTION_SEND` with `text/plain` (and `text/*`). Instagram shares a plain-text extra like `"Reel by @user https://www.instagram.com/reel/XXXX/?igsh=..."`; some apps also set `EXTRA_SUBJECT`. The activity:

1. Reads `EXTRA_TEXT` and `EXTRA_SUBJECT`.
2. On an IO thread, `CaptureRepository.save()` extracts the first http(s) URL, computes the normalized form, assigns a UUID `capture_id` and inserts into Room. If the normalized URL is already queued, no second row is created (a failed row is reset to pending).
3. Enqueues `SyncWorker` through WorkManager (`REPLACE` policy so a capture during a backoff wait runs immediately).
4. Finishes with no transition animation. The theme is `Theme.Translucent.NoTitleBar` with a transparent window, `excludeFromRecents`, `noHistory` and an empty `taskAffinity`, so Instagram stays in front and nothing appears in Recents.

An optional short toast ("Saved to ReelVault") is on by default and can be turned off in Settings. No AI, download or metadata work happens on the phone.

**Verification status:** the flow is covered by an instrumented test (`ShareReceiverTest`: launches the activity with a share intent, asserts the row is persisted and the activity reaches DESTROYED on its own). The Android SDK was not available in the environment where this package was produced, so the APK and the instrumented tests could not be executed there; run them on your machine (`gradlew connectedDebugAndroidTest`) and on a physical device via the manual checklist before relying on the no-interruption behaviour. See `docs/TEST_RESULTS.md`.

## Queue and retries

`Capture` rows carry `sync_state` (pending, synced, failed), `attempts`, `next_attempt_at`, `last_error`. `SyncWorker` sends everything due in one batch. Transport failures (PC off, wrong WiFi) schedule a retry with `Backoff` (30s, 1m, 2m ... capped at 30 min; after 8 attempts the row is marked failed for manual retry) and return `Result.retry()` so WorkManager also backs off. A periodic worker (15 min) picks up anything left when the PC is back; it is only registered while auto-sync is enabled. `401` (token rejected), `403`, `404` and malformed hosts are treated as permanent and need a settings fix plus **Retry failed**.

## Security on the phone

* Token in `EncryptedSharedPreferences` (`MasterKey` AES256-GCM), excluded from backups and device transfer, never logged, masked in the UI.
* The client refuses any host that is not a private, loopback, link-local or CGNAT address or a `.local/.lan/.home` name, so the app can never talk to the public internet.
* Cleartext HTTP is permitted only because v1 syncs on the private LAN (see `docs/SECURITY.md`).

## Building

`scripts\build_apk.bat` (Windows) or `cd android && ./gradlew :app:assembleDebug`. Output: `app/build/outputs/apk/debug/app-debug.apk`, copied to `dist/ReelVault.apk`. The debug build is signed with the standard debug key, which is fine for installing on your own phone. For a release build, add a signing config to `app/build.gradle.kts`.

QR scanning uses `zxing-android-embedded`; the camera permission is requested only when you tap **Scan pairing QR**.
