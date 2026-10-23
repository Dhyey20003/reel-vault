# Third-party components

PC workspace (Python, pinned in `requirements.txt`, wheels in `wheelhouse/`): FastAPI, Starlette, Pydantic, Uvicorn, h11, anyio, click, colorama, python-multipart, segno (QR codes), anthropic SDK (httpx2, httpcore2, jiter, distro, sniffio, truststore, docstring_parser, opentelemetry-api), typing-extensions, tzdata, idna, certifi, PyInstaller (build only). All MIT, BSD or Apache-2.0 licensed; each wheel contains its license text.

Optional external tools you install yourself: yt-dlp (Unlicense), ffmpeg (LGPL/GPL), DaVinci Resolve scripting API (Blackmagic Design).

Android app (resolved by Gradle, see `android/app/build.gradle.kts`): AndroidX (Apache-2.0), Jetpack Compose (Apache-2.0), Room (Apache-2.0), WorkManager (Apache-2.0), security-crypto (Apache-2.0), kotlinx-coroutines (Apache-2.0), zxing-android-embedded (Apache-2.0), ZXing core (Apache-2.0).
