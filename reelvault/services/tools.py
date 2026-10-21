"""Detection of optional external tools (yt-dlp, ffmpeg). Nothing is installed automatically."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _which(configured: str, name: str) -> str | None:
    if configured:
        p = Path(configured)
        if p.is_file():
            return str(p)
        if p.is_dir():
            cand = p / (name + (".exe" if os.name == "nt" else ""))
            if cand.is_file():
                return str(cand)
        return None
    return shutil.which(name)


def _version(path: str, args: list[str]) -> str | None:
    try:
        out = subprocess.run([path, *args], capture_output=True, text=True, timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        line = (out.stdout or out.stderr).strip().splitlines()
        return line[0][:120] if line else None
    except (OSError, subprocess.SubprocessError):
        return None


def detect_tools(ytdlp_setting: str = "", ffmpeg_setting: str = "") -> dict[str, Any]:
    ytdlp = _which(ytdlp_setting, "yt-dlp")
    ffmpeg = _which(ffmpeg_setting, "ffmpeg")
    ffprobe = _which(ffmpeg_setting, "ffprobe") if ffmpeg_setting else shutil.which("ffprobe")
    return {
        "ytdlp": {"found": bool(ytdlp), "path": ytdlp, "version": _version(ytdlp, ["--version"]) if ytdlp else None,
                  "install_hint": "Install yt-dlp: winget install yt-dlp  (or download yt-dlp.exe from https://github.com/yt-dlp/yt-dlp/releases and put it on PATH or set its path in Settings)"},
        "ffmpeg": {"found": bool(ffmpeg), "path": ffmpeg, "version": _version(ffmpeg, ["-version"]) if ffmpeg else None,
                   "install_hint": "Install ffmpeg: winget install Gyan.FFmpeg  (or download from https://ffmpeg.org/download.html and put ffmpeg.exe on PATH or set its folder in Settings)"},
        "ffprobe": {"found": bool(ffprobe), "path": ffprobe},
    }
