import pytest

from shared.title_parser import TitleParser

CARTOONS = ("catalog/desenhos", "cartoons")
SHOWS = ("catalog/series", "shows")


@pytest.mark.parametrize("path, where, title", [
    ("catalog/desenhos/cartoons/Doraemon [tmdbid-57911]/Arquivo por ano/Doraemon 1993/Doraemon 1993-07-09 Capítulo 1258 - La pegatina.avi", CARTOONS, "Doraemon"),
    ("catalog/desenhos/cartoons/Popeye the Sailor (1933)/Year 1935/Popeye - 1935E03.mkv", CARTOONS, "Popeye the Sailor"),
    ("catalog/desenhos/cartoons/SpongeBob SquarePants [tmdbid-387]/Season 05/SpongeBob SquarePants - S05E12.mkv", CARTOONS, "SpongeBob SquarePants"),
    ("catalog/desenhos/cartoons/Beyblade [tmdbid-54728]/Season 01/Beyblade (2001) - S01E14.mkv", CARTOONS, "Beyblade"),
    ("catalog/desenhos/cartoons/Phineas and Ferb [tmdbid-1877]/Season 01/Phineas and Ferb - S01E17.mkv", CARTOONS, "Phineas and Ferb"),
    ("catalog/desenhos/cartoons/Rua Sésamo (1989)/Season 01/Rua Sésamo - S01E09.avi", CARTOONS, "Rua Sésamo"),
    ("catalog/desenhos/cartoons/Avatar - The Last Airbender [tmdbid-246]/Season 01/Avatar - The Last Airbender - S01E14.mp4", CARTOONS, "Avatar - The Last Airbender"),
    ("catalog/series/shows/Riverdale [tmdbid-69050]/Riverdale.US.S06E13.720p.AMZN.WEBRip.x264-GalaxyTV.mkv", SHOWS, "Riverdale"),
    ("catalog/series/shows/The Office (US) [tmdbid-2316]/The.Office.US.S01E03.1080p.BluRay.x265-RARBG.mp4", SHOWS, "The Office (US)"),
    ("catalog/series/shows/The Grand Tour (2016) [tmdbid-67557]/The Grand Tour - S03E07 - Well Aged Scotch.mkv", SHOWS, "The Grand Tour"),
    ("catalog/series/shows/9-1-1 [tmdbid-75219]/9-1-1 S09E18 1080p HEVC x265-MeGusta.mkv", SHOWS, "9-1-1"),
    ("catalog/series/shows/Game of Thrones/Season 5/Game.of.Thrones.S05E03.1080p.Bluray.x265.TrueHD.Atmos-GOD.mkv", SHOWS, "Game of Thrones"),
])
def test_a_show_is_named_after_its_folder(path, where, title):
    assert TitleParser.show_folder_title(path, *where) == title


def test_a_file_straight_in_the_tag_folder_has_no_show_folder():
    assert TitleParser.show_folder_title("catalog/desenhos/cartoons/Some Short.mkv", *CARTOONS) is None


def test_a_file_outside_the_channel_has_no_show_folder():
    assert TitleParser.show_folder_title("runtime/signoff.mp4", *CARTOONS) is None


def test_a_scheduled_episode_shows_its_shows_name(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from server.scheduler import liquid_io
    from server.scheduler.liquid_io import LiquidIO

    manager = MagicMock()
    manager.return_value.server_conf = {"normalize_titles": True, "title_patterns": []}
    manager.return_value.station_by_name.return_value = {"network_name": "Desenhos", "content_dir": "catalog/desenhos"}
    monkeypatch.setattr(liquid_io, "StationManager", manager)
    episode = SimpleNamespace(path="catalog/desenhos/cartoons/Popeye the Sailor (1933)/Year 1935/Popeye - 1935E03.mkv",
                              tag="cartoons", title="Popeye - 1935E03", duration=400.0)
    row = (1, "Desenhos", "LiquidBlock", "2026-10-20T14:00:00", "2026-10-20T14:15:00", "end",
           "Popeye - 1935E03", None, None, "7", "[]")
    block = LiquidIO._build_block_from_row(row, content_cache={7: episode})
    assert block.title == "Popeye the Sailor"
