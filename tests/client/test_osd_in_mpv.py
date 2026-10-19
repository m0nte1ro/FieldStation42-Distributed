import json

import pytest

QtGui = pytest.importorskip("PySide6.QtGui")  # clients install Qt; the CI test environment doesn't

from client.osd import main as osd_main  # noqa: E402
from client.osd.main import MpvOsd, VolumeDisplay, VolumeDisplayConfig  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["test", "-platform", "offscreen"])


class FakeMpv:
    osd_width, osd_height = 640, 360

    def __init__(self):
        self.commands = []

    def command(self, *args):
        self.commands.append(args)


@pytest.fixture
def osd(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runtime").mkdir()
    monkeypatch.setattr(osd_main, "OVERLAY_FILE", str(tmp_path / "osd.bgra"))
    mpv = FakeMpv()
    connections = []

    def connect():
        connections.append(1)
        if len(connections) == 1:
            raise FileNotFoundError("runtime/mpv.socket")  # the player hasn't started mpv yet
        return mpv

    osd = MpvOsd([VolumeDisplay(VolumeDisplayConfig())], connect=connect)
    osd.timer.stop()
    return osd, mpv, tmp_path


def test_a_volume_change_shows_over_the_video(osd):
    osd, mpv, tmp_path = osd
    osd._tick()  # mpv not there yet: nothing breaks, try again next tick
    assert osd.overlay is None
    (tmp_path / "runtime/volume.socket").write_text(json.dumps({"volume": "60%"}))
    osd._tick()
    assert [c[0] for c in mpv.commands] == ["overlay-add"]
    assert mpv.commands[0][7:] == (640, 360, 2560)


def test_the_volume_bar_goes_away_after_its_time(osd):
    osd, mpv, tmp_path = osd
    osd._tick()
    (tmp_path / "runtime/volume.socket").write_text(json.dumps({"volume": "60%"}))
    osd._tick()
    osd.objects[0].time_since_change = 99
    osd._tick()
    assert [c[0] for c in mpv.commands] == ["overlay-add", "overlay-remove"]
