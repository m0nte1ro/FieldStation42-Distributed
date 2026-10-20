import json

import pytest

QtGui = pytest.importorskip("PySide6.QtGui")  # clients install Qt; the CI test environment doesn't

from client.osd.main import StatusDisplay, StatusDisplayConfig, VolumeDisplay, VolumeDisplayConfig, load_objects  # noqa: E402

STYLES = ["vcr", "cable", "kids"]


@pytest.fixture(autouse=True)
def runtime(tmp_path, monkeypatch):
    QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["test", "-platform", "offscreen"])
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime/play_status.socket").write_text(json.dumps(
        {"status": "playing", "network_name": "Desenhos", "channel_number": 3, "title": "Avatar"}))
    return tmp_path


def _draw(obj, w=1280, h=720):
    image = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QtGui.QPainter(image)
    obj.draw(painter, w, h)
    painter.end()
    return image


def _blank(w=1280, h=720):
    image = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    return image


def _volume(runtime, text, style):
    (runtime / "runtime/volume.socket").write_text(json.dumps({"volume": text}))
    display = VolumeDisplay(VolumeDisplayConfig(), style=style)
    display.update(0.01)
    return display


def test_every_style_draws_the_channel_its_own_way():
    drawn = [_draw(StatusDisplay(StatusDisplayConfig(), style=s)) for s in STYLES]
    assert all(image != _blank() for image in drawn)
    assert drawn[0] != drawn[1] != drawn[2] != drawn[0]


@pytest.mark.parametrize("style", STYLES)
def test_the_channel_goes_away_after_its_time(style):
    display = StatusDisplay(StatusDisplayConfig(), style=style)
    display.update(60)
    assert _draw(display) == _blank()


@pytest.mark.parametrize("style", STYLES)
def test_every_style_has_a_volume_bar_and_a_mute_sign(runtime, style):
    bar, mute = _volume(runtime, "60%", style), _volume(runtime, "MUTED (60%)", style)
    assert _blank() != _draw(bar) != _draw(mute) != _blank()


def test_styles_scale_with_the_picture():
    small = StatusDisplay(StatusDisplayConfig(), style="cable")
    assert _draw(small, 640, 360) != _blank(640, 360)


def test_load_objects_uses_the_chosen_style():
    objects = load_objects("kids")
    assert {o.style for o in objects if isinstance(o, (StatusDisplay, VolumeDisplay))} == {"kids"}
