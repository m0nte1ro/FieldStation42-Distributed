import gzip
import json
import queue
import sys
from unittest.mock import MagicMock

import httpx
import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from client.input import local_api, proxy  # noqa: E402
from shared.stations.manager import StationManager  # noqa: E402

SERVER_URL = "http://server:4242"
PPV = {"network_name": "Movies", "network_type": "web", "channel_number": 7}


class RawStream(httpx.AsyncByteStream):
    """An unread body, like a real network response (httpx pre-reads bytes passed as content)."""

    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        yield self.data


def reply(status=200, body=b"", headers=None):
    return httpx.Response(status, headers=headers or {}, stream=RawStream(body))


class Upstream:
    def __init__(self, respond=None):
        self.requests = []
        self.respond = respond or (lambda request: reply(200, b'{"ok": true}', {"content-type": "application/json"}))

    def __call__(self, request):
        self.requests.append(request)
        return self.respond(request)


@pytest.fixture
def client_app(monkeypatch):
    def make(respond=None):
        upstream = Upstream(respond)
        monkeypatch.setattr(local_api, "build_proxy_router",
                            lambda url: proxy.build_proxy_router(url, transport=httpx.MockTransport(upstream)))
        return TestClient(local_api.build_app(SERVER_URL)), upstream

    return make


def test_data_routes_are_proxied_with_query_and_status(client_app):
    client, upstream = client_app(lambda r: reply(404, b'{"detail": "nope"}', {"content-type": "application/json"}))
    response = client.get("/schedules/Toons?start=2026-10-16T20:00:00&end=2026-10-16T21:00:00")
    assert response.status_code == 404 and response.json() == {"detail": "nope"}
    assert str(upstream.requests[0].url) == "http://server:4242/schedules/Toons?start=2026-10-16T20:00:00&end=2026-10-16T21:00:00"


def test_encoded_paths_and_queries_reach_the_server_unchanged(client_app):
    client, upstream = client_app()
    client.get("/media/file?path=catalog%2Fa%20b%231.mp3")
    assert upstream.requests[0].url.raw_path == b"/media/file?path=catalog%2Fa%20b%231.mp3"


def test_post_body_is_proxied(client_app):
    client, upstream = client_app()
    client.post("/build/catalog/all", content=b'{"x": 1}', headers={"content-type": "application/json"})
    assert upstream.requests[0].method == "POST" and upstream.requests[0].content == b'{"x": 1}'


def test_static_pages_are_proxied(client_app):
    client, upstream = client_app(lambda r: reply(200, b"<html>", {"content-type": "text/html"}))
    response = client.get("/static/bump/bump.html?title=X")
    assert response.text == "<html>" and response.headers["content-type"] == "text/html"
    assert upstream.requests[0].url.path == "/static/bump/bump.html"


def test_redirect_is_passed_through_not_followed(client_app):
    client, upstream = client_app(lambda r: reply(307, headers={"location": "/static/index.html"}))
    response = client.get("/static", follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "/static/index.html"
    assert len(upstream.requests) == 1


def test_range_request_and_response_pass_through(client_app):
    def respond(request):
        assert request.headers["range"] == "bytes=0-9"
        return reply(206, b"0123456789", {"content-range": "bytes 0-9/100", "accept-ranges": "bytes"})

    client, _ = client_app(respond)
    response = client.get("/media/file?path=a.mp3", headers={"Range": "bytes=0-9"})
    assert response.status_code == 206 and response.content == b"0123456789"
    assert response.headers["content-range"] == "bytes 0-9/100"


def test_compressed_body_passes_through_raw(client_app):
    client, _ = client_app(lambda r: reply(200, gzip.compress(b"hello"), {"content-encoding": "gzip"}))
    response = client.get("/summary")
    assert response.headers["content-encoding"] == "gzip" and response.content == b"hello"


def test_hop_by_hop_headers_are_dropped(client_app):
    client, _ = client_app(lambda r: reply(200, b"ok", {"keep-alive": "timeout=5", "x-custom": "1"}))
    response = client.get("/summary")
    assert "keep-alive" not in response.headers and response.headers["x-custom"] == "1"


def test_unreachable_server_is_502(client_app):
    def respond(request):
        raise httpx.ConnectError("unreachable", request=request)

    client, _ = client_app(respond)
    response = client.get("/summary")
    assert response.status_code == 502 and response.json() == {"detail": "server unreachable"}


def test_player_routes_stay_local(client_app):
    client, upstream = client_app()
    assert client.get("/player/status/queue_connected").json() == {"queue_connected": False}
    assert upstream.requests == []


def test_ppv_play_file_is_local_and_needs_no_file_on_the_client(client_app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    StationManager._StationManager__we_are_all_one = {
        "_initialized": True, "stations": [PPV], "server_conf": {}, "_name_index": {"Movies": PPV},
        "_number_index": {7: PPV},
    }
    try:
        client, upstream = client_app()
        commands = queue.Queue()
        client.app.state.player_command_queue = commands
        response = client.post("/ppv/7/play_file", json={"file_path": "catalog/ppv/m.mp4"})
        assert response.status_code == 200 and upstream.requests == []
        assert commands.get_nowait() == {"command": "play_file", "file_path": "catalog/ppv/m.mp4"}
    finally:
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []
