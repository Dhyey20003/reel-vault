# Security notes

* **Token-gated sync.** A random 32-byte URL-safe token is generated on first run and compared with `hmac.compare_digest`. Missing or wrong tokens get `401`. Rotate it from Settings.
* **Localhost by default.** LAN access must be enabled explicitly and requires a restart. When enabled, the server binds to all interfaces but a middleware refuses any client outside loopback, RFC1918, link-local, IPv6 ULA and CGNAT ranges (`reelvault/netutil.py`). Allow the Windows Firewall prompt only for **private** networks.
* **Plain HTTP on the LAN (v1 limitation).** Traffic between phone and PC is not encrypted. Anyone on the same WiFi who can sniff traffic could read captured links and the token. Use only on networks you trust (home WiFi, your own hotspot). HTTPS with a self-signed certificate and a QR-delivered fingerprint is the planned next step; the Android client keeps the host check in place regardless.
* **No secrets in code, exe, DB or logs.** The AI key lives in an environment variable or `config.json` in the data folder; `config.json` is gitignored and is read at request time only. The token is in the DB `settings` table on the PC (local file) and in EncryptedSharedPreferences on Android.
* **Input validation.** Only `http(s)` URLs up to 2048 characters are accepted; schemes like `javascript:` and `file:` are rejected. Pydantic validates every request body. Filenames for uploads are reduced to their base name and screenshots are limited to image types and 20 MB.
* **Safe external processes.** yt-dlp and ffmpeg are started with argument lists (`subprocess` without `shell=True`), the URL is passed after `--`, and output file names use yt-dlp's restricted-filename mode.
* **Attachments and thumbnails** are served only by id from inside the data folder.
* **Never destructive to footage.** Exports copy; downloads use `--no-overwrites`; nothing in ReelVault moves, renames or deletes media files.
