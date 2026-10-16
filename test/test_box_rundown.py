import datetime
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from shared.rundown import BlockPlanEntry  # noqa: E402
from fs42.box import clock  # noqa: E402
from fs42.box.rundown import block_from_json, block_to_json, box_meta, load_rundown  # noqa: E402
from fs42.catalog_entry import CatalogEntry  # noqa: E402
from fs42.liquid_blocks import LiquidBlock, LiquidClipBlock, LiquidOffAirBlock, LiquidWebBlock  # noqa: E402
from fs42.liquid_manager import LiquidManager  # noqa: E402

START = datetime.datetime(2026, 10, 16, 20, 0)
END = START + datetime.timedelta(minutes=30)
AUTOBUMP = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=X"


def _entry(path, duration, tag="sitcom", content_type="feature"):
    return CatalogEntry(path, duration, tag, [], 0, content_type, "video")


def _standard_block():
    block = LiquidBlock(_entry("catalog/toons/sitcom/a b#1.mp4", 1320), START, END, "A B", "standard",
                        {"start_bump": None, "end_bump": None, "bump_dir": "bumps"})
    block.sequence_key = {"station_name": "Toons", "sequence_name": "s", "tag_path": "sitcom"}
    block.plan = [
        BlockPlanEntry("catalog/toons/sitcom/a b#1.mp4", 0, 660),
        BlockPlanEntry("catalog/toons/commercials/c.mp4", 0, 30, content_type="commercial"),
        BlockPlanEntry("catalog/toons/bumps/b.mp4", 0, 10, content_type="bump"),
        BlockPlanEntry("catalog/toons/sitcom/a b#1.mp4", 660, 660),
    ]
    return block


def _offair_block():
    block = LiquidOffAirBlock(_entry("runtime/off_air_pattern.mp4", 60, "off_air", "off_air"), START, END, "Offair")
    block.plan = [BlockPlanEntry("runtime/off_air_pattern.mp4", 0, 60, content_type="off_air")] * 30
    return block


def _web_block():
    block = LiquidWebBlock(CatalogEntry(AUTOBUMP, 1800, ":autobump:"), START, END, "Offair")
    block.plan = [BlockPlanEntry(AUTOBUMP, 0, 1800)]
    return block


def _play_point(block, when):
    manager = LiquidManager.__new__(LiquidManager)
    manager.schedules = {"Toons": [block]}
    stations = MagicMock()
    stations.return_value.station_by_name.return_value = {"network_type": "standard"}
    with patch("fs42.liquid_manager.StationManager", stations):
        return manager.get_play_point("Toons", when)


def _round_trip(block):
    return block_from_json(json.loads(json.dumps(block_to_json(block))))


@pytest.fixture(autouse=True)
def _reset_clock():
    clock.set_server_time(datetime.datetime.now().isoformat())
    yield
    clock.set_server_time(datetime.datetime.now().isoformat())


@pytest.mark.parametrize("make_block", [_standard_block, _offair_block, _web_block])
def test_round_trip_gives_the_same_play_point_for_each_block_type(make_block):
    block = make_block()
    box = _round_trip(block)
    when = START + datetime.timedelta(seconds=700)
    server_point, box_point = _play_point(block, when), _play_point(box, when)
    assert type(box) is type(block)
    assert (box_point.index, box_point.offset, box_point.block_title) == (
        server_point.index, server_point.offset, server_point.block_title)
    assert [e.toJSON() for e in box_point.plan] == [e.toJSON() for e in server_point.plan]


def test_standard_block_keeps_times_title_breaks_and_sequence():
    block = _standard_block()
    box = _round_trip(block)
    assert (box.start_time, box.end_time, box.title, box.break_strategy) == (START, END, "A B", "standard")
    assert box.break_info == block.break_info and box.sequence_key == block.sequence_key
    assert box.content.path == "catalog/toons/sitcom/a b#1.mp4" and box.content.title == block.content.title


def test_clip_block_content_list_survives_round_trip():
    clips = [_entry("catalog/toons/clips/1.mp4", 60), _entry("catalog/toons/clips/2.mp4", 90)]
    block = LiquidClipBlock(clips, START, END, "clips")
    block.plan = [BlockPlanEntry(c.path, 0, c.duration) for c in clips]
    assert [c.path for c in _round_trip(block).content] == ["catalog/toons/clips/1.mp4", "catalog/toons/clips/2.mp4"]


def test_load_rundown_fills_meta_and_returns_blocks_by_station(tmp_path):
    block = _standard_block()
    path = tmp_path / "rundown.json"
    path.write_text(json.dumps({
        "server_time": START.isoformat(),
        "stations": {"Toons": [block_to_json(block)]},
        "meta": {"catalog/toons/sitcom/a b#1.mp4": {"title": "A"}},
    }))
    loaded = load_rundown(str(path))
    assert loaded["Toons"][0].title == "A B"
    assert box_meta("catalog/toons/sitcom/a b#1.mp4") == {"title": "A"}
    assert box_meta("catalog/toons/other.mp4") is None


def test_load_rundown_missing_file_is_empty(tmp_path):
    assert load_rundown(str(tmp_path / "nope.json")) == {}


def test_clock_follows_server_time_even_when_local_clock_is_years_off():
    clock.set_server_time("2026-10-16T20:00:00", received_at=datetime.datetime(2001, 1, 1, 0, 0))
    expected = datetime.datetime(2026, 10, 16, 20) - datetime.datetime(2001, 1, 1)
    assert abs((clock.now() - datetime.datetime.now()) - expected) < datetime.timedelta(seconds=1)
