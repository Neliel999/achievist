"""
Tests for the PSN console tag (platform_games.psn_console): GET /api/games
carries it per game and filters on ?console= (exact match on the stored
comma-joined tag), and GET /api/psn/consoles lists the user's distinct tags.
"""

import httpx
import pytest

from app import auth, db
from app.main import app
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login_with_psn_games(db_conn, client) -> None:
    user = await db.create_user(db_conn, "parent", auth.hash_password("parentpassword1"), is_admin=True)
    account_id = await db.upsert_account(db_conn, user["id"], "psn", "111", {})
    ps5 = await db.upsert_platform_game(db_conn, "psn", "NPWR00001_00", "PS5 Game", None, 10, psn_console="PS5")
    ps4 = await db.upsert_platform_game(db_conn, "psn", "NPWR00002_00", "PS4 Game", None, 10, psn_console="PS4")
    cross = await db.upsert_platform_game(db_conn, "psn", "NPWR00003_00", "Cross Game", None, 10, psn_console="PS3,PSVITA")
    for pg_id in (ps5, ps4, cross):
        await db.upsert_user_game(db_conn, account_id, pg_id, 0, 1, 10)
    await db_conn.commit()

    await client.post("/api/auth/login", json={"username": "parent", "password": "parentpassword1"})


async def test_games_response_includes_psn_console(db_conn, client):
    await _login_with_psn_games(db_conn, client)

    resp = await client.get("/api/games", params={"platform": "psn"})
    assert resp.status_code == 200
    by_name = {g["name"]: g["psn_console"] for g in resp.json()["games"]}
    assert by_name == {"PS5 Game": "PS5", "PS4 Game": "PS4", "Cross Game": "PS3,PSVITA"}


async def test_games_console_filter_matches_exact_tag(db_conn, client):
    await _login_with_psn_games(db_conn, client)

    resp = await client.get("/api/games", params={"platform": "psn", "console": "PS5"})
    assert resp.status_code == 200
    assert [g["name"] for g in resp.json()["games"]] == ["PS5 Game"]

    # A single-console filter does not match multi-console rows; the
    # multi-console tag is only reachable via its own option.
    resp = await client.get("/api/games", params={"platform": "psn", "console": "PSVITA"})
    assert resp.status_code == 200
    assert [g["name"] for g in resp.json()["games"]] == []

    resp = await client.get("/api/games", params={"platform": "psn", "console": "PS3,PSVITA"})
    assert [g["name"] for g in resp.json()["games"]] == ["Cross Game"]


async def test_psn_consoles_lists_distinct_tags(db_conn, client):
    await _login_with_psn_games(db_conn, client)

    resp = await client.get("/api/psn/consoles")
    assert resp.status_code == 200
    assert resp.json()["consoles"] == ["PS3,PSVITA", "PS4", "PS5"]
