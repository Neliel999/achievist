"""
Tests for app/platforms/psn.py. A PSN sync stitches together several
endpoints — earned status, trophy details and play time each come from a
different one — so these stub them all with httpx.MockTransport and run
without real network access or a PSN sign-in.
"""

from datetime import datetime, timezone

import httpx
import pytest

from app import db
from app.platforms import psn
from app.platforms.psn import PSNPlatform
from tests.conftest import requires_db

ACCOUNT = "4242"
GAME = "NPWR00001_00"

TROPHY_TITLE = {
    "npCommunicationId": GAME,
    "trophyTitleName": "Cool Game",
    "trophyTitleIconUrl": "https://icon/game.png",
    "trophyTitlePlatform": "PS4",
    "definedTrophies": {"bronze": 1, "silver": 1, "gold": 0, "platinum": 0},
    "earnedTrophies": {"bronze": 1, "silver": 0, "gold": 0, "platinum": 0},
}

# The per-user endpoint: earned status only, no name/description/icon.
EARNED = [
    {"trophyId": 0, "trophyType": "bronze", "earned": True,
     "earnedDateTime": "2026-10-01T12:00:00Z", "trophyEarnedRate": "55.5"},
    {"trophyId": 1, "trophyType": "silver", "earned": False, "trophyEarnedRate": "10.1"},
]

# The game's own trophy list.
DETAILS = [
    {"trophyId": 0, "trophyType": "bronze", "trophyName": "First Steps",
     "trophyDetail": "Finish the tutorial", "trophyIconUrl": "https://icon/0.png"},
    {"trophyId": 1, "trophyType": "silver", "trophyName": "Seasoned",
     "trophyDetail": "Beat the game on Hard", "trophyIconUrl": "https://icon/1.png"},
]

# Two regional releases of GAME, a collection spanning two trophy sets, and a
# title PSN doesn't recognise (which fails any lookup batch it's part of).
PLAYED = [
    {"titleId": "CUSA00001_00", "playDuration": "PT12H30M15S", "lastPlayedDateTime": "2026-10-20T18:00:00Z"},
    {"titleId": "CUSA00002_00", "playDuration": "PT1H5M", "lastPlayedDateTime": "2026-10-25T21:15:30.12Z"},
    {"titleId": "CUSA00003_00", "playDuration": "PT40H", "lastPlayedDateTime": "2026-09-01T10:00:00Z"},
    {"titleId": "CUSA00004_00", "playDuration": "PT2H", "lastPlayedDateTime": "2026-08-01T10:00:00Z"},
]
TROPHY_SETS = {
    "CUSA00001_00": [GAME],
    "CUSA00002_00": [GAME],
    "CUSA00003_00": ["NPWR00010_00", "NPWR00011_00"],
}


def _handler(game_list_status: int = 200, profile_status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/search/v1/universalSearch":
            return httpx.Response(200, json={"domainResponses": [{"results": [
                {"socialMetadata": {"onlineId": "someone_else", "accountId": "999"}},
                {"socialMetadata": {"onlineId": "Someone", "accountId": ACCOUNT}},
            ]}]})
        if path == "/userProfile/v1/users/someone/profile2":
            if profile_status != 200:
                return httpx.Response(profile_status, text="<HTML>Access Denied</HTML>")
            return httpx.Response(200, json={"profile": {"accountId": ACCOUNT}})
        if path == f"/api/trophy/v1/users/{ACCOUNT}/trophyTitles":
            return httpx.Response(200, json={"trophyTitles": [TROPHY_TITLE], "totalItemCount": 1})
        if path == f"/api/trophy/v1/users/{ACCOUNT}/npCommunicationIds/{GAME}/trophyGroups/all/trophies":
            return httpx.Response(200, json={"trophies": EARNED})
        if path == f"/api/trophy/v1/npCommunicationIds/{GAME}/trophyGroups/all/trophies":
            return httpx.Response(200, json={"trophies": DETAILS})
        if path == f"/api/gamelist/v2/users/{ACCOUNT}/titles":
            if game_list_status != 200:
                return httpx.Response(game_list_status, json={"error": {"message": "Forbidden"}})
            return httpx.Response(200, json={"titles": PLAYED, "totalItemCount": len(PLAYED)})
        if path == f"/api/trophy/v1/users/{ACCOUNT}/titles/trophyTitles":
            ids = request.url.params["npTitleIds"].split(",")
            assert len(ids) <= 5
            if any(i not in TROPHY_SETS for i in ids):
                return httpx.Response(404, json={"error": {"message": "Resource not found"}})
            return httpx.Response(200, json={"titles": [
                {"npTitleId": i, "trophyTitles": [{"npCommunicationId": s} for s in TROPHY_SETS[i]]}
                for i in ids
            ]})
        raise AssertionError(f"unexpected request: {request.url}")
    return handler


@pytest.fixture
def psn_api(monkeypatch):
    """Route the PSN sync to a stub API: call the returned function with a handler."""
    async def fake_token():
        return "token"

    monkeypatch.setattr(psn, "get_access_token", fake_token)
    monkeypatch.setattr(psn.config, "REQUEST_DELAY_SECONDS", 0)
    psn._trophy_sets_by_title.clear()
    real_async_client = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kw: real_async_client(transport=httpx.MockTransport(handler))
        )

    yield install
    psn._trophy_sets_by_title.clear()


async def _sync(conn) -> int:
    user = await db.create_user(conn, "parent", "x")
    await PSNPlatform().sync({"external_id": "someone", "user_id": user["id"]}, conn)
    await conn.commit()
    return await db.upsert_linked_account(conn, user["id"], "psn", "someone")


async def _user_game(conn, linked_id: int) -> dict:
    return await db._fetchrow(
        conn,
        "SELECT ug.playtime_minutes, ug.last_played_at, ug.earned_achievements FROM user_games ug "
        "JOIN platform_games pg ON pg.id = ug.platform_game_id "
        "WHERE ug.linked_account_id = %s AND pg.platform_app_id = %s",
        linked_id, GAME,
    )


async def _trophies(conn) -> list[dict]:
    return await db._fetch(
        conn,
        "SELECT a.name, a.description, a.icon_url FROM achievements a "
        "JOIN platform_games pg ON pg.id = a.platform_game_id "
        "WHERE pg.platform_app_id = %s ORDER BY a.platform_ach_id",
        GAME,
    )


def test_play_minutes_parses_psn_durations():
    assert psn._play_minutes("PT228H56M33S") == 228 * 60 + 56
    assert psn._play_minutes("PT45M") == 45
    assert psn._play_minutes("PT3H") == 180
    assert psn._play_minutes("PT0S") == 0
    assert psn._play_minutes(None) == 0
    assert psn._play_minutes("garbage") == 0


@requires_db
async def test_sync_stores_trophy_details_and_play_time(psn_api, db_conn):
    psn_api(_handler())

    linked_id = await _sync(db_conn)

    assert [(t["name"], t["description"], t["icon_url"]) for t in await _trophies(db_conn)] == [
        ("First Steps", "Finish the tutorial", "https://icon/0.png"),
        ("Seasoned", "Beat the game on Hard", "https://icon/1.png"),
    ]
    unlocks = await db._fetch(
        db_conn,
        "SELECT ua.unlocked, ua.unlocked_at FROM user_achievements ua "
        "JOIN achievements a ON a.id = ua.achievement_id "
        "WHERE ua.linked_account_id = %s ORDER BY a.platform_ach_id",
        linked_id,
    )
    assert [(u["unlocked"], u["unlocked_at"]) for u in unlocks] == [
        (True, datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)),
        (False, None),
    ]
    game = await _user_game(db_conn, linked_id)
    # Both regional releases count; the collection and the unrecognised title don't.
    assert game["playtime_minutes"] == (12 * 60 + 30) + 65
    assert game["last_played_at"] == datetime(2026, 10, 25, 21, 15, 30, 120000, tzinfo=timezone.utc)


@requires_db
async def test_sync_repairs_trophies_stored_without_details(psn_api, db_conn):
    """Placeholder-named trophies get fixed even when nothing new was earned since."""
    psn_api(_handler())
    user = await db.create_user(db_conn, "parent", "x")
    linked_id = await db.upsert_linked_account(db_conn, user["id"], "psn", "someone")
    pg_id = await db.upsert_platform_game(db_conn, "psn", GAME, "Cool Game", None, 2)
    await db.upsert_user_game(db_conn, linked_id, pg_id, 0, 1, 2)
    for trophy_id in ("0", "1"):
        await db.upsert_achievement(db_conn, pg_id, trophy_id, f"Trophy {trophy_id}", None, None, 15, None)

    await PSNPlatform().sync({"external_id": "someone", "user_id": user["id"]}, db_conn)

    assert [t["name"] for t in await _trophies(db_conn)] == ["First Steps", "Seasoned"]


@requires_db
async def test_sync_without_game_list_still_imports_trophies(psn_api, db_conn):
    psn_api(_handler(game_list_status=403))

    linked_id = await _sync(db_conn)

    game = await _user_game(db_conn, linked_id)
    assert game["playtime_minutes"] == 0
    assert game["earned_achievements"] == 1
    assert [t["name"] for t in await _trophies(db_conn)] == ["First Steps", "Seasoned"]


@requires_db
async def test_sync_finds_account_by_search_when_profile_lookup_is_refused(psn_api, db_conn):
    psn_api(_handler(profile_status=403))

    linked_id = await _sync(db_conn)

    assert [t["name"] for t in await _trophies(db_conn)] == ["First Steps", "Seasoned"]
    assert (await _user_game(db_conn, linked_id))["earned_achievements"] == 1
