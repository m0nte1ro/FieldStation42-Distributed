import datetime
import os

from server.bumps.styles import STYLES, STYLES_FILE, note_style, styles_in_use

TODAY = datetime.date(2026, 10, 20)


def test_styles_are_the_client_osd_styles():
    from client.playback.config import OSD_STYLES
    assert STYLES == OSD_STYLES


def test_with_no_client_heard_from_the_station_look_is_rendered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert styles_in_use(TODAY) == [None]


def test_styles_clients_asked_for_lately_are_rendered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert note_style("cable", TODAY) is True  # new: worth a scan now
    assert note_style("cable", TODAY) is False
    note_style(None, TODAY)  # an older client that sends no style gets the station's look
    note_style("kids", TODAY - datetime.timedelta(days=45))  # nobody has used it for a while
    assert styles_in_use(TODAY) == [None, "cable"]


def test_the_note_is_written_once_a_day_and_not_where_clients_watch(tmp_path, monkeypatch):
    # runtime/bumps is part of /client/version: writing there would make every client resync
    monkeypatch.chdir(tmp_path)
    assert not STYLES_FILE.startswith("runtime/bumps")
    note_style("vcr", TODAY)
    first = os.stat(STYLES_FILE).st_mtime_ns
    note_style("vcr", TODAY)
    assert os.stat(STYLES_FILE).st_mtime_ns == first
