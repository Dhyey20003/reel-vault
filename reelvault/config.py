"""Paths, settings and (non-secret) configuration for the PC workspace.

Secrets (the AI API key) are never stored in the database. They come from an
environment variable or from ``config.json`` inside the data folder, which is
outside the program folder and never checked into source control.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PORT = 8765

DEFAULT_CATEGORIES = [
    "Travel", "Cinematic", "Storytelling", "Comedy", "Fitness", "Transitions", "Other",
]
STATUSES = ["To Make", "In Progress", "Published"]
DEFAULT_PRIORITIES = ["Low", "Normal", "High"]
METADATA_STATUSES = ["pending", "fetching", "ok", "unavailable"]
DOWNLOAD_STATUSES = ["not_downloaded", "queued", "downloading", "downloaded", "failed"]
ANALYSIS_STATUSES = ["none", "queued", "running", "done", "failed"]

# Settings that live in the database `settings` table with their defaults.
SETTING_DEFAULTS: dict[str, Any] = {
    "server_name": "ReelVault PC",
    "lan_enabled": False,
    "port": DEFAULT_PORT,
    "media_dir": "",                    # empty = default_media_dir()
    "priorities": DEFAULT_PRIORITIES,
    "metadata_providers": ["ytdlp", "oembed"],
    "metadata_auto": True,
    "ai_provider": "anthropic",
    "ai_model": "claude-opus-5-5",
    "ai_frames": 4,                     # frames extracted from a local reference (0 = none)
    "reminders_enabled": False,
    "reminder_quiet_hours": 24,
    "ytdlp_path": "",                   # empty = search PATH
    "ffmpeg_path": "",
    "instagram_oembed_token": "",       # optional Facebook Graph token for the official oEmbed endpoint
    "resolve_scripting_path": "",
}


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def program_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def static_dir() -> Path:
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", program_dir()))
        return base / "reelvault" / "static"
    return Path(__file__).resolve().parent / "static"


def default_data_dir() -> Path:
    env = os.environ.get("REELVAULT_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ReelVault" / "Data"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "ReelVault" / "Data"


def default_media_dir() -> Path:
    env = os.environ.get("REELVAULT_MEDIA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        profile = os.environ.get("USERPROFILE") or str(Path.home())
        return Path(profile) / "Videos" / "ReelVault"
    return Path.home() / "Videos" / "ReelVault"


@dataclass
class Paths:
    data_dir: Path
    db_path: Path = field(init=False)
    thumbnails: Path = field(init=False)
    attachments: Path = field(init=False)
    exports: Path = field(init=False)
    logs: Path = field(init=False)
    backups: Path = field(init=False)
    tmp: Path = field(init=False)
    config_file: Path = field(init=False)

    def __post_init__(self) -> None:
        d = Path(self.data_dir)
        self.data_dir = d
        self.db_path = d / "reelvault.db"
        self.thumbnails = d / "thumbnails"
        self.attachments = d / "attachments"
        self.exports = d / "exports"
        self.logs = d / "logs"
        self.backups = d / "backups"
        self.tmp = d / "tmp"
        self.config_file = d / "config.json"

    def ensure(self) -> None:
        for p in (self.data_dir, self.thumbnails, self.attachments, self.exports,
                  self.logs, self.backups, self.tmp):
            p.mkdir(parents=True, exist_ok=True)


def read_local_config(paths: Paths) -> dict[str, Any]:
    """Reads config.json from the data folder (optional). Never logged."""
    try:
        if paths.config_file.exists():
            data = json.loads(paths.config_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {}


def get_ai_api_key(paths: Paths, provider: str) -> str | None:
    """Resolution order: REELVAULT_AI_API_KEY, provider-specific env var, config.json."""
    key = os.environ.get("REELVAULT_AI_API_KEY")
    if key:
        return key.strip()
    env_names = {"anthropic": "ANTHROPIC_API_KEY"}
    name = env_names.get(provider)
    if name and os.environ.get(name):
        return os.environ[name].strip()
    cfg = read_local_config(paths)
    for k in ("ai_api_key", f"{provider}_api_key"):
        v = cfg.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None
