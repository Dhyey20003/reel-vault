# Known limitations and assumptions (v1)

* **APK and exe were not prebuilt in the packaging environment.** The build machine had no access to Google's Android repositories (dl.google.com was blocked) and was Linux, so `dist\ReelVault.apk` and `dist\ReelVault.exe` must be produced on your Windows PC with `scripts\build_apk.bat` and `scripts\build_pc_exe.bat`. The PyInstaller spec was validated by building a Linux binary with the same spec; the Android `app` module compiles only once the SDK is present. See `docs/TEST_RESULTS.md`.
* **Instagram metadata** depends on yt-dlp or an official oEmbed app token. Without either, Instagram ideas show *metadata unavailable* and you type the title yourself. This is expected and never counts as a failed capture.
* **Downloads** need yt-dlp and work only for content yt-dlp can access; private or login-gated Reels fail honestly.
* **Plain HTTP on the LAN** for sync (see `docs/SECURITY.md`).
* **AI analysis** needs a key and costs money per run. The model cannot watch video; it only sees text, extracted frames and screenshots.
* **Reminders** are shown by the web UI (banner + browser notification). There is no Windows tray service in v1, so you see reminders when the workspace is open.
* **LAN access and port changes** need a restart of the server.
* **Resolve scripting** is detected, not bundled; importing into a bin requires Resolve to run with external scripting enabled.
* **No multi-user, no accounts, no social features** by design.
