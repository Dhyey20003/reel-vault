# Test results for this package (environment: Linux container, Python 3.13.16, JDK 21, Gradle 8.14.3)

| Area | How | Result |
|---|---|---|
| PC backend unit/API tests (`tests/`) | `python -m pytest` | **43 passed** (sync API and token gating, dedup and capture replay, invalid captures, migrations incl. incremental upgrade, metadata failure path and no-overwrite of user edits, download state machine incl. missing-file verification, analysis without key / with fake provider / schema validation, trips and inbox semantics, suggestions never assign, categories, exports, reminders, settings and pairing, attachments, backup) |
| Web UI | Playwright (Chromium) against a live server | Inbox/All/Priority/Trips/Trip/Idea/Settings render; quick priority change, detail edit + save, trip create/assign/checklist, filter persistence across Grid/List all verified; **0 console errors** |
| PyInstaller spec | `pyinstaller reelvault.spec` on Linux | Builds a working single-file binary (21 MB). The Windows exe must be built on Windows with `scripts\build_pc_exe.bat`. |
| Android `core` module | `./gradlew -Preelvault.coreOnly=true :core:test` | **9 passed** (URL normalization parity with the PC, share text parsing, pairing URI, backoff, sync JSON) |
| Android `app` module unit tests (`CaptureRepositoryTest`, 7 tests) | needs Android SDK | **not run here** (SDK and Google Maven unreachable in the build environment) |
| Android instrumented tests (`CaptureDaoTest`, `ShareReceiverTest`) | needs device/emulator | **not run here** |
| APK build | `scripts\build_apk.bat` | **not produced here**; script verified for logic only |
| Windows `.bat` scripts | reviewed, CRLF line endings | **not executed here** (no Windows) |
| Manual checklist (`docs/WINDOWS_MANUAL_CHECKLIST.md`) | physical PC + phone | **pending**: must be done by you before relying on the invisible-capture claim |

Everything marked "not run here" is honest unverified work; the code was written carefully against current library APIs but a compile on your machine is the real test. If `build_apk.bat` reports a compile error, paste the first error line back and it can be fixed quickly.
