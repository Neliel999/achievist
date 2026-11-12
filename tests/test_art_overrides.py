"""
Tests for POST /api/art-set (per-game cover/portrait/icon URL overrides with
reset) and for _sgdb_art_for returning SGDB's vertical grids and icons, which
feed the art picker.

DB tests use the shared db_conn fixture (skipped without a test DB, same as
the rest of the integration suite); the SGDB fetch test uses
httpx.MockTransport like test_sgdb.py.
"""

from datetime import datetime, timezone

import httpx
import pytest

from app import auth, db
from app.main import _sgdb_art_for, app
from tests.conftest import requires_db

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@requires_db
async def _seed(db_conn, client) -> tuple[int, int]:
    user = await db.create_user(db_conn, "parent", auth.hash_password("parentpassword1"), is_admin=True)
    account_id = await db.upsert_account(db_conn, user["id"], "steam", "111", {})
    game_id = await db.upsert_platform_game(db_conn, "steam", "42", "Art Test", "https://cdn/steam-icon.png", 10)
    await db.upsert_user_game(db_conn, account_id, game_id, 0, 1, 10)
    await db_conn.commit()
    await client.post("/api/auth/login", json={"username": "parent", "password": "parentpassword1"})
    return game_id, account_id


@requires_db
async def test_art_set_portrait_icon_cover_roundtrip_and_reset(db_conn, client):
    game_id, _ = await _seed(db_conn, client)

    for field, column in (("portrait", "portrait_cover_url"), ("icon", "icon_url_override"), ("cover", "sgdb_cover_url")):
        r = await client.post("/api/art-set", params={"platform_game_id": game_id, "field": field, "url": "https://cdn/custom.png"})
        assert r.status_code == 200, (field, r.text)
        row = await db._fetchrow(db_conn, f"SELECT {column} AS v FROM platform_games WHERE id = %s", game_id)
        assert row["v"] == "https://cdn/custom.png"

        r = await client.post("/api/art-set", params={"platform_game_id": game_id, "field": field, "url": ""})
        assert r.status_code == 200, (field, r.text)
        row = await db._fetchrow(db_conn, f"SELECT {column} AS v FROM platform_games WHERE id = %s", game_id)
        # cover keeps the historic '' reset marker; portrait/icon store NULL
        assert row["v"] == ("" if field == "cover" else None)


@requires_db
async def test_art_set_rejects_unknown_field(db_conn, client):
    game_id, _ = await _seed(db_conn, client)
    r = await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "wallpaper", "url": "https://cdn/x.png"})
    assert r.status_code == 400


@requires_db
async def test_games_list_reads_overrides_through_coalesce(db_conn, client):
    game_id, _ = await _seed(db_conn, client)
    await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "icon", "url": "https://cdn/icon-override.png"})
    await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "portrait", "url": "https://cdn/portrait.png"})

    resp = await client.get("/api/games")
    assert resp.status_code == 200
    game = next(g for g in resp.json()["games"] if g["platform_game_id"] == game_id)
    assert game["icon_url"] == "https://cdn/icon-override.png"
    assert game["igdb_cover_url"] == "https://cdn/portrait.png"

    # reset -> falls back to the synced icon and (no IGDB art) null portrait
    await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "icon", "url": ""})
    await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "portrait", "url": ""})
    resp = await client.get("/api/games")
    game = next(g for g in resp.json()["games"] if g["platform_game_id"] == game_id)
    assert game["icon_url"] == "https://cdn/steam-icon.png"
    assert game["igdb_cover_url"] is None


@requires_db
async def test_art_set_rejects_non_http_url(db_conn, client):
    game_id, _ = await _seed(db_conn, client)
    for bad in ("javascript:alert(1)", "ftp://cdn/x.png", "not a url"):
        r = await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "icon", "url": bad})
        assert r.status_code == 400, (bad, r.text)
    row = await db._fetchrow(db_conn, "SELECT icon_url_override AS v FROM platform_games WHERE id = %s", game_id)
    assert row["v"] is None


@requires_db
async def test_art_set_unknown_game_returns_404(db_conn, client):
    await _seed(db_conn, client)
    r = await client.post("/api/art-set", params={"platform_game_id": 999999, "field": "icon", "url": "https://cdn/x.png"})
    assert r.status_code == 404


@requires_db
async def test_activity_feed_reads_icon_override_through_coalesce(db_conn, client):
    game_id, account_id = await _seed(db_conn, client)
    ach_id = await db.upsert_achievement(
        db_conn, game_id, "ach-1", "First", "desc", "https://cdn/ach.png", 10, 5.0
    )
    await db.upsert_user_achievement(db_conn, account_id, ach_id, True, datetime.now(timezone.utc))
    await db_conn.commit()

    await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "icon", "url": "https://cdn/icon-override.png"})
    resp = await client.get("/api/activity")
    assert resp.status_code == 200
    entry = next(e for e in resp.json()["feed"] if e["platform_game_id"] == game_id)
    # no cover/IGDB art, so the feed's cover_url falls through to the icon override
    assert entry["cover_url"] == "https://cdn/icon-override.png"

    await client.post("/api/art-set", params={"platform_game_id": game_id, "field": "icon", "url": ""})
    resp = await client.get("/api/activity")
    entry = next(e for e in resp.json()["feed"] if e["platform_game_id"] == game_id)
    assert entry["cover_url"] == "https://cdn/steam-icon.png"



async def test_sgdb_art_for_returns_verticals_and_icons():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/heroes/game/" in path:
            return httpx.Response(200, json={"data": [{"url": "https://cdn/hero.png"}]})
        if "/icons/game/" in path:
            return httpx.Response(200, json={"data": [{"url": "https://cdn/icon.png"}]})
        if "/grids/game/" in path:
            if request.url.params.get("dimensions") == "600x900":
                return httpx.Response(200, json={"data": [{"url": "https://cdn/vertical.png"}]})
            return httpx.Response(200, json={"data": [{"url": "https://cdn/grid.png"}]})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    art = await _sgdb_art_for(client, {"Authorization": "Bearer k"}, "https://www.steamgriddb.com/api/v2", 7)
    assert art["heroes"] == ["https://cdn/hero.png"]
    assert art["grids"] == ["https://cdn/grid.png", "https://cdn/grid.png"]  # 460x215 + 920x430 passes
    assert art["verticals"] == ["https://cdn/vertical.png"]
    assert art["icons"] == ["https://cdn/icon.png"]
