import datetime
import json
import sys
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from shared.rundown import BlockPlanEntry  # noqa: E402
from fs42.box.media import media_location  # noqa: E402
from fs42.box.rundown import block_to_json  # noqa: E402
from fs42.catalog_entry import CatalogEntry  # noqa: E402
from fs42.liquid_blocks import LiquidBlock  # noqa: E402
from fs42.liquid_manager import LiquidManager  # noqa: E402
from fs42.metadata_io import MetadataIO  # noqa: E402
from shared.stations.manager import StationManager  # noqa: E402

HTTP = {"server_url": "http://homelab:4242", "media": {"method": "http"}, "main_config": {}}
START = datetime.datetime(2026, 10, 16, 20, 0)


def _station(name, channel, content_dir):
    return {
        "network_name": name, "channel_number": channel, "network_type": "standard",
        "schedule_increment": 30, "content_dir": content_dir,
        "day_templates": {"daily": {"0": {"tags": "anything"}}},
        "monday": "daily", "tuesday": "daily", "wednesday": "daily", "thursday": "daily",
        "friday": "daily", "saturday": "daily", "sunday": "daily",
    }


def _reset_singletons():
    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []
    LiquidManager._LiquidManager__we_are_all_one = {}


@pytest.fixture
def box_dir(tmp_path, monkeypatch):
    _reset_singletons()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "confs").mkdir()
    (tmp_path / "runtime").mkdir()
    (tmp_path / "confs/toons.json").write_text(json.dumps({"station_conf": _station("Toons", 3, "catalog/missing")}))
    yield tmp_path
    _reset_singletons()


def _make_box(path):
    (path / "box.json").write_text(json.dumps({"server_url": "http://homelab:4242"}))


def test_http_location_round_trips_awkward_names():
    path = "catalog/toons/Ep 1 #2 ?&ção.mp4"
    url = media_location(path, HTTP)
    assert url.startswith("http://homelab:4242/box/media?path=")
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


def test_box_mode_keeps_station_with_missing_media(box_dir):
    _make_box(box_dir)
    assert [s["network_name"] for s in StationManager().stations] == ["Toons"]


def test_without_box_json_station_with_missing_media_is_skipped(box_dir):
    assert StationManager().stations == []


def _write_rundown(path):
    block = LiquidBlock(CatalogEntry("catalog/toons/a.mp4", 1500, "toons"), START,
                        START + datetime.timedelta(minutes=30), "A")
    block.plan = [BlockPlanEntry("catalog/toons/a.mp4", 0, 1800)]
    (path / "runtime/rundown.json").write_text(json.dumps({
        "server_time": START.isoformat(),
        "stations": {"Toons": [block_to_json(block)]},
        "meta": {"catalog/toons/a.mp4": {"type": "episode", "title": "Pilot"}},
    }))


def test_box_mode_schedules_come_from_rundown(box_dir):
    _make_box(box_dir)
    _write_rundown(box_dir)
    blocks = LiquidManager().schedules["Toons"]
    assert [(b.title, b.start_time) for b in blocks] == [("A", START)]


def test_box_mode_metadata_comes_from_rundown(box_dir):
    _make_box(box_dir)
    _write_rundown(box_dir)
    LiquidManager()
    assert MetadataIO.read("catalog/toons/a.mp4")["title"] == "Pilot"
    assert MetadataIO.read_many(["catalog/toons/a.mp4", "catalog/toons/b.mp4"]) == {
        "catalog/toons/a.mp4": {"type": "episode", "title": "Pilot"}}
