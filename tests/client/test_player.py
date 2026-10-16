import json
import time
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())
# the Tk guide is imported by the player; clients install python3-tk, this test never opens a window
for _tk in ("tkinter", "tkinter.font", "tkinter.ttk"):
    sys.modules.setdefault(_tk, MagicMock())

from client.playback import player as station_player  # noqa: E402
from client.playback.sync import refresh_requested, reload_requested  # noqa: E402
from client.playback.player import StationPlayer  # noqa: E402

TOONS = {"network_name": "Toons", "channel_number": 3}


class FakeMPV:
    def __init__(self):
        self.commands = []
        self.played = []
        self.start = "none"
        self.time_pos = None
        self.duration = 600.0
        self.stuck_at_zero = False
        self.idle_active = False

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
    (tmp_path / "client.json").write_text(json.dumps({"server_url": "http://homelab:4242"}))
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


def test_client_plays_server_url_but_reports_original_path(player, tmp_path):
    p = player()
    assert p.play_file("catalog/remote only.mp4", file_duration=600, offset_seconds=0)
    assert p.mpv.played == ["http://homelab:4242/client/media?path=catalog%2Fremote%20only.mp4"]
    assert _status(tmp_path)["file_path"] == "catalog/remote only.mp4"


def test_client_play_and_wait_maps_the_path(player, tmp_path):
    p = player()
    p.input_check_fn = lambda: station_player.PlayerOutcome(station_player.PlayerState.CHANNEL_CHANGE)
    p.play_and_wait("catalog/ppv/movie.mp4")
    assert ("loadfile", "http://homelab:4242/client/media?path=catalog%2Fppv%2Fmovie.mp4", "replace") in p.mpv.commands


def test_schedule_panic_requests_a_fresh_rundown(player, tmp_path):
    p = player()
    p.schedule_panic("Toons")
    assert refresh_requested.is_set()


def test_input_check_reloads_when_sync_requests_it(tmp_path):
    from client import main as field_player

    socket = tmp_path / "channel.socket"
    socket.write_text("")
    stations, store = MagicMock(), MagicMock()
    stations.return_value.server_conf = {"channel_socket": str(socket)}
    reload_requested.set()
    with patch.object(field_player, "StationManager", stations), patch.object(field_player, "rundown_store", store):
        assert field_player.input_check() is None
    stations.return_value._reload_stations.assert_called_once()
    store.load.assert_called_once()
    assert not reload_requested.is_set()


def test_client_plays_files_it_has_locally_without_the_server(player, tmp_path):
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime/standby.png").write_bytes(b"png")
    p = player()
    p.play_file("runtime/standby.png")
    assert p.mpv.played == ["runtime/standby.png"]


def test_failed_server_open_gives_up_fast(player, tmp_path):
    p = player()
    p.mpv.play = lambda path: p.mpv.played.append(path)  # never starts: time_pos stays None
    p.mpv.idle_active = True
    started = time.time()
    assert p.play_file("catalog/gone.mp4", file_duration=600, offset_seconds=0) is False
    assert time.time() - started < 0.9 * 1  # well under video_seek_timeout


def test_channel_change_during_a_server_open_is_not_lost(player, tmp_path):
    p = player()
    p.mpv.play = lambda path: p.mpv.played.append(path)
    p.mpv.idle_active = False  # still loading
    change = station_player.PlayerOutcome(station_player.PlayerState.CHANNEL_CHANGE)
    p.input_check_fn = lambda: change
    assert p.play_file("catalog/slow.mp4", file_duration=600, offset_seconds=0) is False
    assert p._pending_response is change


def _stations(*confs):
    manager = MagicMock()
    manager.stations = list(confs)
    return manager


def test_current_station_follows_a_station_that_moved_in_the_list():
    from client import main as field_player

    toons = {"network_name": "Toons", "channel_number": 3, "hidden": False}
    news = {"network_name": "News", "channel_number": 2, "hidden": False}
    fresh_toons = dict(toons, logo_dir="new")
    assert field_player.current_station(_stations(news, fresh_toons), toons) == (1, fresh_toons)


def test_current_station_falls_back_when_the_station_was_removed():
    from client import main as field_player

    news = {"network_name": "News", "channel_number": 2, "hidden": False}
    gone = {"network_name": "Toons", "channel_number": 3, "hidden": False}
    assert field_player.current_station(_stations(news), gone) == (0, news)


def test_current_station_finds_a_renamed_station_by_channel_number():
    from client import main as field_player

    renamed = {"network_name": "Cartoons", "channel_number": 3, "hidden": False}
    old = {"network_name": "Toons", "channel_number": 3, "hidden": False}
    assert field_player.current_station(_stations(renamed), old) == (0, renamed)
