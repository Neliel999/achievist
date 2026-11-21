import logging
import time

import httpx

from app import config

log = logging.getLogger(__name__)

_token: str | None = None
_token_expires: float = 0.0

_AUTH_URL = "https://id.twitch.tv/oauth2/token"
_BASE = "https://api.igdb.com/v4"


async def _get_token() -> str | None:
    global _token, _token_expires
    if _token and time.time() < _token_expires - 60:
        return _token
    if not config.IGDB_CLIENT_ID or not config.IGDB_CLIENT_SECRET:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(_AUTH_URL, params={
            "client_id": config.IGDB_CLIENT_ID,
            "client_secret": config.IGDB_CLIENT_SECRET,
            "grant_type": "client_credentials",
        })
    if resp.status_code != 200:
        log.warning("IGDB auth failed: %s", resp.text)
        return None
    data = resp.json()
    _token = data["access_token"]
    _token_expires = time.time() + data.get("expires_in", 3600)
    return _token


import re


_PLATFORM_IDS: dict[str, list[int]] = {
    "xbox": [12, 49, 169],   # Xbox 360, Xbox One, Xbox Series X/S
    "steam": [6],            # PC (Windows)
    "retroachievements": [], # many old platforms — don't filter
}

_CLEAN_RE = re.compile(r'[®™©]')
# Hiragana, katakana, CJK unified ideographs, halfwidth katakana — when the
# synced title contains these, the primary-name search usually misses because
# IGDB/SGDB index romanized names, so we also try IGDB alternative_names.
_NON_LATIN_RE = re.compile(r'[぀-ヿ一-鿿ｦ-ﾟ]')


async def search_cover(name: str, platform: str = "") -> tuple[int, str, str] | None:
    """Return (igdb_id, cover_url, canonical_name) for the best match, or None.

    Tries the primary name search first; if it yields no covered result and the
    name is non-Latin, also queries alternative_names, which carry
    original-language titles, so e.g. a Japanese synced title can still match
    the game's romanized entry. canonical_name is IGDB's primary (usually
    English/romanized) name, reused as the SGDB search term by the caller.
    """
    token = await _get_token()
    if not token:
        return None
    headers = {
        "Client-ID": config.IGDB_CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }
    clean_name = _CLEAN_RE.sub('', name).strip()
    platform_ids = _PLATFORM_IDS.get(platform, [])
    plat_filter = ""
    if platform_ids:
        plat_filter = " | ".join(f"platforms = ({pid})" for pid in platform_ids)

    bodies = []
    primary = f'search "{clean_name}"; fields id,name,cover.url; limit 5;'
    if plat_filter:
        primary = f'search "{clean_name}"; fields id,name,cover.url; where ({plat_filter}); limit 5;'
    bodies.append(primary)
    if _NON_LATIN_RE.search(name):
        alt_where = f'alternative_names.name ~ "*{clean_name}*"'
        if plat_filter:
            alt_where = f"({alt_where}) & ({plat_filter})"
        bodies.append(f'fields id,name,cover.url; where {alt_where}; limit 5;')

    async with httpx.AsyncClient(timeout=15) as client:
        for body in bodies:
            resp = await client.post(f"{_BASE}/games", headers=headers, content=body)
            if resp.status_code != 200:
                log.warning("IGDB search failed for '%s': %s", name, resp.text)
                return None
            for r in resp.json():
                if r.get("cover", {}).get("url"):
                    cover = r["cover"]["url"].replace("//", "https://").replace("t_thumb", "t_cover_big_2x")
                    return r["id"], cover, r["name"]
    return None
