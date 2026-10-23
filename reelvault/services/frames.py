"""Frame extraction from a local reference video using ffmpeg (optional)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def video_duration(ffprobe_path: str | None, video: Path) -> float | None:
    if not ffprobe_path:
        return None
    try:
        out = subprocess.run([ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of",
                              "default=noprint_wrappers=1:nokey=1", str(video)], capture_output=True, text=True,
                             timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def extract_frames(ffmpeg_path: str, ffprobe_path: str | None, video: Path, out_dir: Path, count: int = 4) -> list[Path]:
    """Extracts up to ``count`` evenly spaced JPEG frames (max 768px wide). Returns the files that exist."""
    if count <= 0 or not video.exists():
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = video_duration(ffprobe_path, video) or 15.0
    frames: list[Path] = []
    for i in range(count):
        t = max(0.0, duration * (i + 0.5) / count)
        dest = out_dir / f"frame_{i + 1:02d}.jpg"
        try:
            subprocess.run([ffmpeg_path, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                            "-vf", "scale='min(768,iw)':-2", "-q:v", "4", str(dest)], capture_output=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            continue
        if dest.exists() and dest.stat().st_size > 0:
            frames.append(dest)
    return frames
