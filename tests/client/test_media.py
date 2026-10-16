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
