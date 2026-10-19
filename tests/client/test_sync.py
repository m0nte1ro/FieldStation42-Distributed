import json
import os
import sys
from unittest.mock import MagicMock

import httpx
import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from client.playback import sync  # noqa: E402
from client.playback.sync import ClientSync, reload_requested, refresh_requested  # noqa: E402

SERVER = "http://homelab:4242"


class FakeServer:
    def __init__(self):
        self.version = "v1"
        self.files = {
            "confs/main_config.json": json.dumps({"time_format": "%H:%M", "start_channel": 1}).encode(),
            "confs/toons.json": b'{"station_conf": {"network_name": "Toons"}}',
            "catalog/toons/logos/a.png": b"png",
        }
        self.rundown = {"server_time": "2026-10-16T20:00:00", "stations": {"Toons": []}, "meta": {}, "version": "v1"}
        self.requests = []
        self.down = 0  # number of upcoming requests that fail to connect
        self.extra_manifest = []

    def manifest(self):
        entries = [{"path": p, "size": len(b), "mtime": 1000.0} for p, b in sorted(self.files.items())]
        return entries + self.extra_manifest

    def handle(self, request):
        self.requests.append((request.url.path, dict(request.url.params)))
        if self.down:
            self.down -= 1
            raise httpx.ConnectError("unreachable", request=request)
        match request.url.path:
            case "/client/version":
                return httpx.Response(200, json={"version": self.version, "server_time": "2026-10-16T20:00:00"})
            case "/client/files":
                return httpx.Response(200, json=self.manifest())
            case "/client/file":
                path = request.url.params["path"]
                if path not in self.files:
                    return httpx.Response(404)
                return httpx.Response(200, content=self.files[path])
            case "/client/rundown":
                return httpx.Response(200, json=self.rundown)
        return httpx.Response(404)

    def file_requests(self):
        return [params["path"] for path, params in self.requests if path == "/client/file"]


@pytest.fixture
def server():
    reload_requested.clear()
    refresh_requested.clear()
    yield FakeServer()
    reload_requested.clear()
    refresh_requested.clear()


def _client(server, root, main_config=None):
    config = {"server_url": SERVER, "media": {"method": "http"}, "main_config": main_config or {}}
    client = httpx.Client(base_url=SERVER, transport=httpx.MockTransport(server.handle))
    return ClientSync(config, root=str(root), client=client)


def _read_json(root, path):
    with open(os.path.join(root, path)) as f:
        return json.load(f)


def test_initial_sync_writes_files_rundown_and_merged_main_config(server, tmp_path):
    _client(server, tmp_path, {"start_channel": 3}).initial_sync(retry_seconds=0)
    assert _read_json(tmp_path, "confs/main_config.json") == {"time_format": "%H:%M", "start_channel": 3}
    assert (tmp_path / "confs/toons.json").read_bytes() == server.files["confs/toons.json"]
    assert (tmp_path / "catalog/toons/logos/a.png").read_bytes() == b"png"
    assert _read_json(tmp_path, "runtime/rundown.json")["stations"] == {"Toons": []}


def test_unchanged_files_are_not_downloaded_again(server, tmp_path):
    client = _client(server, tmp_path)
    client.sync_files()
    server.requests.clear()
    client.sync_files()
    assert server.file_requests() == []


def test_changed_file_is_downloaded_again(server, tmp_path):
    client = _client(server, tmp_path)
    client.sync_files()
    server.files["confs/toons.json"] = b'{"station_conf": {"network_name": "Toons", "channel_number": 4}}'
    server.requests.clear()
    client.sync_files()
    assert server.file_requests() == ["confs/toons.json"]


def test_stale_station_conf_is_removed(server, tmp_path):
    (tmp_path / "confs").mkdir()
    (tmp_path / "confs/old.json").write_text("{}")
    _client(server, tmp_path).sync_files()
    assert not (tmp_path / "confs/old.json").exists()
    assert (tmp_path / "confs/main_config.json").exists()


def test_absolute_and_dotdot_manifest_paths_are_skipped(server, tmp_path):
    server.extra_manifest = [{"path": "/etc/evil.json", "size": 1, "mtime": 1.0},
                             {"path": "../evil.json", "size": 1, "mtime": 1.0},
                             {"path": "catalog/../../evil.png", "size": 1, "mtime": 1.0}]
    _client(server, tmp_path).sync_files()
    assert not any(p in server.file_requests() for p in ("/etc/evil.json", "../evil.json", "catalog/../../evil.png"))
    assert not (tmp_path.parent / "evil.json").exists()


def test_poll_without_changes_does_nothing(server, tmp_path):
    client = _client(server, tmp_path)
    client.initial_sync(retry_seconds=0)
    assert client.poll_once() is False
    assert not reload_requested.is_set()


def test_poll_after_version_change_resyncs_and_requests_reload(server, tmp_path):
    client = _client(server, tmp_path)
    client.initial_sync(retry_seconds=0)
    server.version = "v2"
    server.rundown["stations"] = {"Toons": [], "News": []}
    assert client.poll_once() is True
    assert reload_requested.is_set()
    assert set(_read_json(tmp_path, "runtime/rundown.json")["stations"]) == {"Toons", "News"}


def test_poll_refreshes_the_rundown_when_it_is_old(server, tmp_path):
    client = _client(server, tmp_path)
    client.initial_sync(retry_seconds=0)
    server.requests.clear()
    assert client.poll_once(rundown_every=0) is True
    assert [p for p, _ in server.requests] == ["/client/version", "/client/rundown"]


def test_poll_with_server_down_returns_false_and_keeps_files(server, tmp_path):
    client = _client(server, tmp_path)
    client.initial_sync(retry_seconds=0)
    server.down = 10
    assert client.poll_once() is False
    assert _read_json(tmp_path, "runtime/rundown.json")["stations"] == {"Toons": []}


def test_refresh_requested_forces_a_resync(server, tmp_path):
    client = _client(server, tmp_path)
    client.initial_sync(retry_seconds=0)
    refresh_requested.set()
    server.requests.clear()
    assert client.poll_once() is True
    assert "/client/rundown" in [p for p, _ in server.requests]
    assert not refresh_requested.is_set()


def test_initial_sync_with_cache_returns_even_if_server_is_down(server, tmp_path):
    _client(server, tmp_path).initial_sync(retry_seconds=0)
    server.down = 10
    _client(server, tmp_path).initial_sync(retry_seconds=0)
    assert server.down == 9


def test_initial_sync_without_cache_retries_until_server_answers(server, tmp_path):
    server.down = 2
    _client(server, tmp_path).initial_sync(retry_seconds=0)
    assert (tmp_path / "runtime/rundown.json").exists()


def test_paths_are_constants_relative_to_root():
    assert sync.MANIFEST_STATE == "runtime/client_manifest.json"
    assert sync.SERVER_MAIN_CONFIG == "runtime/main_config.server.json"


def test_poll_survives_an_unexpected_server_reply(server, tmp_path):
    client = _client(server, tmp_path)
    client.initial_sync(retry_seconds=0)
    original = server.handle

    def odd(request):
        if request.url.path == "/client/version":
            return httpx.Response(200, json={"version": "v9"})  # no server_time
        return original(request)

    client.client = httpx.Client(base_url=SERVER, transport=httpx.MockTransport(odd))
    assert client.poll_once() is False
