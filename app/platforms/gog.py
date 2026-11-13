"""
GOG platform sync — direct against GOG's API, no Exophase middleman.

Auth is per-user OAuth via app/gog_auth.py (stored on the linked account as a
refresh token; external_id is the numeric GOG user id from the token response).

Pipeline per sync:
1. GET https://embed.gog.com/user/data/games        → owned product ids
2. per product: resolve the per-game Galaxy client id from gogdb.org build data
   (product.json → latest listed build → builds/<id>.json → clientId), cached
   in platform_games.gog_client_id. The per-game client *secret* in the same
   build data is only needed for writes; reads use the user token.
3. GET https://gameplay.gog.com/clients/{clientId}/users/{userId}/achievements
   → full achievement catalog incl. locked items, unlock dates, icons, rarity.

Unofficial endpoints throughout — every external call degrades gracefully:
non-200s are logged and skip that product/lookup instead of failing the run.
Respects config.REQUEST_DELAY_SECONDS between external calls.

Reference: https://github.com/timendum/gog-achievements-gui (src/bun/gog/)
"""

import asyncio
import logging
import re
from datetime import datetime

import httpx

from app import config, db, gog_auth
from app.platforms.base import Platform

log = logging.getLogger(__name__)

_EMBED = "https://embed.gog.com"
_GAMEPLAY = "https://gameplay.gog.com"
_GOGDB = "https://www.gogdb.org"

_GAMEPLAY_HEADERS = {"Accept": "application/json", "X-Gog-Lc": "en"}

_TS_SUFFIX_RE = re.compile(r"([+-]\d{2})(\d{2})$")


def _parse_unlock_time(value) -> datetime | None:
    """GOG date_unlocked, e.g. '2024-01-02T15:04:05+0000' or ISO with Z."""
    if not value:
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = _TS_SUFFIX_RE.sub(r"\1:\2", s)  # '+0000' → '+00:00'
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _to_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def fetch_owned_product_ids(client: httpx.AsyncClient, access_token: str) -> list[int]:
    """Owned GOG product ids (includes DLC ids; achievement-less products are skipped later)."""
    resp = await client.get(
        f"{_EMBED}/user/data/games",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"GOG library request failed ({resp.status_code})")
    owned = resp.json().get("owned") or []
    return [int(p) for p in owned]


async def fetch_product_info(client: httpx.AsyncClient, product_id: int) -> dict | None:
    """
    gogdb.org product.json → {"client_id", "title", "cover"} from the latest
    listed build's build data. Returns None on any failure (404 for non-game
    products, missing builds, network errors) — callers skip the product.
    """
    resp = await client.get(f"{_GOGDB}/data/products/{product_id}/product.json")
    if resp.status_code != 200:
        return None
    product = resp.json()
    builds = [b for b in product.get("builds") or [] if b.get("date_published") and b.get("listed")]
    if not builds:
        return None
    builds.sort(key=lambda b: b["date_published"], reverse=True)
    build_id = builds[0]["id"]
    await asyncio.sleep(config.REQUEST_DELAY_SECONDS)
    build_resp = await client.get(f"{_GOGDB}/data/products/{product_id}/builds/{build_id}.json")
    if build_resp.status_code != 200:
        return None
    client_id = build_resp.json().get("clientId")
    if not client_id:
        return None
    cover = product.get("image_boxart") or product.get("image_background") or ""
    if cover.startswith("//"):
        cover = "https:" + cover
    return {
        "client_id": str(client_id),
        "title": product.get("title") or str(product_id),
        "cover": cover or None,
    }


async def fetch_achievements(
    client: httpx.AsyncClient, client_id: str, user_id: str, access_token: str,
) -> list[dict]:
    """Full achievement catalog for one game (locked + unlocked). [] on non-200."""
    resp = await client.get(
        f"{_GAMEPLAY}/clients/{client_id}/users/{user_id}/achievements",
        headers={**_GAMEPLAY_HEADERS, "Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code != 200:
        log.warning("GOG achievements request failed for client %s (%s)", client_id, resp.status_code)
        return []
    return resp.json().get("items") or []


class GOGPlatform(Platform):
    KEY = "gog"
    LABEL = "GOG"
    # Credentials come from the OAuth "Sign in with GOG" flow (app/gog_auth.py)
    # and live in the account's credentials JSON — there are no form fields.
    # external_id is the numeric GOG user id from the token response.
    AUTH_TYPE = "oauth"
    CONNECT_FIELDS = []
    SECRET_CRED_KEYS = {"refresh_token", "access_token"}

    async def sync(self, account: dict, conn) -> None:
        credentials = account.get("credentials") or {}
        access_token, new_credentials = await gog_auth.get_access_token(credentials)
        if new_credentials != credentials and account.get("id"):
            # Persist the (possibly rotated) refresh token / fresh access token.
            await db.set_account_credentials(conn, account["id"], new_credentials)
        user_id = str(account["external_id"])

        linked_id = await db.upsert_linked_account(conn, account["user_id"], "gog", user_id)
        # One account per platform per user: drop the stale fixed-id "gog" row
        # left by the old Exophase-based connect (cascades its user_games).
        await db.delete_other_accounts_for_platform(conn, account["user_id"], "gog", user_id)
        await db.repair_legacy_gog_exophase_rows(conn, linked_id)

        delay = config.REQUEST_DELAY_SECONDS
        async with httpx.AsyncClient(timeout=30) as client:
            owned = await fetch_owned_product_ids(client, access_token)
            log.info("gog: %d owned products", len(owned))

            for product_id in owned:
                app_id = str(product_id)
                self._inc("games_seen")

                row = await db.get_platform_game_by_key(conn, "gog", app_id)
                if row and row["gog_client_id"]:
                    client_id, title, cover = row["gog_client_id"], row["name"], row["icon_url"]
                else:
                    await asyncio.sleep(delay)
                    info = await fetch_product_info(client, product_id)
                    if not info:
                        continue  # not a game / no usable build — skip
                    client_id, title, cover = info["client_id"], info["title"], info["cover"]

                await asyncio.sleep(delay)
                items = await fetch_achievements(client, client_id, user_id, access_token)
                total = len(items)
                if not total:
                    continue  # DLCs/extras without achievements

                pg_id = await db.upsert_platform_game(conn, "gog", app_id, title, cover, total)
                await db.set_gog_client_id(conn, pg_id, client_id)

                unlock_times = [t for t in (_parse_unlock_time(it.get("date_unlocked")) for it in items) if t]
                earned = len(unlock_times)
                last_played = max(unlock_times) if unlock_times else None
                await db.upsert_user_game(conn, linked_id, pg_id, 0, earned, total, last_played)

                for it in items:
                    ach_id = str(it.get("achievement_id") or it.get("achievement_key") or "")
                    if not ach_id:
                        continue
                    self._inc("achievements_synced")
                    unlocked = bool(it.get("date_unlocked"))
                    icon = it.get("image_url_unlocked") if unlocked else it.get("image_url_locked")
                    db_ach_id = await db.upsert_achievement(
                        conn, pg_id, ach_id,
                        it.get("name") or ach_id, it.get("description"),
                        icon, None, _to_float(it.get("rarity")),
                    )
                    await db.upsert_user_achievement(
                        conn, linked_id, db_ach_id, unlocked,
                        _parse_unlock_time(it.get("date_unlocked")),
                    )
