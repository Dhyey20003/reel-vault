"""Media inspection, playback conversion, thumbnails. All via ffprobe/ffmpeg argument lists."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

BROWSER_VIDEO = {"h264", "vp8", "vp9", "av1"}
BROWSER_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac", None}
BROWSER_EXT = {".mp4", ".webm", ".m4v"}
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def probe(ffprobe: str | None, path: Path) -> dict[str, Any]:
    """Returns {'status': ok|audio_only|invalid|unprobed, 'duration', 'video_codec', 'audio_codec', 'width', 'height', 'container'}."""
    info: dict[str, Any] = {"status": "unprobed", "duration": None, "video_codec": None, "audio_codec": None,
                            "width": None, "height": None, "container": path.suffix.lower().lstrip(".")}
    if not path.is_file() or path.stat().st_size == 0:
        info["status"] = "invalid"; info["error"] = "file missing or empty"
        return info
    if not ffprobe:
        return info
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                             capture_output=True, text=True, timeout=60, creationflags=_FLAGS)
        data = json.loads(out.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        info["status"] = "invalid"; info["error"] = f"ffprobe failed: {e}"
        return info
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) != 1), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        info["duration"] = float((data.get("format") or {}).get("duration") or (v or a or {}).get("duration") or 0) or None
    except ValueError:
        info["duration"] = None
    if v:
        info.update(video_codec=v.get("codec_name"), width=v.get("width"), height=v.get("height"))
    if a:
        info["audio_codec"] = a.get("codec_name")
    if not v and a:
        info["status"] = "audio_only"
    elif not v:
        info["status"] = "invalid"; info["error"] = "no video stream"
    elif not info["duration"] or info["duration"] <= 0:
        info["status"] = "invalid"; info["error"] = "no usable duration"
    else:
        info["status"] = "ok"
    return info


def browser_compatible(info: dict[str, Any], path: Path) -> bool:
    return (info.get("status") == "ok" and path.suffix.lower() in BROWSER_EXT
            and info.get("video_codec") in BROWSER_VIDEO and info.get("audio_codec") in BROWSER_AUDIO)


def make_playback_copy(ffmpeg: str, src: Path, dest: Path, info: dict[str, Any]) -> Path:
    """Creates a browser-playable MP4 next to the original (original untouched). Re-encodes only what is needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    vcopy = info.get("video_codec") in BROWSER_VIDEO and info.get("video_codec") != "vp8"
    acopy = info.get("audio_codec") in {"aac", "mp3"} or info.get("audio_codec") is None
    args = [ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
            "-c:v", "copy" if vcopy else "libx264", *([] if vcopy else ["-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]),
            "-c:a", "copy" if acopy else "aac", "-movflags", "+faststart", str(dest)]
    subprocess.run(args, capture_output=True, timeout=3600, creationflags=_FLAGS)
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError("conversion produced no file")
    return dest


def frame_at(ffmpeg: str, src: Path, dest: Path, t: float, width: int = 720) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(src), "-frames:v", "1",
                        "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", str(dest)], capture_output=True, timeout=120, creationflags=_FLAGS)
    except (OSError, subprocess.SubprocessError):
        return None
    return dest if dest.is_file() and dest.stat().st_size > 0 else None


def scene_sample_times(ffmpeg: str, src: Path, duration: float, count: int) -> list[float]:
    """Scene-change timestamps (ffmpeg scene filter) thinned to `count`; falls back to even spacing."""
    even = [duration * (i + 0.5) / count for i in range(count)] if duration else []
    if count <= 0 or not duration:
        return even
    try:
        out = subprocess.run([ffmpeg, "-loglevel", "info", "-i", str(src), "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"],
                             capture_output=True, text=True, timeout=300, creationflags=_FLAGS)
    except (OSError, subprocess.SubprocessError):
        return even
    import re
    times = sorted({float(m) for m in re.findall(r"pts_time:([0-9.]+)", out.stderr or "")})
    times = [t for t in times if 0 <= t < duration]
    if len(times) < 2:
        return even
    if len(times) <= count:
        picks = times
    else:
        step = len(times) / count
        picks = [times[int(i * step)] for i in range(count)]
    return sorted(set([0.5] + picks))[:count]


def file_fingerprint(path: Path) -> str:
    st = path.stat()
    return hashlib.sha1(f"{path.name}:{st.st_size}:{int(st.st_mtime)}".encode()).hexdigest()[:16]


def content_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
