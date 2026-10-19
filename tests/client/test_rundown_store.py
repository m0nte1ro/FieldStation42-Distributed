import datetime
import json

import pytest

from client.playback import clock, rundown_store

START = datetime.datetime(2026, 10, 16, 20, 0)
BLOCK = {
    "liquid_type": "LiquidBlock", "start_time": START.isoformat(),
    "end_time": (START + datetime.timedelta(minutes=30)).isoformat(), "title": "A", "break_strategy": "standard",
    "break_info": None, "sequence_key": None,
    "content": {"path": "catalog/toons/a.mp4", "title": "a", "tag": "toons", "duration": 1500.0,
                "content_type": "feature", "media_type": "video"},
    "plan": [{"path": "catalog/toons/a.mp4", "skip": 0, "duration": 1800, "is_stream": False,
              "content_type": "feature", "media_type": "video"}],
}


@pytest.fixture
def rundown(tmp_path):
    path = tmp_path / "rundown.json"
    path.write_text(json.dumps({"server_time": START.isoformat(), "stations": {"Toons": [BLOCK]},
                                "meta": {"catalog/toons/a.mp4": {"type": "episode", "title": "Pilot"}}}))
    yield str(path)
    rundown_store.load(str(tmp_path / "gone.json"))


def test_load_gives_blocks_metadata_and_play_points(rundown):
    rundown_store.load(rundown)
    assert [(b.title, b.start_time) for b in rundown_store.blocks("Toons")] == [("A", START)]
    assert rundown_store.meta("catalog/toons/a.mp4") == {"type": "episode", "title": "Pilot"}
    point = rundown_store.station_play_point({"network_name": "Toons", "network_type": "standard"},
                                             START + datetime.timedelta(seconds=90))
    assert (point.index, point.offset, point.block_title) == (0, 90, "A")


def test_unknown_station_has_no_schedule(rundown):
    rundown_store.load(rundown)
    with pytest.raises(rundown_store.ScheduleNotFound):
        rundown_store.programming_block("News", START)


def test_missing_rundown_is_empty(tmp_path):
    rundown_store.load(str(tmp_path / "nope.json"))
    assert rundown_store.blocks("Toons") == [] and rundown_store.meta("catalog/toons/a.mp4") is None


def test_clock_follows_server_time_even_when_local_clock_is_years_off():
    clock.set_server_time("2026-10-16T20:00:00", received_at=datetime.datetime(2001, 1, 1, 0, 0))
    expected = datetime.datetime(2026, 10, 16, 20) - datetime.datetime(2001, 1, 1)
    try:
        assert abs((clock.now() - datetime.datetime.now()) - expected) < datetime.timedelta(seconds=1)
    finally:
        clock.set_server_time(datetime.datetime.now().isoformat())
