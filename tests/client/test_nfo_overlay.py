import pytest
from client.osd.overlays.nfo_overlay import NFOOverlay


class TestOverlayLines:

    def test_music_order_is_artist_title_album_year(self):
        meta = {
            "type": "music",
            "title": "No Rain",
            "artist": "Blind Melon",
            "album": "Live at the Palace",
            "year": "1993",
        }
        assert NFOOverlay.overlay_lines(meta) == [
            "Blind Melon", "No Rain", "Live at the Palace", "1993",
        ]

    def test_music_skips_missing_fields(self):
        meta = {"type": "music", "title": "Solo", "artist": "Nobody"}
        assert NFOOverlay.overlay_lines(meta) == ["Nobody", "Solo"]

    def test_plaintext_returns_lines(self):
        meta = {"type": "plaintext", "lines": ["a", "b", "c"]}
        assert NFOOverlay.overlay_lines(meta) == ["a", "b", "c"]

    def test_movie_is_not_overlay_eligible(self):
        meta = {"type": "movie", "title": "The Thing", "year": "1982"}
        assert NFOOverlay.overlay_lines(meta) is None

    def test_episode_is_not_overlay_eligible(self):
        meta = {"type": "episode", "title": "The Constant"}
        assert NFOOverlay.overlay_lines(meta) is None

    def test_none_is_none(self):
        assert NFOOverlay.overlay_lines(None) is None
