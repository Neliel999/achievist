"""
Tests for app/platforms/gog.py — direct GOG sync (no Exophase middleman):
per-user OAuth tokens via app/gog_auth.py, owned library from
embed.gog.com/user/data/games, per-game achievements from
gameplay.gog.com/clients/{clientId}/users/{userId}/achievements, with the
per-game client id resolved from gogdb.org build data and cached in
platform_games.gog_client_id.

All GOG HTTP is mocked at the module-function level (gog_module.fetch_* /
gog_auth.refresh); stub tokens only — no real endpoints or credentials.
"""

import time
from datetime import datetime, timezone

import pytest

from app import config, db
from app import gog_auth
from app.platforms import gog as gog_module
from app.platforms.gog import GOGPlatform
from tests.conftest import requires_db


# ── Pure auth helpers (no DB) ────────────────────────────────────────────────


def test_extract_code_from_url():
    url = "https://embed.gog.com/on_login_success?origin=client&code=abc123XYZ_-"
    assert gog_auth.extract_code(url) == "abc123XYZ_-"


def test_extract_code_bare():
    assert gog_auth.extract_code("  abc123  ") == "abc123"


def test_extract_code_garbage_raises():
    with pytest.raises(RuntimeError, match="code"):
        gog_auth.extract_code("https://example.com/nope")


def test_authorize_url_uses_galaxy_client_and_fixed_redirect():
    url = gog_auth.authorize_url()
    assert url.startswith("https://auth.gog.com/auth?")
    assert f"client_id={config.GOG_CLIENT_ID}" in url
    assert "redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient" in url
    assert "response_type=code" in url


@requires_db
async def test_missing_refresh_token_raises():
    with pytest.raises(RuntimeError, match="refresh token"):
        await GOGPlatform().sync(
            {"id": 1, "user_id": 1, "external_id": "1", "credentials": {}}, conn=None,
        )


# ── Sync (DB-backed, GOG HTTP mocked) ────────────────────────────────────────


ACH_ITEMS = [
    {"achievement_id": "ach-1", "achievement_key": "k1", "name": "First Catch",
     "description": "d1", "image_url_unlocked": "https://cdn/a.png",
     "image_url_locked": "https://cdn/a-locked.png", "rarity": 70.0,
     "date_unlocked": "2024-01-02T15:04:05+0000", "visible": True},
    {"achievement_id": "ach-2", "achievement_key": "k2", "name": "Collector",
     "description": "d2", "image_url_unlocked": "https://cdn/b.png",
     "image_url_locked": "https://cdn/b-locked.png", "rarity": 30.0,
     "date_unlocked": None, "visible": True},
]


async def _owned(client, token):
    return [1207658924, 999999999]  # second product has no gogdb entry -> skipped


async def _product_info(client, product_id):
    if product_id == 1207658924:
        return {"client_id": "48384666369469807", "title": "DREDGE", "cover": "https://cdn/cover.png"}
    return None


async def _achievements(client, client_id, user_id, token):
    assert client_id == "48384666369469807"
    assert user_id == "goguser1"
    return ACH_ITEMS


async def _make_account(db_conn, creds):
    user = await db.create_user(db_conn, "parent", "x")
    account_id = await db.upsert_account(db_conn, user["id"], "gog", "goguser1", creds, "goguser")
    return {
        "id": account_id,
        "user_id": user["id"],
        "external_id": "goguser1",
        "credentials": creds,
    }


def _patch_gog_http(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0)
    monkeypatch.setattr(gog_module, "fetch_owned_product_ids", _owned)
    monkeypatch.setattr(gog_module, "fetch_product_info", _product_info)
    monkeypatch.setattr(gog_module, "fetch_achievements", _achievements)
    # no real network: no profile stats unless a test overrides these
    async def no_user_data(token):
        return {}
    async def no_stats(client, username):
        return {}
    monkeypatch.setattr(gog_auth, "fetch_user_data", no_user_data)
    monkeypatch.setattr(gog_module, "fetch_profile_game_stats", no_stats)


@requires_db
async def test_sync_upserts_games_and_achievements(monkeypatch, db_conn):
    _patch_gog_http(monkeypatch)
    creds = {
        "refresh_token": "rt",
        "access_token": "at",
        "token_expires_at": int(time.time()) + 3600,  # valid -> no refresh call
    }
    account = await _make_account(db_conn, creds)

    await GOGPlatform().sync(account, db_conn)
    await db_conn.commit()

    pg = await db.get_platform_game_by_key(db_conn, "gog", "1207658924")
    assert pg is not None
    assert pg["name"] == "DREDGE"
    assert pg["icon_url"] == "https://cdn/cover.png"
    assert pg["total_achievements"] == 2
    assert pg["gog_client_id"] == "48384666369469807"  # cached for next sync
    # the DLC-ish product without gogdb data must not appear
    assert await db.get_platform_game_by_key(db_conn, "gog", "999999999") is None

    linked_id = account["id"]
    row = await db._fetchrow(
        db_conn,
        "SELECT ug.earned_achievements, ug.total_achievements, ug.last_played_at "
        "FROM user_games ug JOIN platform_games pg ON pg.id = ug.platform_game_id "
        "WHERE ug.linked_account_id = %s AND pg.platform_app_id = %s",
        linked_id, "1207658924",
    )
    assert row["earned_achievements"] == 1
    assert row["total_achievements"] == 2
    assert row["last_played_at"] is not None

    rows = await db._fetch(
        db_conn,
        "SELECT a.platform_ach_id, a.name, a.icon_url, a.rarity_pct, ua.unlocked, ua.unlocked_at "
        "FROM user_achievements ua JOIN achievements a ON a.id = ua.achievement_id "
        "WHERE ua.linked_account_id = %s ORDER BY a.platform_ach_id",
        linked_id,
    )
    assert [r["platform_ach_id"] for r in rows] == ["ach-1", "ach-2"]
    assert rows[0]["unlocked"] is True
    assert rows[0]["unlocked_at"] is not None
    assert rows[0]["icon_url"] == "https://cdn/a.png"  # unlocked icon when unlocked
    assert float(rows[0]["rarity_pct"]) == 70.0
    assert rows[1]["unlocked"] is False
    assert rows[1]["unlocked_at"] is None
    assert rows[1]["icon_url"] == "https://cdn/b-locked.png"  # locked icon when locked


@requires_db
async def test_second_sync_uses_cached_client_id(monkeypatch, db_conn):
    _patch_gog_http(monkeypatch)
    creds = {"refresh_token": "rt", "access_token": "at", "token_expires_at": int(time.time()) + 3600}
    account = await _make_account(db_conn, creds)
    await GOGPlatform().sync(account, db_conn)
    await db_conn.commit()

    async def boom(client, product_id):
        if product_id == 1207658924:
            raise AssertionError("gogdb must not be refetched when gog_client_id is cached")
        return None  # products without achievements have no row, so they are re-probed (by design)

    monkeypatch.setattr(gog_module, "fetch_product_info", boom)
    await GOGPlatform().sync(account, db_conn)  # second run: client id from DB cache
    await db_conn.commit()
    pg = await db.get_platform_game_by_key(db_conn, "gog", "1207658924")
    assert pg is not None and pg["gog_client_id"] == "48384666369469807"
    row = await db._fetchrow(
        db_conn,
        "SELECT ug.earned_achievements, ug.total_achievements FROM user_games ug "
        "JOIN platform_games pg ON pg.id = ug.platform_game_id "
        "WHERE ug.linked_account_id = %s AND pg.platform_app_id = %s",
        account["id"], "1207658924",
    )
    assert row["earned_achievements"] == 1 and row["total_achievements"] == 2


@requires_db
async def test_refresh_token_rotation_persisted(monkeypatch, db_conn):
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0)
    async def no_user_data(token):
        return {}
    monkeypatch.setattr(gog_auth, "fetch_user_data", no_user_data)

    async def fake_refresh(refresh_token):
        assert refresh_token == "rt-old"
        return {"access_token": "at-new", "refresh_token": "rt-new", "expires_in": 3600, "user_id": "goguser1"}

    async def no_games(client, token):
        assert token == "at-new"
        return []

    monkeypatch.setattr(gog_auth, "refresh", fake_refresh)
    monkeypatch.setattr(gog_module, "fetch_owned_product_ids", no_games)

    account = await _make_account(db_conn, {"refresh_token": "rt-old"})
    await GOGPlatform().sync(account, db_conn)
    await db_conn.commit()

    row = await db.get_account(db_conn, account["id"], account["user_id"])
    assert row["credentials"]["refresh_token"] == "rt-new"
    assert row["credentials"]["access_token"] == "at-new"


@requires_db
async def test_legacy_exophase_rows_repaired(db_conn):
    user = await db.create_user(db_conn, "parent", "x")
    linked_id = await db.upsert_linked_account(db_conn, user["id"], "gog", "goguser1")
    old_pg = await db.upsert_platform_game(db_conn, "gog", "dredge-gog", "DREDGE", None, 3)
    new_pg = await db.upsert_platform_game(db_conn, "gog", "1207658924", "DREDGE", None, 2)
    await db.upsert_user_game(db_conn, linked_id, old_pg, 0, 1, 3, None)
    await db.upsert_user_game(db_conn, linked_id, new_pg, 0, 2, 2, None)

    await db.repair_legacy_gog_exophase_rows(db_conn, linked_id)
    await db_conn.commit()

    assert await db.get_platform_game_by_key(db_conn, "gog", "dredge-gog") is None
    assert await db.get_platform_game_by_key(db_conn, "gog", "1207658924") is not None
    remaining = await db._fetch(
        db_conn,
        "SELECT platform_game_id FROM user_games WHERE linked_account_id = %s",
        linked_id,
    )
    assert [r["platform_game_id"] for r in remaining] == [new_pg]


# ── Profile gameplay stats (public profile HAL endpoint) ────────────────────


class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, pages):
        self._pages = pages  # list of _FakeResp, indexed by page-1
        self.requests = []

    async def get(self, url, params=None):
        self.requests.append((url, params))
        return self._pages[(params or {}).get("page", 1) - 1]


def _stats_item(product_id, playtime, last_session):
    return {
        "game": {"id": product_id, "title": "T", "url": "/en/game/t",
                 "achievementSupport": True, "image": "https://cdn/t.png"},
        "stats": {"48384666369469807": {"playtime": playtime, "lastSession": last_session}},
    }


async def test_fetch_profile_game_stats_paginates_and_maps(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0)
    pages = [
        _FakeResp(200, {"page": 1, "pages": 2, "total": 4, "_embedded": {"items": [
            _stats_item("111", 15, "2026-11-02T22:59:23+00:00"),
            _stats_item("222", 8863, "2022-07-26T06:38:11+00:00"),
        ]}}),
        _FakeResp(200, {"page": 2, "pages": 2, "total": 4, "_embedded": {"items": [
            _stats_item("333", 0, None),
            {"game": {"id": "444"}, "stats": {"48384666369469807": {"playtime": None}}},  # no playtime -> skipped
            {"game": {}, "stats": {}},  # no product id -> skipped
        ]}}),
    ]
    client = _FakeClient(pages)
    stats = await gog_module.fetch_profile_game_stats(client, "someuser")
    assert client.requests[0][0] == "https://www.gog.com/u/someuser/games/stats"
    assert [p["page"] for _, p in client.requests] == [1, 2]
    assert set(stats) == {"111", "222", "333"}
    assert stats["222"]["playtime_minutes"] == 8863
    assert stats["222"]["last_played"] == datetime(2022, 7, 26, 6, 38, 11, tzinfo=timezone.utc)
    assert stats["111"]["playtime_minutes"] == 15
    assert stats["333"]["playtime_minutes"] == 0 and stats["333"]["last_played"] is None


async def test_fetch_profile_game_stats_hidden_profile_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0)
    client = _FakeClient([_FakeResp(403)])
    assert await gog_module.fetch_profile_game_stats(client, "privateuser") == {}
    assert len(client.requests) == 1  # stops after the first page


async def test_fetch_profile_game_stats_single_page_not_refetched(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0)
    pages = [_FakeResp(200, {"page": 1, "pages": 1, "_embedded": {"items": [_stats_item("1", 5, None)]}})]
    client = _FakeClient(pages)
    stats = await gog_module.fetch_profile_game_stats(client, "u")
    assert set(stats) == {"1"} and len(client.requests) == 1


@requires_db
async def test_sync_writes_profile_playtime(monkeypatch, db_conn):
    _patch_gog_http(monkeypatch)

    async def user_data(token):
        return {"userId": "goguser1", "username": "goguser"}

    async def stats(client, username):
        assert username == "goguser"
        return {"1207658924": {"playtime_minutes": 8863,
                               "last_played": datetime(2022, 7, 26, 6, 38, 11, tzinfo=timezone.utc)}}

    monkeypatch.setattr(gog_auth, "fetch_user_data", user_data)
    monkeypatch.setattr(gog_module, "fetch_profile_game_stats", stats)
    creds = {"refresh_token": "rt", "access_token": "at", "token_expires_at": int(time.time()) + 3600}
    account = await _make_account(db_conn, creds)

    await GOGPlatform().sync(account, db_conn)
    await db_conn.commit()

    row = await db._fetchrow(
        db_conn,
        "SELECT ug.playtime_minutes, ug.last_played_at FROM user_games ug "
        "JOIN platform_games pg ON pg.id = ug.platform_game_id "
        "WHERE ug.linked_account_id = %s AND pg.platform_app_id = %s",
        account["id"], "1207658924",
    )
    assert row["playtime_minutes"] == 8863
    assert row["last_played_at"] == datetime(2022, 7, 26, 6, 38, 11, tzinfo=timezone.utc)


@requires_db
async def test_sync_without_profile_stats_keeps_playtime_zero(monkeypatch, db_conn):
    _patch_gog_http(monkeypatch)  # fetch_user_data -> {}, fetch_profile_game_stats -> {}
    creds = {"refresh_token": "rt", "access_token": "at", "token_expires_at": int(time.time()) + 3600}
    account = await _make_account(db_conn, creds)

    await GOGPlatform().sync(account, db_conn)
    await db_conn.commit()

    row = await db._fetchrow(
        db_conn,
        "SELECT ug.playtime_minutes FROM user_games ug "
        "JOIN platform_games pg ON pg.id = ug.platform_game_id "
        "WHERE ug.linked_account_id = %s AND pg.platform_app_id = %s",
        account["id"], "1207658924",
    )
    assert row["playtime_minutes"] == 0
