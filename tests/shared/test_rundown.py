import datetime
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from shared.rundown import (  # noqa: E402
    BlockPlanEntry, ScheduleNotFound, ScheduleQueryNotInBounds, block_at, decode_rundown,
    is_autobump_url, play_point, strip_autobump,
)

START = datetime.datetime(2026, 10, 12, 20, 0)
STANDARD = {"network_type": "standard"}


def _block(start=START, minutes=30, title="Cartoons", plan=None):
    return SimpleNamespace(
        start_time=start, end_time=start + datetime.timedelta(minutes=minutes), title=title,
        plan=plan or [BlockPlanEntry("show.mp4", 0, 1797)],
    )


def test_inside_plan_returns_the_scheduled_entry():
    point = play_point(STANDARD, [_block()], START + datetime.timedelta(seconds=100))
    assert point.index == 0 and point.offset == 100 and point.plan[0].path == "show.mp4"


def test_gap_after_plan_plays_brb_until_block_end():
    when = START + datetime.timedelta(seconds=1798)
    point = play_point(dict(STANDARD, be_right_back_media="runtime/brb.png"), [_block()], when)
    assert [(e.path, e.duration) for e in point.plan] == [("runtime/brb.png", 2)]
    assert point.index == 0 and point.offset == 0 and point.block_title == "Cartoons"


def test_gap_without_brb_still_returns_nothing():
    assert play_point(STANDARD, [_block()], START + datetime.timedelta(seconds=1798)) is None


def test_second_block_is_found_by_time():
    later = _block(START + datetime.timedelta(minutes=30), title="News",
                   plan=[BlockPlanEntry("a.mp4", 0, 600), BlockPlanEntry("b.mp4", 0, 1200)])
    point = play_point(STANDARD, [_block(), later], START + datetime.timedelta(minutes=45))
    assert (point.block_title, point.index, point.offset) == ("News", 1, 300)


def test_streaming_channel_plays_its_streams_without_a_schedule():
    station = {"network_type": "streaming", "streams": [{"url": "https://x/live.m3u8", "duration": 30}]}
    point = play_point(station, [], START)
    assert point.plan[0].path == "https://x/live.m3u8" and point.plan[0].is_stream


def test_no_schedule_and_out_of_bounds_raise():
    with pytest.raises(ScheduleNotFound):
        block_at([], START)
    with pytest.raises(ScheduleQueryNotInBounds):
        block_at([_block()], START + datetime.timedelta(hours=2))


def test_autobump_urls_are_recognised_and_stripped():
    url = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=X"
    assert is_autobump_url(url) and not is_autobump_url("catalog/a.mp4")
    assert strip_autobump(url) == "http://127.0.0.1:4242/static/bump/bump.html?title=X"


def test_decode_rundown_round_trips_the_server_encoding():
    from server.api.rundown_export import block_to_json
    from server.catalog.catalog_entry import CatalogEntry
    from server.scheduler.liquid_blocks import LiquidBlock

    block = LiquidBlock(CatalogEntry("catalog/toons/a b#1.mp4", 1320, "sitcom"), START,
                        START + datetime.timedelta(minutes=30), "A B", "standard", {"bump_dir": "bumps"})
    block.plan = [BlockPlanEntry("catalog/toons/a b#1.mp4", 0, 660),
                  BlockPlanEntry("catalog/toons/commercials/c.mp4", 0, 30, content_type="commercial")]
    data = json.loads(json.dumps({"stations": {"Toons": [block_to_json(block)]}}))
    decoded = decode_rundown(data)["Toons"][0]
    assert (decoded.start_time, decoded.end_time, decoded.title) == (block.start_time, block.end_time, "A B")
    assert decoded.content.path == "catalog/toons/a b#1.mp4" and decoded.liquid_type == "LiquidBlock"
    when = START + datetime.timedelta(seconds=600)
    server, client = play_point(STANDARD, [block], when), play_point(STANDARD, [decoded], when)
    assert (client.index, client.offset) == (server.index, server.offset)
    assert [e.toJSON() for e in client.plan] == [e.toJSON() for e in server.plan]


def test_server_play_point_delegates_to_shared():
    from server.scheduler.liquid_manager import LiquidManager

    manager = LiquidManager.__new__(LiquidManager)
    manager.schedules = {"Toons": [_block()]}
    stations = MagicMock()
    stations.return_value.station_by_name.return_value = STANDARD
    when = START + datetime.timedelta(seconds=100)
    with patch("server.scheduler.liquid_manager.StationManager", stations):
        server = manager.get_play_point("Toons", when)
    shared = play_point(STANDARD, [_block()], when)
    assert (server.index, server.offset, server.block_title) == (shared.index, shared.offset, shared.block_title)


def _server_blocks():
    from server.catalog.catalog_entry import CatalogEntry
    from server.scheduler.liquid_blocks import (
        LiquidBlock, LiquidClipBlock, LiquidLoopBlock, LiquidOffAirBlock, LiquidWebBlock,
    )

    end = START + datetime.timedelta(minutes=30)
    autobump = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=X"
    standard = LiquidBlock(CatalogEntry("catalog/t/a.mp4", 1320, "t"), START, end, "A", "standard",
                           {"start_bump": None, "end_bump": None, "bump_dir": "bumps"})
    standard.sequence_key = {"station_name": "Toons", "sequence_name": "s", "tag_path": "t"}
    standard.plan = [BlockPlanEntry("catalog/t/a.mp4", 0, 660), BlockPlanEntry("catalog/t/c.mp4", 0, 30, content_type="commercial"),
                     BlockPlanEntry("catalog/t/a.mp4", 660, 660)]
    offair = LiquidOffAirBlock(CatalogEntry("runtime/off_air_pattern.mp4", 60, "off_air", content_type="off_air"), START, end, "Offair")
    offair.plan = [BlockPlanEntry("runtime/off_air_pattern.mp4", 0, 60, content_type="off_air")] * 30
    web = LiquidWebBlock(CatalogEntry(autobump, 1800, ":autobump:"), START, end, "Offair")
    web.plan = [BlockPlanEntry(autobump, 0, 1800)]
    clips = [CatalogEntry("catalog/t/clips/1.mp4", 60, "clips"), CatalogEntry("catalog/t/clips/2.mp4", 90, "clips")]
    clip = LiquidClipBlock(clips, START, end, "clips")
    clip.plan = [BlockPlanEntry(c.path, 0, c.duration) for c in clips] + [BlockPlanEntry("catalog/t/c.mp4", 0, 1650)]
    loop = LiquidLoopBlock([CatalogEntry("catalog/loop/m.mp4", 200, "content")], START, end, "Loop")
    loop.plan = [BlockPlanEntry("catalog/loop/m.mp4", 0, 200)] * 9
    return {"standard": standard, "offair": offair, "web": web, "clip": clip, "loop": loop}


@pytest.mark.parametrize("kind", ["standard", "offair", "web", "clip", "loop"])
def test_every_block_type_round_trips_to_the_same_play_point(kind):
    from server.api.rundown_export import block_to_json

    block = _server_blocks()[kind]
    decoded = decode_rundown(json.loads(json.dumps({"stations": {"S": [block_to_json(block)]}})))["S"][0]
    assert decoded.liquid_type == type(block).__name__
    assert (decoded.break_info, decoded.sequence_key) == (block.break_info or {}, block.sequence_key)
    for seconds in (0, 100, 700, 1500):
        when = START + datetime.timedelta(seconds=seconds)
        server, client = play_point(STANDARD, [block], when), play_point(STANDARD, [decoded], when)
        assert (client is None) == (server is None)
        if server:
            assert (client.index, client.offset, client.block_title) == (server.index, server.offset, server.block_title)
            assert [e.toJSON() for e in client.plan] == [e.toJSON() for e in server.plan]
