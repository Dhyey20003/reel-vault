# Known limitations (v2.0.0)

* **Binaries and APK are not prebuilt here** (Android SDK unreachable from the build environment; no macOS/Windows host). Build them with the scripts; the Android `app` module compiled only in your environment, so a first build may surface a compile error I could not see. Send the first error line.
* **Share sheet ranking** is decided by Android. The Sharing Shortcut makes "Save to ReelVault" eligible for the direct-share row; pinning it (long-press in the share sheet) is the reliable one-tap path. There is no button inside Instagram's own UI.
* **Android background limits**: sync runs through WorkManager; with battery optimisation on some phones it may wait until the app is opened or the periodic window (15 min) fires. Captures are never lost; they wait on the phone.
* **Metadata** for Instagram depends on yt-dlp or an official oEmbed token; private/login-only sources are reported, not bypassed.
* **Playback copies** need ffmpeg; without it, non-MP4/H.264 files show "Needs ffmpeg". H.264 is not decodable in some open-source Chromium builds (tests used WebM); mainstream browsers play MP4/H.264.
* **Local transcription** requires a whisper CLI you install; without it the transcript field stays empty unless typed.
* **Local AI quality** depends on the model and RAM; frames are samples, not the video. Outputs are suggestions to edit.
* **Plain HTTP on the LAN** for phone sync (see `docs/SECURITY.md`); Ollama has no authentication and must stay on localhost or a private network/tunnel.
* **LAN access and port changes** still need a restart.
* **Reminders** appear in the web UI only.
