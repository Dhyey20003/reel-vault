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


def run_download(*, ytdlp_path: str, ffmpeg_path: str | None, url: str, target_dir: Path, idea_id: str,
                 on_progress: Callable[[float, str], None] | None = None, timeout: int = 1800) -> Path:
    if not is_safe_url(url):
        raise DownloadError("Refusing to download a non-http(s) URL")
    target_dir.mkdir(parents=True, exist_ok=True)
    template = str(target_dir / f"{idea_id[:8]} - %(title).80B.%(ext)s")
    args = [
        ytdlp_path,
        "--no-playlist", "--newline", "--no-warnings", "--no-overwrites", "--restrict-filenames",
        "--socket-timeout", "30", "--retries", "3",
        "--output", template,
        "--print", "after_move:filepath",
        "--no-simulate",
    ]
    if ffmpeg_path:
        args += ["--ffmpeg-location", ffmpeg_path]
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
        raise DownloadError(err[:400])
    out = Path(printed_path) if printed_path else None
    if out is None or not out.exists():
        # Fallback: newest file in target_dir that starts with the idea prefix.
        cands = sorted(target_dir.glob(f"{idea_id[:8]} - *"), key=lambda p: p.stat().st_mtime, reverse=True)
        cands = [c for c in cands if c.is_file() and not c.name.endswith(".part")]
        out = cands[0] if cands else None
    if out is None or not out.exists() or out.stat().st_size == 0:
        raise DownloadError("yt-dlp finished but no output file was found; the reel may not be downloadable")
    return out


def tail_log(lines: list[str], n: int = 30) -> str:
    return "\n".join(lines[-n:])


def describe_states() -> dict[str, Any]:
    return {"states": ["not_downloaded", "queued", "downloading", "downloaded", "failed"]}
