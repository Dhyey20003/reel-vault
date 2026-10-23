# Manual checklist (ReelVault v1.0.0, Windows or macOS)

Tick each item on a real PC or Mac and a real Android phone. On macOS replace each `scripts\x.bat` with `bash scripts/x.sh` (`build_pc_exe.bat` is `build_pc_app.sh`), `Explorer` with Finder, and the data folder with `~/Library/Application Support/ReelVault/Data`. Record the result in `docs/TEST_RESULTS.md`.

## Setup
- [ ] `scripts\setup.bat` completes with "[OK] Setup finished" on a PC with only Python installed (no internet needed).
- [ ] `scripts\run_server.bat` prints the data folder, `http://127.0.0.1:8765/` and the LAN IP, and opens the browser to the Inbox.
- [ ] Settings > tick LAN access > Save > restart: console shows `LAN access: ENABLED`. Windows Firewall prompt allowed for private networks only.
- [ ] `scripts\build_pc_exe.bat` produces `dist\ReelVault.exe`; double-clicking it starts the same workspace (and it refuses with a clear message if the port is already in use).
- [ ] `scripts\build_apk.bat` with no JDK or SDK prints exactly what to install and exits; with both present it produces `dist\ReelVault.apk`.

## Phone
- [ ] Install `dist\ReelVault.apk` (unknown sources allowed). App opens to an empty Inbox.
- [ ] Settings > Scan pairing QR scans the PC's QR and fills host/port/token; Test connection says "Connected to the PC".
- [ ] Typing a public IP (e.g. 8.8.8.8) as host is refused on Save.

## Hero flow
- [ ] In Instagram, open a Reel > Share > "Save to ReelVault". Instagram stays in front, no app window opens, at most a brief toast is shown. Time from tap to being back in Instagram is well under a second.
- [ ] Within ~10 s the idea appears in the PC Inbox with the link (title/thumbnail if metadata was available, otherwise "metadata unavailable").
- [ ] Phone Inbox shows the capture as "synced".

## Reliability
- [ ] Turn WiFi off on the phone (or stop the PC server), share two Reels: phone shows them as "pending". Turn WiFi/server back on: they sync without any tap (within the retry delay or 15 min periodic), or immediately with Sync now.
- [ ] Force-stop the ReelVault app (Settings > Apps) after sharing while offline; reopen later: the capture is still there and syncs.
- [ ] Share the same Reel twice (and once with a different `?igsh=` parameter): the PC has one idea; the phone shows one row (or "synced (already on PC)").
- [ ] PC > Add idea by link with an existing link offers to open the existing idea; with "Save even if exists" it creates a copy.
- [ ] Generate new token on the PC: phone sync fails with "token rejected"; re-scan QR and Retry failed syncs again.

## Workspace
- [ ] Edit every field in the detail page, Save, restart the server: all values persist. Change status/priority from a list card: persists.
- [ ] Create trips (Udaipur, Kedarnath, Tungnath, Future Travel Vlogs, General Reel Inspiration); assign an idea to one, then to two; Inbox no longer shows it; Trip page shows it.
- [ ] Search and each filter work in All Ideas; switching Grid/List keeps the filters.
- [ ] Categories: add, rename, delete with reassign.
- [ ] Metadata unavailable path: an idea with no metadata keeps its link; manual title works; Retry metadata re-queues.
- [ ] With yt-dlp installed: Download reference shows progress, ends "downloaded", file is in `Videos\ReelVault\<Trip>\`; Open in player and Reveal in Explorer work. Delete the file manually, click Verify: state returns to not downloaded. Without yt-dlp: button disabled with install hint.
- [ ] Without an AI key: Analyze is disabled with instructions. With a key: Analyze runs, brief appears with "Inputs given to the model" line, fields are editable, Save brief persists, Export .md downloads.
- [ ] Trip > Build shot list downloads Markdown and plain text. Export trip folder creates `Data\exports\<Trip>-<stamp>\` with trip.md, shotlist.md, trip.json and copied references; originals untouched.
- [ ] Reminders: enable, set an idea to High with a past follow-up date, reload: banner appears; Dismiss hides it; it does not return until the idea changes.
- [ ] Backup DB now creates a file in `Data\backups\`.

## v2 additions
- [ ] Upgrade: with a v1 install running, stop it, run `upgrade_v2`, start v2: all ideas, trips, notes, categories, attachments and pairing are still there; `Data\backups\pre-v2-*.db` exists.
- [ ] Rollback: run `rollback_v2` with that backup and start v1 again: works. Then re-run the upgrade.
- [ ] Install the v2 APK over v1 without uninstalling: the phone Inbox still lists the old captures; pairing kept.
- [ ] Share from Instagram: "Save to ReelVault" visible in the share sheet (direct-share row after pinning); back in Instagram immediately; capture appears on the PC. Try YouTube and a Short too. Try Paste + Save.
- [ ] Pairing: scan the PC QR; host/port/token fill in and the card says "Connected". Then: rotate the token on the PC → phone shows "token rejected" with the hint; rescan → Retry failed syncs. Turn LAN access off → message names LAN access/firewall.
- [ ] Offline PC: share 3 reels with the PC off; phone shows pending/"waiting for PC (retrying)"; start the PC; they arrive within 15 min (or at once with Sync now); force-stop and reopen the app: queue intact.
- [ ] Download a reel with ffmpeg installed: file has video and audio; play it inside ReelVault; seek; A–B loop; add a timestamped note; it plays inside the trip view too. Without ffmpeg: audio-only result is reported as failed (file kept) and listed in Repair centre.
- [ ] Drag a local MP4 onto the Library: imported, playable, cover generated; drag the same file again: not duplicated.
- [ ] Local AI: run `scripts/local_ai/setup_ollama_mac.sh`, Test local AI is green, Analyze an idea with a downloaded video: brief lists frames analysed; turn WiFi off during analysis: still completes (no external calls).
- [ ] Adapt for my trip generates a plan; edits save.
- [ ] Pipeline: enable auto-download, share a reel: it downloads by itself; pause stops new work; restart the server mid-download: it resumes.
