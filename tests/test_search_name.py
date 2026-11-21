"""
Tests for POST /api/games/{id}/search-name — the per-game search-title
override used by SGDB/IGDB enrichment for games whose synced title (e.g.
Japanese) doesn't match their romanized SGDB/IGDB entry — including that
setting it clears cached lookup failures (igdb_id = -1, sgdb_cover_url = '')
while keeping real prior matches.

DB tests use the shared db_conn fixture (skipped without a test DB, same as
the rest of the integration suite), mirroring tests/test_art_overrides.py.
"""

import httpx
import pytest

from app import auth, db
from app.main import app
from tests.conftest import requires_db

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@requires_db
async def _seed(db_conn, client) -> int:
    user = await db.create_user(db_conn, "parent", auth.hash_password("parentpassword1"), is_admin=True)
    account_id = await db.upsert_account(db_conn, user["id"], "steam", "111", {})
    game_id = await db.upsert_platform_game(db_conn, "steam", "42", "ゼルダの伝説", "https://cdn/steam-icon.png", 10)
    await db.upsert_user_game(db_conn, account_id, game_id, 0, 1, 10)
    await db_conn.commit()
    await client.post("/api/auth/login", json={"username": "parent", "password": "parentpassword1"})
    return game_id


@requires_db
async def test_search_name_set_reset_and_game_detail_exposes_it(db_conn, client):
    game_id = await _seed(db_conn, client)

    r = await client.post(f"/api/games/{game_id}/search-name", params={"name": "The Legend of Zelda"})
    assert r.status_code == 200, r.text
    row = await db._fetchrow(db_conn, "SELECT search_name_override AS v FROM platform_games WHERE id = %s", game_id)
    assert row["v"] == "The Legend of Zelda"

    resp = await client.get(f"/api/games/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["search_name_override"] == "The Legend of Zelda"

    r = await client.post(f"/api/games/{game_id}/search-name", params={"name": ""})
    assert r.status_code == 200, r.text
    row = await db._fetchrow(db_conn, "SELECT search_name_override AS v FROM platform_games WHERE id = %s", game_id)
    assert row["v"] is None


@requires_db
async def test_search_name_unknown_game_returns_404(db_conn, client):
    await _seed(db_conn, client)
    r = await client.post("/api/games/999999/search-name", params={"name": "X"})
    assert r.status_code == 404


async def test_search_name_clears_cached_lookup_failures(db_conn, client):
    game_id = await _seed(db_conn, client)
    # igdb_id = -1 is the lookup-failure marker; the FK requires a sentinel row
    await db.upsert_igdb_game(db_conn, -1, "NOT FOUND", "")
    await db_conn.execute(
        "UPDATE platform_games SET igdb_id = -1, sgdb_cover_url = '' WHERE id = %s", (game_id,)
    )
    await db_conn.commit()

    r = await client.post(f"/api/games/{game_id}/search-name", params={"name": "The Legend of Zelda"})
    assert r.status_code == 200, r.text
    row = await db._fetchrow(
        db_conn,
        "SELECT igdb_id, sgdb_cover_url FROM platform_games WHERE id = %s",
        game_id,
    )
    assert row["igdb_id"] is None
    assert row["sgdb_cover_url"] is None


@requires_db
async def test_search_name_keeps_real_prior_match(db_conn, client):
    game_id = await _seed(db_conn, client)
    await db.upsert_igdb_game(db_conn, 5, "The Legend of Zelda", "https://cdn/igdb.png")
    await db_conn.execute(
        "UPDATE platform_games SET igdb_id = 5, sgdb_cover_url = 'https://cdn/sgdb.png' WHERE id = %s",
        (game_id,),
    )
    await db_conn.commit()

    r = await client.post(f"/api/games/{game_id}/search-name", params={"name": "Other Title"})
    assert r.status_code == 200, r.text
    row = await db._fetchrow(
        db_conn,
        "SELECT igdb_id, sgdb_cover_url, search_name_override AS s FROM platform_games WHERE id = %s",
        game_id,
    )
    assert row["igdb_id"] == 5
    assert row["sgdb_cover_url"] == "https://cdn/sgdb.png"
    assert row["s"] == "Other Title"
