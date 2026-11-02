import asyncio
import logging
import re
from datetime import datetime

import httpx

from app import config, db
from app.platforms.base import Platform
from app.psn_auth import get_access_token, auth_headers

log = logging.getLogger(__name__)

_BASE = "https://m.np.playstation.com/api"

# Profile lookups stay on the legacy host: the m.np "internal" profile2 route
# is refused with HTTP 403 by PSN's edge, while this one resolves Online IDs.
_PROFILE_BASE = "https://us-prof.np.community.playstation.net"

# Rough point weighting per trophy tier (PSN has no built-in points system).
_TROPHY_POINTS = {"bronze": 15, "silver": 30, "gold": 90, "platinum": 300}

# PSN only records play time for PS4 and PS5 games.
_PLAYED_CATEGORIES = "ps4_game,ps5_native_game"

# titles/trophyTitles rejects a request naming more than 5 npTitleIds.
_TITLE_ID_BATCH = 5

# npTitleId (CUSA…/PPSA…) → the trophy set(s) it belongs to. Kept across
# syncs: a title's trophy sets never change, and looking them up costs a
# request per five titles.
_trophy_sets_by_title: dict[str, list[str]] = {}

# PSN play time, e.g. "PT228H56M33S" — hours are its largest unit.
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _play_minutes(duration: str | None) -> int:
    """Whole minutes in a PSN playDuration; 0 if it's missing or unparseable."""
    m = _DURATION_RE.match(duration or "")
    if not m:
        return 0
    hours, minutes, _seconds = (int(g or 0) for g in m.groups())
    return hours * 60 + minutes


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _lookup_trophy_sets(client: httpx.AsyncClient, headers: dict, account_id: str,
                              title_ids: list[str], delay: float) -> dict[str, list[str]] | None:
    """{npTitleId: [npCommunicationId, …]} for up to 5 titles, or None if PSN refused the lookup."""
    await asyncio.sleep(delay)
    resp = await client.get(
        f"{_BASE}/trophy/v1/users/{account_id}/titles/trophyTitles",
        headers=headers,
        params={"npTitleIds": ",".join(title_ids)},
    )
    if resp.status_code != 200:
        return None
    found = {}
    for entry in resp.json().get("titles") or []:
        sets = [s["npCommunicationId"] for s in entry.get("trophyTitles") or [] if s.get("npCommunicationId")]
        if entry.get("npTitleId") and sets:
            found[entry["npTitleId"]] = sets
    return found


async def _fetch_playtime(client: httpx.AsyncClient, headers: dict, account_id: str,
                          delay: float) -> dict[str, tuple[int, datetime | None]]:
    """
    {npCommunicationId: (minutes played, last played)} for the account's PS4/PS5
    games. PSN keeps play time in its game list, which is keyed by npTitleId
    rather than by trophy set, so each played title is mapped to its trophy set
    first. Trophies still sync without it, e.g. when the player's privacy
    settings hide their game list.
    """
    played: list[dict] = []
    offset = 0
    while True:
        await asyncio.sleep(delay)
        resp = await client.get(
            f"{_BASE}/gamelist/v2/users/{account_id}/titles",
            headers=headers,
            params={"categories": _PLAYED_CATEGORIES, "limit": 200, "offset": offset},
        )
        if resp.status_code != 200:
            log.warning("PSN game list unavailable (HTTP %s); syncing without play time", resp.status_code)
            return {}
        data = resp.json()
        page = data.get("titles") or []
        played.extend(page)
        offset += len(page)
        if not page or offset >= (data.get("totalItemCount") or len(played)):
            break

    unresolved = list(dict.fromkeys(
        t["titleId"] for t in played
        if t.get("titleId") and t["titleId"] not in _trophy_sets_by_title
    ))
    for i in range(0, len(unresolved), _TITLE_ID_BATCH):
        batch = unresolved[i:i + _TITLE_ID_BATCH]
        found = await _lookup_trophy_sets(client, headers, account_id, batch, delay)
        if found is None and len(batch) > 1:
            # One id PSN doesn't recognise fails the whole request, so retry
            # the batch a title at a time.
            found = {}
            for title_id in batch:
                found.update(await _lookup_trophy_sets(client, headers, account_id, [title_id], delay) or {})
        _trophy_sets_by_title.update(found or {})

    playtime: dict[str, tuple[int, datetime | None]] = {}
    for t in played:
        sets = _trophy_sets_by_title.get(t.get("titleId")) or []
        # A title spanning several trophy sets (a collection) can't have its
        # play time split between them, so it isn't credited to any.
        if len(sets) != 1:
            continue
        # Several titles can share one trophy set (e.g. regional releases).
        minutes, last_played = playtime.get(sets[0], (0, None))
        played_at = _parse_datetime(t.get("lastPlayedDateTime"))
        if played_at and (last_played is None or played_at > last_played):
            last_played = played_at
        playtime[sets[0]] = (minutes + _play_minutes(t.get("playDuration")), last_played)
    return playtime


async def _resolve_account_id(client: httpx.AsyncClient, headers: dict, online_id: str) -> str:
    """
    The numeric accountId for an Online ID. Uses the profile endpoint; if PSN
    refuses it (HTTP 403), falls back to a universal search for the exact
    Online ID.
    """
    profile = await client.get(
        f"{_PROFILE_BASE}/userProfile/v1/users/{online_id}/profile2",
        headers=headers,
        params={"fields": "accountId"},
    )
    if profile.status_code == 404:
        raise RuntimeError(f"No PlayStation profile found for '{online_id}'.")
    if profile.status_code != 403:
        profile.raise_for_status()
        body = profile.json()
        account_id = (body.get("profile") or body).get("accountId")
        if not account_id:
            raise RuntimeError(f"Could not resolve accountId for '{online_id}'.")
        return account_id

    log.warning("PSN profile lookup refused (HTTP 403); trying universal search")
    resp = await client.post(
        f"{_BASE}/search/v1/universalSearch",
        headers=headers,
        json={"searchTerm": online_id, "domainRequests": [{"domain": "SocialAllAccounts"}]},
    )
    resp.raise_for_status()
    for domain in resp.json().get("domainResponses") or []:
        for result in domain.get("results") or []:
            meta = result.get("socialMetadata") or {}
            # Search is fuzzy; only an exact Online ID match is the account.
            if (meta.get("onlineId") or "").lower() == online_id.lower() and meta.get("accountId"):
                return str(meta["accountId"])
    raise RuntimeError(f"No PlayStation profile found for '{online_id}'.")


class PSNPlatform(Platform):
    KEY = "psn"
    LABEL = "PlayStation"
    CONNECT_FIELDS = [
        {"name": "external_id", "label": "PSN Online ID", "type": "text", "required": True,
         "help": "Your PSN username. Trophy privacy must be set to 'Anyone' for this to sync."},
    ]

    async def sync(self, account: dict, conn) -> None:
        online_id = account["external_id"]
        delay = config.REQUEST_DELAY_SECONDS

        access_token = await get_access_token()
        headers = auth_headers(access_token)

        linked_id = await db.upsert_linked_account(conn, account["user_id"], "psn", online_id)
        earned_cache = await db.get_earned_counts(conn, linked_id)
        # Games stored before trophy details were fetched are re-fetched even
        # when nothing new was earned, or they'd keep their placeholder names.
        missing_details = await db.get_psn_games_missing_trophy_details(conn)

        async with httpx.AsyncClient(timeout=30) as client:
            account_id = await _resolve_account_id(client, headers, online_id)

            titles: list[dict] = []
            offset = 0
            while True:
                await asyncio.sleep(delay)
                resp = await client.get(
                    f"{_BASE}/trophy/v1/users/{account_id}/trophyTitles",
                    headers=headers,
                    params={"limit": 100, "offset": offset},
                )
                if resp.status_code == 403:
                    raise RuntimeError(
                        f"PlayStation profile '{online_id}' has trophies set to private."
                    )
                resp.raise_for_status()
                data = resp.json()
                page = data.get("trophyTitles") or []
                titles.extend(page)
                total_count = (data.get("totalItemCount") or len(titles))
                offset += len(page)
                if not page or offset >= total_count:
                    break

            log.info("PSN: %d titles for %s", len(titles), online_id)

            playtime = await _fetch_playtime(client, headers, account_id, delay)

            for title in titles:
                np_comm_id = title.get("npCommunicationId")
                name = title.get("trophyTitleName") or np_comm_id
                icon = title.get("trophyTitleIconUrl")
                defined = title.get("definedTrophies") or {}
                earned = title.get("earnedTrophies") or {}
                total = sum(int(defined.get(t, 0) or 0) for t in _TROPHY_POINTS)
                earned_total = sum(int(earned.get(t, 0) or 0) for t in _TROPHY_POINTS)
                if not np_comm_id or total == 0:
                    continue

                is_ps5 = "PS5" in (title.get("trophyTitlePlatform") or "")
                service_name = "trophy2" if is_ps5 else "trophy"

                self._inc("games_seen")
                minutes, last_played_at = playtime.get(np_comm_id, (0, None))
                pg_id = await db.upsert_platform_game(conn, "psn", np_comm_id, name, icon, total)
                await db.upsert_user_game(conn, linked_id, pg_id, minutes, earned_total, total, last_played_at)

                cached = earned_cache.get(np_comm_id)
                if (cached and cached["earned"] == earned_total and cached["stored"] >= total > 0
                        and np_comm_id not in missing_details):
                    continue

                await asyncio.sleep(delay)
                tr_resp = await client.get(
                    f"{_BASE}/trophy/v1/users/{account_id}/npCommunicationIds/{np_comm_id}/trophyGroups/all/trophies",
                    headers=headers,
                    params={"npServiceName": service_name, "fields": "@default,trophyRare,trophyEarnedRate,trophyType"},
                )
                if tr_resp.status_code != 200:
                    log.warning("PSN trophies fetch failed for %s: %s", name, tr_resp.status_code)
                    continue

                # The per-user endpoint above only reports earned status; each
                # trophy's name, description and icon come from the game's own
                # trophy list.
                await asyncio.sleep(delay)
                details_resp = await client.get(
                    f"{_BASE}/trophy/v1/npCommunicationIds/{np_comm_id}/trophyGroups/all/trophies",
                    headers=headers,
                    params={"npServiceName": service_name},
                )
                if details_resp.status_code == 200:
                    details = {d.get("trophyId"): d for d in details_resp.json().get("trophies") or []}
                else:
                    # Earned status is still worth storing; the placeholder
                    # names this leaves get the game re-fetched next sync.
                    log.warning("PSN trophy details fetch failed for %s: %s", name, details_resp.status_code)
                    details = {}

                for t in tr_resp.json().get("trophies") or []:
                    trophy_id = t.get("trophyId")
                    if trophy_id is None:
                        continue
                    self._inc("achievements_synced")
                    detail = details.get(trophy_id) or {}
                    trophy_type = t.get("trophyType") or "bronze"
                    rarity = t.get("trophyEarnedRate")
                    db_ach_id = await db.upsert_achievement(
                        conn,
                        pg_id,
                        str(trophy_id),
                        detail.get("trophyName") or f"Trophy {trophy_id}",
                        detail.get("trophyDetail"),
                        detail.get("trophyIconUrl"),
                        _TROPHY_POINTS.get(trophy_type),
                        float(rarity) if rarity is not None else None,
                    )
                    unlocked = bool(t.get("earned"))
                    unlocked_at = _parse_datetime(t.get("earnedDateTime")) if unlocked else None
                    await db.upsert_user_achievement(conn, linked_id, db_ach_id, unlocked, unlocked_at)
