import json
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())
# the Tk guide is imported by station_player; boxes install python3-tk, this test never opens a window
for _tk in ("tkinter", "tkinter.font", "tkinter.ttk"):
    sys.modules.setdefault(_tk, MagicMock())

from fs42 import station_player  # noqa: E402
from fs42.box.sync import refresh_requested, reload_requested  # noqa: E402
from fs42.station_player import StationPlayer  # noqa: E402

TOONS = {"network_name": "Toons", "channel_number": 3}


class FakeMPV:
    def __init__(self):
        self.commands = []
        self.played = []
        self.start = "none"
        self.time_pos = None
        self.duration = 600.0
        self.stuck_at_zero = False

    def command(self, *args):
        self.commands.append(args)
        if args[:2] == ("set", "start"):
            self.start = args[2]

    def play(self, path):
        self.played.append(path)
        if self.stuck_at_zero or self.start == "none":
            self.time_pos = 0.0
        else:
            self.time_pos = float(self.start)


@pytest.fixture
def player(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog/a.mp4").write_bytes(b"x")
    manager = MagicMock()
    manager.return_value.server_conf = {
        "status_socket": str(tmp_path / "status.json"), "date_time_format": "%Y-%m-%dT%H:%M:%S",
        "video_seek_timeout": 1,
    }
    refresh_requested.clear()
    with patch.object(station_player, "StationManager", manager), \
            patch.object(StationPlayer, "_apply_vfx"), \
            patch.object(StationPlayer, "_nfo_overlay_data", return_value=None):
        yield lambda: StationPlayer(dict(TOONS), lambda: None, mpv=FakeMPV())
    refresh_requested.clear()


def _status(tmp_path):
    return json.loads((tmp_path / "status.json").read_text())


def test_tune_opens_once_at_the_offset(player):
    p = player()
    assert p.play_file("catalog/a.mp4", file_duration=600, offset_seconds=120)
    start_index = p.mpv.commands.index(("set", "start", "120"))
    assert p.mpv.played == ["catalog/a.mp4"]
    assert start_index < len(p.mpv.commands) and not any(c[0] == "seek" for c in p.mpv.commands)


def test_zero_offset_resets_start(player):
    p = player()
    p.play_file("catalog/a.mp4", file_duration=600, offset_seconds=0)
    assert ("set", "start", "none") in p.mpv.commands


def test_open_that_misses_the_offset_falls_back_to_seek(player):
    p = player()
    p.mpv.stuck_at_zero = True
    with patch.object(StationPlayer, "_seek_with_verify") as seek:
        p.play_file("catalog/a.mp4", file_duration=600, offset_seconds=120)
    seek.assert_called_once()
    assert seek.call_args.args[1] == 120


def test_box_plays_server_url_but_reports_original_path(player, tmp_path):
    (tmp_path / "box.json").write_text(json.dumps({"server_url": "http://homelab:4242"}))
    p = player()
    assert p.play_file("catalog/remote only.mp4", file_duration=600, offset_seconds=0)
    assert p.mpv.played == ["http://homelab:4242/box/media?path=catalog%2Fremote%20only.mp4"]
    assert _status(tmp_path)["file_path"] == "catalog/remote only.mp4"


def test_box_play_and_wait_maps_the_path(player, tmp_path):
    (tmp_path / "box.json").write_text(json.dumps({"server_url": "http://homelab:4242"}))
    p = player()
    p.input_check_fn = lambda: station_player.PlayerOutcome(station_player.PlayerState.CHANNEL_CHANGE)
    p.play_and_wait("catalog/ppv/movie.mp4")
    assert ("loadfile", "http://homelab:4242/box/media?path=catalog%2Fppv%2Fmovie.mp4", "replace") in p.mpv.commands


def test_box_schedule_panic_requests_refresh_and_builds_nothing(player, tmp_path):
    (tmp_path / "box.json").write_text(json.dumps({"server_url": "http://homelab:4242"}))
    p = player()
    with patch.object(station_player, "LiquidSchedule", side_effect=AssertionError("box built a schedule")):
        p.schedule_panic("Toons")
    assert refresh_requested.is_set()


def test_input_check_reloads_when_sync_requests_it(tmp_path):
    import field_player

    socket = tmp_path / "channel.socket"
    socket.write_text("")
    stations, liquid = MagicMock(), MagicMock()
    stations.return_value.server_conf = {"channel_socket": str(socket)}
    reload_requested.set()
    with patch.object(field_player, "StationManager", stations), patch.object(field_player, "LiquidManager", liquid):
        assert field_player.input_check() is None
    stations.return_value._reload_stations.assert_called_once()
    liquid.return_value.reload_schedules.assert_called_once()
    assert not reload_requested.is_set()
