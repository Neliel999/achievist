"""
Tests for the same-origin image proxy (GET /api/img, app/imgproxy.py).

No database needed: ASGI transport harness copied from test_api_smoke.py.
Upstream HTTP is faked by monkeypatching imgproxy._make_client to return a
client on httpx.MockTransport; the disk cache is pointed at tmp_path by
monkeypatching config.IMG_PROXY_CACHE_DIR (imgproxy reads config at call
time, so this works without reloading modules).
"""

import json
import time

import httpx
import pytest

from app import config, imgproxy
from app.main import app


ALLOWED = "https://cdn2.steamgriddb.com/grid/example.png"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "IMG_PROXY_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "IMG_PROXY_EXTRA_HOSTS", [])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def mock_upstream(monkeypatch, handler):
    """Point imgproxy at a MockTransport; returns a list recording requests."""
    calls = []

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    def _make_client(timeout):
        return httpx.AsyncClient(transport=httpx.MockTransport(_handler))

    monkeypatch.setattr(imgproxy, "_make_client", _make_client)
    return calls


def ok_image(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"\x89PNG-fake", headers={"Content-Type": "image/png"})


# --- host_allowed unit tests -------------------------------------------------

def test_host_allowed_exact_and_subdomain():
    assert imgproxy.host_allowed("https://cdn2.steamgriddb.com/x.png")
    assert imgproxy.host_allowed("https://avatars.steamstatic.com/abc.jpg")
    assert imgproxy.host_allowed("http://media.steampowered.com/steamcommunity/public/images/apps/1/a.jpg")


def test_host_allowed_normalizes_case_and_trailing_dot():
    assert imgproxy.host_allowed("https://CDN2.SteamGridDB.com./x.png")


def test_host_allowed_rejects_unknown_host_and_lookalikes():
    assert not imgproxy.host_allowed("https://example.com/x.png")
    assert not imgproxy.host_allowed("https://evil-steamstatic.com/x.png")
    assert not imgproxy.host_allowed("https://steamstatic.com.evil.com/x.png")


def test_host_allowed_rejects_non_http_scheme_userinfo_and_ports():
    assert not imgproxy.host_allowed("file:///etc/passwd")
    assert not imgproxy.host_allowed("ftp://cdn2.steamgriddb.com/x.png")
    assert not imgproxy.host_allowed("https://user:pass@cdn2.steamgriddb.com/x.png")
    assert not imgproxy.host_allowed("https://cdn2.steamgriddb.com:8080/x.png")
    assert not imgproxy.host_allowed("https:///x.png")


def test_host_allowed_extra_hosts_from_config(monkeypatch):
    monkeypatch.setattr(config, "IMG_PROXY_EXTRA_HOSTS", ["nextcloud.example.com"])
    assert imgproxy.host_allowed("https://nextcloud.example.com/s/share/x.png")
    assert imgproxy.host_allowed("https://files.nextcloud.example.com/x.png")
    assert not imgproxy.host_allowed("https://nextcloud.example.com.evil.com/x.png")


# --- endpoint behavior --------------------------------------------------------

async def test_allowed_host_proxied_with_cache_headers(client, monkeypatch, tmp_path):
    calls = mock_upstream(monkeypatch, ok_image)
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG-fake"
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert len(calls) == 1
    # body + metadata landed in the disk cache
    assert len(list(tmp_path.glob("*.img"))) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


async def test_disallowed_host_400_and_never_fetched(client, monkeypatch):
    calls = mock_upstream(monkeypatch, ok_image)
    resp = await client.get("/api/img", params={"url": "https://example.com/x.png"})
    assert resp.status_code == 400
    assert calls == []


async def test_non_http_scheme_400(client, monkeypatch):
    mock_upstream(monkeypatch, ok_image)
    resp = await client.get("/api/img", params={"url": "file:///etc/passwd"})
    assert resp.status_code == 400


async def test_missing_url_param_422(client):
    resp = await client.get("/api/img")
    assert resp.status_code == 422


async def test_upstream_500_without_cache_502(client, monkeypatch):
    mock_upstream(monkeypatch, lambda r: httpx.Response(500))
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 502


async def test_upstream_error_serves_stale_cache(client, monkeypatch, tmp_path):
    # seed a stale (older than TTL) cache entry
    monkeypatch.setattr(config, "IMG_PROXY_TTL_SECONDS", 60)
    imgproxy._cache_write(str(tmp_path), ALLOWED, b"stale-bytes", "image/png")
    _, meta_path = imgproxy._cache_paths(str(tmp_path), ALLOWED)
    meta = json.loads(open(meta_path).read())
    meta["fetched_at"] = time.time() - 3600
    with open(meta_path, "w") as f:
        json.dump(meta, f)

    calls = mock_upstream(monkeypatch, lambda r: httpx.Response(500))
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 200
    assert resp.content == b"stale-bytes"
    assert len(calls) == 1  # stale entry was revalidated, not silently served


async def test_fresh_cache_hit_does_not_touch_upstream(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "IMG_PROXY_TTL_SECONDS", 3600)
    imgproxy._cache_write(str(tmp_path), ALLOWED, b"cached-bytes", "image/webp")
    calls = mock_upstream(monkeypatch, lambda r: httpx.Response(500))
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 200
    assert resp.content == b"cached-bytes"
    assert resp.headers["content-type"] == "image/webp"
    assert calls == []


async def test_redirect_to_allowlisted_host_followed(client, monkeypatch):
    target = "https://cdn2.steamgriddb.com/grid/other.png"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL(ALLOWED):
            return httpx.Response(302, headers={"Location": target})
        return ok_image(request)

    mock_upstream(monkeypatch, handler)
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG-fake"


async def test_redirect_to_disallowed_host_fails(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://example.com/evil.png"})

    calls = mock_upstream(monkeypatch, handler)
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 502
    assert len(calls) == 1  # the redirect target was never fetched


async def test_network_error_without_cache_502(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    mock_upstream(monkeypatch, handler)
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 502


async def test_cache_eviction_respects_size_cap(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "IMG_PROXY_MAX_MB", 0)  # cap of 0 bytes: evict everything
    mock_upstream(monkeypatch, ok_image)
    resp = await client.get("/api/img", params={"url": ALLOWED})
    assert resp.status_code == 200  # response still served; cache evicted after write
    assert list(tmp_path.glob("*.img")) == []
    assert list(tmp_path.glob("*.json")) == []
