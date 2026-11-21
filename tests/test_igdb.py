"""
Tests for app/igdb.py's search_cover candidate pipeline: primary name search
first, then — only for non-Latin (e.g. Japanese) names that yield no covered
result — an IGDB alternative_names query, which carries original-language
titles. Returns (igdb_id, cover_url, canonical_name).

Uses httpx.MockTransport (built into httpx, no extra test dependency) to stub
IGDB responses so these run without real network access or credentials.
"""

import httpx
import pytest

from app import config
from app import igdb
from app.igdb import search_cover


def _mock_client(monkeypatch, handler) -> list[httpx.Request]:
    """Route all httpx.AsyncClient calls through MockTransport; return seen requests."""
    seen: list[httpx.Request] = []

    def tracking_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_async_client(transport=httpx.MockTransport(tracking_handler))
    )
    return seen


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(config, "IGDB_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "IGDB_CLIENT_SECRET", "secret")

    async def fake_get_token():
        return "tok"

    monkeypatch.setattr(igdb, "_get_token", fake_get_token)


def _game(gid: int, name: str, cover: str | None = "//images.igdb.com/igdb/image/upload/t_thumb/abc.jpg") -> dict:
    g = {"id": gid, "name": name}
    if cover:
        g["cover"] = {"url": cover}
    return g


class TestSearchCover:
    async def test_none_without_token(self, monkeypatch):
        async def fake_get_token():
            return None

        monkeypatch.setattr(igdb, "_get_token", fake_get_token)
        seen = _mock_client(monkeypatch, lambda r: httpx.Response(200, json=[]))
        assert await search_cover("Some Game") is None
        assert seen == []

    async def test_primary_hit_returns_cover_and_canonical_name(self, monkeypatch, token):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[_game(7, "Some Game")])

        seen = _mock_client(monkeypatch, handler)
        result = await search_cover("Some Game")
        assert result == (7, "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/abc.jpg", "Some Game")
        assert len(seen) == 1
        body = seen[0].content.decode()
        assert body.startswith('search "Some Game";')
        assert "alternative_names" not in body

    async def test_non_latin_name_falls_back_to_alternative_names(self, monkeypatch, token):
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.content.decode()
            if body.startswith('search "'):
                return httpx.Response(200, json=[])
            assert 'alternative_names.name ~ "*ゼルダの伝説*"' in body
            return httpx.Response(200, json=[_game(99, "The Legend of Zelda")])

        seen = _mock_client(monkeypatch, handler)
        result = await search_cover("ゼルダの伝説")
        assert result == (99, "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/abc.jpg", "The Legend of Zelda")
        assert len(seen) == 2

    async def test_latin_name_does_not_query_alternative_names(self, monkeypatch, token):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        seen = _mock_client(monkeypatch, handler)
        assert await search_cover("Nonexistent Game") is None
        assert len(seen) == 1
        assert "alternative_names" not in seen[0].content.decode()

    async def test_platform_filter_in_both_query_shapes(self, monkeypatch, token):
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.content.decode()
            if body.startswith('search "'):
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[_game(5, "Steam JP Game")])

        seen = _mock_client(monkeypatch, handler)
        result = await search_cover("日本語ゲーム", platform="steam")
        assert result is not None
        assert "platforms = (6)" in seen[0].content.decode()
        assert "platforms = (6)" in seen[1].content.decode()
        assert "alternative_names.name" in seen[1].content.decode()

    async def test_non_200_returns_none(self, monkeypatch, token):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        _mock_client(monkeypatch, handler)
        assert await search_cover("Some Game") is None

    async def test_skips_results_without_cover(self, monkeypatch, token):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[_game(1, "No Cover", cover=None), _game(2, "Has Cover")])

        _mock_client(monkeypatch, handler)
        result = await search_cover("Some Game")
        assert result is not None
        assert result[0] == 2
