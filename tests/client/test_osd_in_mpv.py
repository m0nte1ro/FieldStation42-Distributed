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
    core_idle, idle_active = False, False  # playing

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
    osd = [c for c in mpv.commands if c[1] == 1]
    assert [c[0] for c in osd] == ["overlay-add"]
    assert osd[0][7:] == (640, 360, 2560)


def test_the_volume_bar_goes_away_after_its_time(osd):
    osd, mpv, tmp_path = osd
    osd._tick()
    (tmp_path / "runtime/volume.socket").write_text(json.dumps({"volume": "60%"}))
    osd._tick()
    osd.objects[0].time_since_change = 99
    osd._tick()
    assert [c[0] for c in mpv.commands if c[1] == 1] == ["overlay-add", "overlay-remove"]


def test_the_osd_uses_a_retro_font_by_default(app):
    assert osd_main.resolve_font(None, 40).family() == "VT323"


def _volume(tmp_path, text):
    (tmp_path / "runtime/volume.socket").write_text(json.dumps({"volume": text}))


def _drawn(display, w=640, h=360):
    image = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QtGui.QPainter(image)
    display.draw(painter, w, h)
    painter.end()
    return image


def test_muting_shows_the_mute_sign_for_as_long_as_it_is_muted(osd):
    _, _, tmp_path = osd
    display = VolumeDisplay(VolumeDisplayConfig())
    _volume(tmp_path, "MUTED (75%)")
    display.update(0.1)
    assert display.muted
    bar = VolumeDisplay(VolumeDisplayConfig())
    _volume(tmp_path, "75%")
    bar.update(0.1)
    assert _drawn(display) != _drawn(bar)  # a mute sign, not the volume bar
    display.update(60)  # long after the bar would have gone
    blank = QtGui.QImage(640, 360, QtGui.QImage.Format_ARGB32_Premultiplied)
    blank.fill(0)
    assert _drawn(display) != blank


def test_unmuting_brings_the_volume_bar_back(osd):
    _, _, tmp_path = osd
    display = VolumeDisplay(VolumeDisplayConfig())
    _volume(tmp_path, "MUTED (75%)")
    display.update(0.1)
    _volume(tmp_path, "75%")
    display.update(0.1)
    assert not display.muted and display.volume == 0.75



def _status(tmp_path, channel, network):
    (tmp_path / "runtime/play_status.socket").write_text(json.dumps(
        {"status": "playing", "channel_number": channel, "network_name": network}))


@pytest.fixture
def tv(app, tmp_path, monkeypatch):
    """The OSD with the channel name and volume, connected to a fake mpv straight away."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runtime").mkdir()
    monkeypatch.setattr(osd_main, "OVERLAY_FILE", str(tmp_path / "osd.bgra"))
    monkeypatch.setattr(osd_main, "STATIC_FILE", str(tmp_path / "static.bgra"), raising=False)
    mpv = FakeMpv()
    osd = MpvOsd(osd_main.load_objects("vcr", mute_state=lambda: None), connect=lambda: mpv)
    osd.timer.stop()
    return osd, mpv, tmp_path


def _static(mpv):
    return [c for c in mpv.commands if c[1] == 0]


def test_static_covers_the_picture_while_a_channel_tunes(tv):
    osd, mpv, _ = tv
    mpv.core_idle = True
    osd._tick()
    osd._tick()
    shown = _static(mpv)
    assert [c[0] for c in shown] == ["overlay-add", "overlay-add"]
    # small noise frames, scaled up to the whole picture by mpv on the GPU
    assert shown[0][7:9] == (320, 180) and shown[0][10:] == (640, 360)
    assert shown[0][5] != shown[1][5]  # a different frame each time: it moves
    mpv.core_idle = False
    osd._tick()
    osd._tick()
    assert [c[0] for c in _static(mpv)][-1] == "overlay-remove"
    assert [c[0] for c in _static(mpv)].count("overlay-remove") == 1


def test_no_static_with_no_file_loaded(tv):
    osd, mpv, _ = tv
    mpv.core_idle, mpv.idle_active = True, True
    osd._tick()
    assert _static(mpv) == []


def test_the_channel_name_waits_until_the_channel_plays(tv):
    osd, mpv, tmp_path = tv
    mpv.core_idle = True
    _status(tmp_path, 4, "Series")
    for _ in range(3):
        osd._tick()
    status = next(o for o in osd.objects if isinstance(o, osd_main.StatusDisplay))
    assert status.time_since_change <= 0  # held while tuning
    assert [c for c in mpv.commands if c[1] == 1] == []  # nothing drawn over the static yet
    mpv.core_idle = False
    osd._tick()
    assert [c[0] for c in mpv.commands if c[1] == 1] == ["overlay-add"]


def test_a_mute_made_outside_fs42_still_shows(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runtime").mkdir()
    display = VolumeDisplay(VolumeDisplayConfig(), mute_state=lambda: True)
    display.update(5.0)
    assert display.muted
    display._mute_state = lambda: False
    display.update(5.0)
    assert not display.muted


def test_no_mixer_answer_changes_nothing(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runtime").mkdir()
    display = VolumeDisplay(VolumeDisplayConfig(), mute_state=lambda: None)
    display.muted = True
    display.update(5.0)
    assert display.muted
