"""
Same-origin image proxy backend (issue #15: proxy and cache remote images).

The frontend stores raw third-party image URLs (icon_url, sgdb_cover_url,
igdb_cover_url, achievement icons, avatars), so on clients that cannot reach
those CDN hosts directly (e.g. a phone on a VPN exit node) nothing renders.
GET /api/img?url=... fetches the image server-side instead, behind a host
allowlist so the endpoint cannot be abused as an open proxy, and caches the
body on disk with a TTL so previously-synced games keep rendering even when
an upstream host is unreachable (stale-if-error).

Config lives in app/config.py (IMG_PROXY_*); read at call time so tests can
monkeypatch it. _make_client is the seam tests use to inject MockTransport.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from urllib.parse import urljoin, urlsplit

import httpx

from app import config

log = logging.getLogger(__name__)

# Image hosts the app actually stores in DB URL fields (found by grepping
# app/ for URL bases). Keep in sync with KNOWN_HOSTS in
# frontend/src/lib/imgUrl.ts. Matching is exact host or any subdomain.
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    "cdn2.steamgriddb.com",
    "cdn.steamgriddb.com",
    "steamgriddb.com",
    "media.steampowered.com",
    "steamstatic.com",
    "steamcdn-a.akamaihd.net",
    "m.exophase.com",
    "images.igdb.com",
    "retroachievements.org",
    "image-ssl.xboxlive.com",
    "thumbnails.roblox.com",
    "render.guildwars2.com",
    "wgcdn.co",
    "wargaming.net",
    "m.np.playstation.com",
)

_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def host_allowed(url: str) -> bool:
    """True only for http(s) URLs on an allowlisted host (exact or subdomain).

    Rejects non-http schemes, userinfo, explicit non-standard ports, and
    empty hosts — everything that could turn /api/img into an open proxy or
    an SSRF vector.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    if parts.username or parts.password:
        return False
    if port not in (None, 80, 443):
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return False
    entries = DEFAULT_ALLOWED_HOSTS + tuple(config.IMG_PROXY_EXTRA_HOSTS)
    return any(host == e or host.endswith("." + e) for e in entries)


def _cache_paths(cache_dir: str, url: str) -> tuple[str, str]:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, key + ".img"), os.path.join(cache_dir, key + ".json")


def _cache_read(cache_dir: str, url: str) -> tuple[bytes, str, float] | None:
    """Return (body, content_type, fetched_at) for a cached entry, else None."""
    img_path, meta_path = _cache_paths(cache_dir, url)
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        with open(img_path, "rb") as f:
            body = f.read()
        return body, str(meta["content_type"]), float(meta["fetched_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _cache_write(cache_dir: str, url: str, body: bytes, content_type: str) -> None:
    img_path, meta_path = _cache_paths(cache_dir, url)
    os.makedirs(cache_dir, exist_ok=True)
    tmp_path = img_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(body)
    os.replace(tmp_path, img_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"url": url, "content_type": content_type, "fetched_at": time.time()}, f)
    _evict_if_needed(cache_dir)


def _evict_if_needed(cache_dir: str) -> None:
    """Delete oldest-mtime cache entries (body + sidecar) until under the cap."""
    max_bytes = config.IMG_PROXY_MAX_MB * 1024 * 1024
    try:
        names = [n for n in os.listdir(cache_dir) if n.endswith((".img", ".json"))]
        files = []
        for n in names:
            p = os.path.join(cache_dir, n)
            files.append((p, os.path.getmtime(p), os.path.getsize(p)))
    except OSError:
        return
    total = sum(size for _, _, size in files)
    files.sort(key=lambda t: t[1])
    for path, _, size in files:
        if total <= max_bytes:
            break
        try:
            os.remove(path)
        except OSError:
            continue
        total -= size
        sidecar = path[:-4] + ".json" if path.endswith(".img") else path[:-5] + ".img"
        try:
            os.remove(sidecar)
        except OSError:
            pass


def _make_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout)


async def fetch_image(url: str) -> tuple[bytes, str] | None:
    """Fetch `url` upstream (allowlist-checked) with disk cache.

    Returns (body, content_type), or None if upstream failed and there is no
    cached copy. A fresh cache entry is served without touching upstream; a
    stale one is revalidated but still served if upstream fails.
    """
    if not host_allowed(url):
        return None
    cache_dir = config.IMG_PROXY_CACHE_DIR
    ttl = config.IMG_PROXY_TTL_SECONDS
    cached = await asyncio.to_thread(_cache_read, cache_dir, url)
    if cached is not None and time.time() - cached[2] <= ttl:
        return cached[0], cached[1]

    def stale() -> tuple[bytes, str] | None:
        return (cached[0], cached[1]) if cached is not None else None

    try:
        async with _make_client(config.IMG_PROXY_TIMEOUT_SECONDS) as client:
            current = url
            for _ in range(_MAX_REDIRECTS + 1):
                resp = await client.get(current, follow_redirects=False)
                if resp.status_code in _REDIRECT_STATUSES:
                    location = resp.headers.get("location")
                    if not location:
                        return stale()
                    current = urljoin(current, location)
                    if not host_allowed(current):
                        log.warning("imgproxy: redirect to non-allowlisted host: %s", current)
                        return stale()
                    continue
                if resp.status_code != 200:
                    log.warning("imgproxy: upstream %s for %s", resp.status_code, url)
                    return stale()
                body = resp.content
                content_type = resp.headers.get("content-type") or "application/octet-stream"
                await asyncio.to_thread(_cache_write, cache_dir, url, body, content_type)
                return body, content_type
            log.warning("imgproxy: too many redirects for %s", url)
            return stale()
    except httpx.HTTPError as e:
        log.warning("imgproxy: fetch failed for %s: %s", url, e)
        return stale()
