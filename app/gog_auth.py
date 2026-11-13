"""
GOG authentication: OAuth2 authorization-code flow against GOG's public
"Galaxy client" — the same client_id/client_secret hardcoded in lgogdownloader,
Minigalaxy, Heroic and other open-source GOG clients (stable for 10+ years,
env-overridable via GOG_CLIENT_ID / GOG_CLIENT_SECRET).

GOG offers no device-code flow, and the Galaxy client's redirect_uri is fixed
to https://embed.gog.com/on_login_success?origin=client (verified live: any
other redirect_uri is rejected with redirect_uri_mismatch). A server-side app
therefore cannot receive the redirect itself — the user completes login in a
browser, lands on that GOG page whose URL carries ?code=..., and pastes the
code (or the whole URL) back into achievist. The code is exchanged server-side
at auth.gog.com/token (GET with query params, not a POST body — that is what
GOG expects).

Read-only access (owned library + achievements) needs only this user token;
per-game client secrets are required for writes only, which achievist never
performs.

Reference implementations of this pipeline:
- https://github.com/timendum/gog-achievements-gui (src/bun/gog/)
- lgogdownloader / Minigalaxy / Heroic (auth code exchange + refresh grant)
"""

import logging
import re
import time
from urllib.parse import urlencode

import httpx

from app import config

log = logging.getLogger(__name__)

_AUTH_URL = "https://auth.gog.com/auth"
_TOKEN_URL = "https://auth.gog.com/token"
_USER_DATA_URL = "https://embed.gog.com/userData.json"
# The Galaxy client's only registered redirect target; the code arrives in its
# query string after login and must be sent unchanged in the token exchange.
_REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"

_CODE_RE = re.compile(r"[?&]code=([^&#]+)")
_BARE_CODE_RE = re.compile(r"[A-Za-z0-9_\-.]+")


def authorize_url() -> str:
    """Browser URL that starts the GOG login and ends with ?code=..."""
    params = {
        "client_id": config.GOG_CLIENT_ID,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "layout": "client2",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def extract_code(text: str) -> str:
    """Pull the authorization code out of a pasted redirect URL or bare code."""
    text = (text or "").strip()
    m = _CODE_RE.search(text)
    if m:
        return m.group(1)
    if _BARE_CODE_RE.fullmatch(text):
        return text
    raise RuntimeError(
        "No GOG authorization code found — paste the full URL of the GOG "
        "'on_login_success' page you landed on (it contains ?code=...)."
    )


async def _token_request(params: dict) -> dict:
    """GET auth.gog.com/token with query params (GOG's non-standard but required shape)."""
    params = {**params, "client_id": config.GOG_CLIENT_ID, "client_secret": config.GOG_CLIENT_SECRET}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_TOKEN_URL, params=params)
    if resp.status_code != 200:
        detail = ""
        try:
            body = resp.json()
            detail = body.get("error_description") or body.get("error") or ""
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError(f"GOG token request failed ({resp.status_code}): {detail}")
    data = resp.json()
    if not data.get("access_token") or not data.get("refresh_token"):
        raise RuntimeError("GOG token response missing access_token/refresh_token")
    return data


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    return await _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _REDIRECT_URI,
    })


async def refresh(refresh_token: str) -> dict:
    """
    Refresh-token grant. GOG may return a new refresh_token — callers must
    persist whatever comes back (rotation not guaranteed, but assumed).
    """
    return await _token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "without_new_session": "1",
    })


def creds_from_token_response(data: dict) -> dict:
    """Credential dict to store on the linked account (secrets; masked in API responses)."""
    return {
        "refresh_token": data["refresh_token"],
        "access_token": data["access_token"],
        "token_expires_at": int(time.time()) + int(data.get("expires_in") or 3600),
    }


async def get_access_token(credentials: dict) -> tuple[str, dict]:
    """
    Return (access_token, credentials_to_persist). Uses the cached access token
    while it is valid (60s safety margin), otherwise refreshes. The returned
    dict carries the possibly-rotated refresh token; persist it when it differs
    from the input.
    """
    creds = dict(credentials or {})
    expires_at = int(creds.get("token_expires_at") or 0)
    if creds.get("access_token") and time.time() < expires_at - 60:
        return creds["access_token"], creds
    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("GOG account has no refresh token — reconnect via 'Sign in with GOG'.")
    data = await refresh(refresh_token)
    new_creds = {**creds, **creds_from_token_response(data)}
    return new_creds["access_token"], new_creds


async def fetch_user_data(access_token: str) -> dict:
    """embed.gog.com/userData.json → {userId, username, ...}; {} on any failure."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _USER_DATA_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return {}
        return resp.json()
    except Exception as e:
        log.warning("GOG userData fetch failed: %s", e)
        return {}
