from unittest.mock import MagicMock

import pytest

from client.platform.window import mpv_window_options, tv_rect, window_size


@pytest.fixture
def QRect():
    # clients install Qt; the CI test environment doesn't
    return pytest.importorskip("PySide6.QtCore").QRect


def _screen(QRect):
    screen = MagicMock()
    screen.geometry.return_value = QRect(0, 0, 1920, 1080)
    return screen


def test_the_tv_is_fullscreen_by_default():
    assert window_size({}) is None
    assert mpv_window_options(None) == {"fs": True}


def test_the_osd_covers_the_screen_by_default(QRect):
    assert tv_rect(_screen(QRect), {}) == QRect(0, 0, 1920, 1080)


def test_fs42_window_plays_in_a_window_of_that_size():
    assert window_size({"FS42_WINDOW": "1280x720"}) == (1280, 720)
    assert mpv_window_options((1280, 720)) == {"fs": False, "geometry": "1280x720+0+0", "border": False}


def test_the_osd_covers_the_window_not_the_screen(QRect):
    assert tv_rect(_screen(QRect), {"FS42_WINDOW": "960x540"}) == QRect(0, 0, 960, 540)


def test_a_bad_window_size_says_what_it_expects():
    with pytest.raises(SystemExit, match="1280x720"):
        window_size({"FS42_WINDOW": "big"})
