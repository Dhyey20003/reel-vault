"""Reference download via yt-dlp with structured arguments and a verified state machine.

States per item: not_downloaded -> queued -> downloading -> downloaded | failed.
A file is only marked downloaded when it exists on disk with a non-zero size.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..urlnorm import is_safe_url

log = logging.getLogger("reelvault.download")
_PROGRESS_RE = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 _.()-]+")


def safe_folder_name(name: str, fallback: str = "General") -> str:
    cleaned = _SAFE_NAME_RE.sub("", name or "").strip().strip(".")
    return cleaned[:60] or fallback


class DownloadError(Exception):
    pass


QUALITY_HEIGHT = {"best": None, "1080p": 1080, "720p": 720, "480p": 480}


def format_selector(ffmpeg_available: bool, quality: str = "best") -> str:
    """Video+audio merged when ffmpeg can merge; otherwise a single combined format that already has both.
    Never falls back to audio-only."""
    h = QUALITY_HEIGHT.get(quality)
    cap = f"[height<={h}]" if h else ""
    if ffmpeg_available:
        return f"bv*{cap}[ext=mp4]+ba[ext=m4a]/bv*{cap}+ba/b{cap}[vcodec!=none][acodec!=none]/b[vcodec!=none][acodec!=none]"
    return f"b{cap}[ext=mp4][vcodec!=none][acodec!=none]/b{cap}[vcodec!=none][acodec!=none]/b[vcodec!=none][acodec!=none]"


def run_download(*, ytdlp_path: str, ffmpeg_path: str | None, url: str, target_dir: Path, idea_id: str,
                 on_progress: Callable[[float, str], None] | None = None, timeout: int = 1800,
                 quality: str = "best", should_cancel: Callable[[], bool] | None = None) -> Path:
    if not is_safe_url(url):
        raise DownloadError("Refusing to download a non-http(s) URL")
    target_dir.mkdir(parents=True, exist_ok=True)
    template = str(target_dir / f"{idea_id[:8]} - %(title).80B.%(ext)s")
    args = [
        ytdlp_path,
        "--no-playlist", "--newline", "--no-warnings", "--no-overwrites", "--restrict-filenames",
        "--socket-timeout", "30", "--retries", "3",
        "-f", format_selector(bool(ffmpeg_path), quality),
        "--output", template,
        "--print", "after_move:filepath",
        "--no-simulate",
    ]
    if ffmpeg_path:
        args += ["--ffmpeg-location", ffmpeg_path, "--merge-output-format", "mp4"]
    args += ["--", url]
    log.info("yt-dlp start idea=%s", idea_id)
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as e:
        raise DownloadError(f"Could not start yt-dlp: {e}") from e
    lines: list[str] = []
    printed_path: str | None = None
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            if not line:
                continue
            lines.append(line)
            if len(lines) > 400:
                del lines[:100]
            if should_cancel and should_cancel():
                proc.kill()
                raise DownloadError("cancelled")
            m = _PROGRESS_RE.search(line)
            if m and on_progress:
                on_progress(min(100.0, float(m.group(1))), line)
            elif not line.startswith("[") and (os.path.isabs(line) or line.startswith(str(target_dir))):
                printed_path = line.strip()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as e:
        proc.kill()
        raise DownloadError("yt-dlp timed out") from e
    if proc.returncode != 0:
        err = next((l for l in reversed(lines) if "ERROR" in l), lines[-1] if lines else f"exit code {proc.returncode}")
        raise DownloadError(explain_error(err))
    out = Path(printed_path) if printed_path else None
    if out is None or not out.exists():
        # Fallback: newest file in target_dir that starts with the idea prefix.
        cands = sorted(target_dir.glob(f"{idea_id[:8]} - *"), key=lambda p: p.stat().st_mtime, reverse=True)
        cands = [c for c in cands if c.is_file() and not c.name.endswith(".part")]
        out = cands[0] if cands else None
    if out is None or not out.exists() or out.stat().st_size == 0:
        raise DownloadError("yt-dlp finished but no output file was found; the reel may not be downloadable")
    return out


def explain_error(err: str) -> str:
    low = err.lower()
    if "login" in low or "cookies" in low or "sign in" in low or "private" in low:
        return "This source needs a login or is private; ReelVault does not bypass access controls. " + err[:200]
    if "unavailable" in low or "removed" in low or "not available" in low or "404" in low:
        return "The video is unavailable or was deleted at the source. " + err[:200]
    if "requested format is not available" in low:
        return "No format with both video and audio was offered; install ffmpeg so separate streams can be merged. " + err[:200]
    if "rate" in low and "limit" in low:
        return "The source is rate-limiting requests; try again later. " + err[:200]
    return err[:400]


def tail_log(lines: list[str], n: int = 30) -> str:
    return "\n".join(lines[-n:])


def describe_states() -> dict[str, Any]:
    return {"states": ["not_downloaded", "queued", "downloading", "downloaded", "failed"]}
