"""Best-effort metadata retrieval behind a provider abstraction.

Providers only use documented, authorized methods:
  * ``ytdlp``  runs ``yt-dlp --dump-single-json`` (no download) when yt-dlp is installed.
  * ``oembed`` calls public oEmbed endpoints (YouTube, Vimeo, TikTok) and, for Instagram,
    the official Graph oEmbed endpoint only when an access token is configured.
No provider logs in, bypasses CAPTCHAs or scrapes HTML behind access controls.
On failure the idea keeps its link and is marked ``unavailable`` so it can be edited by hand or retried.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from ..urlnorm import is_safe_url

log = logging.getLogger("reelvault.metadata")
USER_AGENT = "ReelVault/1.0 (+local workspace; metadata via public endpoints)"
_MIN_INTERVAL_S = 1.5
_last_call: dict[str, float] = {}


@dataclass
class Metadata:
    title: str = ""
    creator: str = ""
    caption: str = ""
    canonical_url: str = ""
    thumbnail_url: str = ""
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.title or self.creator or self.caption or self.thumbnail_url)


class MetadataProvider(Protocol):
    name: str
    def fetch(self, url: str) -> Metadata | None: ...


class MetadataUnavailable(Exception):
    pass


def _rate_limit(host: str) -> None:
    last = _last_call.get(host, 0.0)
    wait = _MIN_INTERVAL_S - (time.monotonic() - last)
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.monotonic()


def http_get_json(url: str, timeout: float = 15.0) -> dict[str, Any]:
    if not is_safe_url(url):
        raise MetadataUnavailable("unsafe URL")
    _rate_limit(urlsplit(url).hostname or "")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https only, validated above
        data = resp.read(2_000_000)
    return json.loads(data.decode("utf-8", errors="replace"))


def download_file(url: str, dest: Path, max_bytes: int = 15_000_000, timeout: float = 20.0) -> Path:
    if not is_safe_url(url):
        raise MetadataUnavailable("unsafe thumbnail URL")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        ctype = (resp.headers.get("Content-Type") or "").lower()
        ext = ".jpg"
        if "png" in ctype:
            ext = ".png"
        elif "webp" in ctype:
            ext = ".webp"
        dest = dest.with_suffix(ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            total = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise MetadataUnavailable("thumbnail too large")
                f.write(chunk)
    return dest


class YtDlpProvider:
    name = "ytdlp"

    def __init__(self, ytdlp_path: str | None):
        self.ytdlp_path = ytdlp_path

    def fetch(self, url: str) -> Metadata | None:
        if not self.ytdlp_path:
            return None
        args = [self.ytdlp_path, "--dump-single-json", "--skip-download", "--no-playlist", "--no-warnings",
                "--socket-timeout", "20", "--", url]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=90,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as e:
            raise MetadataUnavailable(f"yt-dlp could not run: {e}") from e
        if proc.returncode != 0:
            err = (proc.stderr or "").strip().splitlines()
            raise MetadataUnavailable("yt-dlp: " + (err[-1] if err else f"exit code {proc.returncode}")[:300])
        try:
            info = json.loads(proc.stdout)
        except ValueError as e:
            raise MetadataUnavailable("yt-dlp returned invalid JSON") from e
        return Metadata(
            title=(info.get("title") or "")[:300],
            creator=(info.get("uploader") or info.get("channel") or info.get("uploader_id") or "")[:200],
            caption=(info.get("description") or "")[:5000],
            canonical_url=info.get("webpage_url") or "",
            thumbnail_url=info.get("thumbnail") or "",
            provider=self.name,
            raw={k: info.get(k) for k in ("duration", "view_count", "like_count", "upload_date", "extractor", "id")},
        )


class OEmbedProvider:
    name = "oembed"

    def __init__(self, instagram_token: str = ""):
        self.instagram_token = instagram_token

    def endpoint_for(self, url: str) -> str | None:
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        q = urllib.parse.quote(url, safe="")
        if host in ("youtube.com", "m.youtube.com", "youtu.be"):
            return f"https://www.youtube.com/oembed?format=json&url={q}"
        if host in ("vimeo.com",):
            return f"https://vimeo.com/api/oembed.json?url={q}"
        if host in ("tiktok.com", "vm.tiktok.com"):
            return f"https://www.tiktok.com/oembed?url={q}"
        if host in ("instagram.com", "m.instagram.com", "instagr.am"):
            if not self.instagram_token:
                return None
            tok = urllib.parse.quote(self.instagram_token, safe="")
            return f"https://graph.facebook.com/v19.0/instagram_oembed?url={q}&omitscript=true&access_token={tok}"
        return None

    def fetch(self, url: str) -> Metadata | None:
        endpoint = self.endpoint_for(url)
        if not endpoint:
            return None
        try:
            data = http_get_json(endpoint)
        except urllib.error.HTTPError as e:
            raise MetadataUnavailable(f"oEmbed HTTP {e.code}") from e
        except (urllib.error.URLError, ValueError, OSError) as e:
            raise MetadataUnavailable(f"oEmbed failed: {e}") from e
        return Metadata(
            title=(data.get("title") or "")[:300],
            creator=(data.get("author_name") or "")[:200],
            caption="",
            canonical_url=data.get("author_url") and "" or "",
            thumbnail_url=data.get("thumbnail_url") or "",
            provider=self.name,
            raw={k: data.get(k) for k in ("provider_name", "author_url", "width", "height")},
        )


def build_providers(order: list[str], ytdlp_path: str | None, instagram_token: str = "") -> list[Any]:
    available = {"ytdlp": YtDlpProvider(ytdlp_path), "oembed": OEmbedProvider(instagram_token)}
    return [available[n] for n in order if n in available]


def fetch_metadata(url: str, providers: list[Any]) -> tuple[Metadata | None, list[str]]:
    """Tries providers in order. Returns (metadata, errors). metadata is None when every provider failed."""
    errors: list[str] = []
    for p in providers:
        try:
            md = p.fetch(url)
        except MetadataUnavailable as e:
            errors.append(f"{p.name}: {e}")
            continue
        except Exception as e:  # noqa: BLE001
            log.warning("provider %s crashed: %s", p.name, e)
            errors.append(f"{p.name}: {type(e).__name__}")
            continue
        if md is None:
            errors.append(f"{p.name}: not applicable")
            continue
        if md.is_empty():
            errors.append(f"{p.name}: empty result")
            continue
        return md, errors
    return None, errors
