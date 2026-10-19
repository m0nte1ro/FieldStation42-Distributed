from urllib.parse import parse_qs, urlparse

import pytest

from client.playback.media import media_location

HTTP = {"server_url": "http://homelab:4242", "media": {"method": "http"}, "main_config": {}}


def test_http_location_round_trips_awkward_names():
    path = "catalog/toons/Ep 1 #2 ?&ção.mp4"
    url = media_location(path, HTTP)
    assert url.startswith("http://homelab:4242/client/media?path=")
    assert parse_qs(urlparse(url).query)["path"] == [path]


def test_mount_location_joins_root():
    config = {"server_url": "http://h:4242", "media": {"method": "mount", "root": "/mnt/fs42/"}}
    assert media_location("catalog/a.mp4", config) == "/mnt/fs42/catalog/a.mp4"
    assert media_location("/srv/media/a.mp4", config) == "/mnt/fs42/srv/media/a.mp4"


@pytest.mark.parametrize("path", [
    "https://example.com/live.m3u8",
    ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=X",
])
def test_streams_and_autobumps_are_left_alone(path):
    assert media_location(path, HTTP) == path


def test_files_the_client_has_play_locally(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime/standby.png").write_bytes(b"png")
    assert media_location("runtime/standby.png", HTTP) == "runtime/standby.png"


from client.playback.media import local_page_url  # noqa: E402


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:4242/static/bump/bump.html?title=X",
    "http://localhost:4242/static/diagnostics.html",
])
def test_pages_follow_the_client_port_when_it_differs(url):
    config = dict(HTTP, local_api_port=4243)
    assert local_page_url(url, config, 4242).startswith("http://127.0.0.1:4243/static/")


def test_pages_are_unchanged_on_the_default_port_or_elsewhere():
    assert local_page_url("http://127.0.0.1:4242/static/a.html", HTTP, 4242) == "http://127.0.0.1:4242/static/a.html"
    other = "https://example.com/page"
    assert local_page_url(other, dict(HTTP, local_api_port=4243), 4242) == other
