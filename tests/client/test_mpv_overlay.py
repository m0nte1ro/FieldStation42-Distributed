import pytest

QtGui = pytest.importorskip("PySide6.QtGui")  # clients install Qt; the CI test environment doesn't

from client.osd.mpv_overlay import OVERLAY_ID, MpvOverlay  # noqa: E402


class FakeMpv:
    def __init__(self, width=320, height=180):
        self.osd_width, self.osd_height = width, height
        self.commands = []

    def command(self, *args):
        self.commands.append(args)


def _draw_box(image, color=0xFF00FF00):
    painter = QtGui.QPainter(image)
    painter.fillRect(10, 10, 50, 20, QtGui.QColor.fromRgba(color))
    painter.end()


@pytest.fixture
def overlay(tmp_path):
    mpv = FakeMpv()
    return mpv, MpvOverlay(mpv, str(tmp_path / "osd.bgra"))


def test_nothing_on_screen_sends_nothing(overlay):
    mpv, osd = overlay
    osd.frame()
    osd.present()
    assert mpv.commands == []


def test_a_drawn_frame_goes_to_mpv_as_an_overlay(overlay, tmp_path):
    mpv, osd = overlay
    _draw_box(osd.frame())
    osd.present()
    assert mpv.commands == [("overlay-add", OVERLAY_ID, 0, 0, str(tmp_path / "osd.bgra"), 0, "bgra", 320, 180, 1280)]
    # premultiplied BGRA in the file, where mpv reads it: the box's green pixel at (10, 10)
    pixel = (10 * 1280) + 10 * 4
    assert (tmp_path / "osd.bgra").read_bytes()[pixel:pixel + 4] == bytes([0, 255, 0, 255])


def test_an_unchanged_frame_is_not_sent_again(overlay):
    mpv, osd = overlay
    for _ in range(3):
        _draw_box(osd.frame())
        osd.present()
    assert len(mpv.commands) == 1


def test_a_changed_frame_goes_in_the_other_buffer(overlay):
    # mpv may still be reading the shown buffer, so the next frame is drawn in the other one
    mpv, osd = overlay
    _draw_box(osd.frame())
    osd.present()
    _draw_box(osd.frame(), color=0xFFFF0000)
    osd.present()
    assert [c[5] for c in mpv.commands] == [0, 320 * 180 * 4]


def test_the_overlay_goes_away_when_the_osd_has_nothing_to_show(overlay):
    mpv, osd = overlay
    _draw_box(osd.frame())
    osd.present()
    osd.frame()
    osd.present()
    osd.frame()
    osd.present()
    assert mpv.commands[1:] == [("overlay-remove", OVERLAY_ID)]


def test_the_osd_follows_the_size_of_mpvs_picture(overlay):
    mpv, osd = overlay
    assert osd.frame().size() == QtGui.QImage(320, 180, QtGui.QImage.Format_ARGB32).size()
    mpv.osd_width, mpv.osd_height = 640, 360
    image = osd.frame()
    assert (image.width(), image.height()) == (640, 360)
    _draw_box(image)
    osd.present()
    assert mpv.commands[-1][7:] == (640, 360, 2560)


def test_before_mpv_has_a_picture_there_is_nothing_to_draw_on(tmp_path):
    mpv = FakeMpv(0, 0)
    osd = MpvOverlay(mpv, str(tmp_path / "osd.bgra"))
    assert osd.frame() is None
    osd.present()
    assert mpv.commands == []
