"""URL extraction and normalization shared by the sync API and dedup logic.

The Android client has an equivalent implementation (core/UrlNormalizer.kt).
Both must agree on the normalized form so dedup is stable across devices.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRACKING_PARAMS = {
    "igsh", "igshid", "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "fbclid", "gclid", "si", "feature", "ref", "ref_src", "s", "t",
}
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am"}
_INSTAGRAM_PATH_RE = re.compile(r"^/(?:[A-Za-z0-9_.]+/)?(reel|reels|p|tv)/([A-Za-z0-9_-]+)/?")
_ALLOWED_SCHEMES = {"http", "https"}


def extract_url(text: str | None) -> str | None:
    """Returns the first http(s) URL inside arbitrary shared text, or None."""
    if not text:
        return None
    m = _URL_RE.search(text)
    if not m:
        return None
    url = m.group(0).rstrip(".,;:)!?")
    return url


def is_safe_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in _ALLOWED_SCHEMES and bool(parts.netloc) and len(url) <= 2048


def normalize_url(url: str) -> str:
    """Canonical form used for dedup. Never used to replace the original URL."""
    url = url.strip()
    parts = urlsplit(url)
    scheme = "https" if parts.scheme.lower() in ("http", "https") else parts.scheme.lower()
    host = parts.hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path or "/"
    query_items = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if k.lower() not in _TRACKING_PARAMS]
    if host in {"instagram.com", "m.instagram.com", "instagr.am"}:
        m = _INSTAGRAM_PATH_RE.match(path)
        if m:
            kind = "reel" if m.group(1) in ("reel", "reels") else m.group(1)
            return f"https://instagram.com/{kind}/{m.group(2)}"
    if host in {"youtube.com", "m.youtube.com"}:
        q = dict(query_items)
        if path == "/watch" and "v" in q:
            return f"https://youtube.com/watch?v={q['v']}"
        m = re.match(r"^/shorts/([A-Za-z0-9_-]+)", path)
        if m:
            return f"https://youtube.com/shorts/{m.group(1)}"
    if host == "youtu.be":
        return f"https://youtube.com/watch?v={path.strip('/')}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = urlencode(sorted(query_items)) if query_items else ""
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    return urlunsplit((scheme, host + port, path, query, ""))


def instagram_shortcode(url: str) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in {"instagram.com", "m.instagram.com", "instagr.am"}:
        return None
    m = _INSTAGRAM_PATH_RE.match(parts.path or "")
    return m.group(2) if m else None
