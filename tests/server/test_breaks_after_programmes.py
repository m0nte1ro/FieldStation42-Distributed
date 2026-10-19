import datetime
import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from server.catalog.catalog import ShowCatalog  # noqa: E402
from server.catalog.catalog_entry import MatchingContentNotFound  # noqa: E402
from server.scheduler.liquid_blocks import LiquidBlock  # noqa: E402

TWO_PM = datetime.datetime(2026, 10, 19, 14, 0)
AUTOBUMP = {"title": "Desenhos", "subtitle": "Sempre ligado", "next_up_text": "A seguir na {network}", "fill_break": 0.25}


def _catalog(autobump=None, strategy="standard"):
    catalog = ShowCatalog.__new__(ShowCatalog)
    catalog.config = {
        "network_name": "Desenhos", "break_strategy": strategy, "break_duration": 120,
        "commercial_free": False, "bump_dir": "bump", "monday": {"14": {"tags": "cartoons"}},
    }
    if autobump:
        catalog.config["autobump"] = dict(autobump)
    catalog.clip_index = {
        "bump": [SimpleNamespace(path="bump.mp4", duration=5, hints=[], tag="bump", count=0, content_type="bump",
                                 media_type="video")],
        "bump-prebump": [], "bump-postbump": [],
    }
    catalog._l = logging.getLogger("test")
    catalog.min_gap = 3

    def find_commercial(seconds, when, commercial_dir=None):
        if seconds < 30:
            raise MatchingContentNotFound("nothing fits")
        return SimpleNamespace(path="ad.mp4", duration=30, content_type="commercial", media_type="video")

    catalog.find_commercial = find_commercial
    return catalog


def _plan(catalog, episode_seconds, block_minutes, strategy="standard"):
    episode = SimpleNamespace(path="doraemon.avi", realpath="doraemon.avi", duration=episode_seconds,
                              title="Doraemon", content_type="feature", media_type="video")
    break_info = {"start_bump": None, "end_bump": None, "bump_dir": None, "commercial_dir": None}
    block = LiquidBlock(episode, TWO_PM, TWO_PM + datetime.timedelta(minutes=block_minutes), "Doraemon", strategy,
                        break_info)
    block.make_plan(catalog)
    return block.plan


@pytest.mark.parametrize("strategy", ["standard", "center", "end"])
def test_a_programme_is_never_cut_by_a_break(strategy):
    plan = _plan(_catalog(strategy=strategy), episode_seconds=1320, block_minutes=30, strategy=strategy)
    shows = [e for e in plan if e.path == "doraemon.avi"]
    assert len(shows) == 1 and (shows[0].skip, shows[0].duration) == (0, 1320)
    assert plan[0].path == "doraemon.avi"


def test_after_the_episode_comes_one_coming_up_next_then_the_countdown():
    plan = _plan(_catalog(AUTOBUMP), episode_seconds=624, block_minutes=15)
    assert [e.path.split("?")[0] for e in plan] == ["doraemon.avi"] + [":autobump:=" + plan[1].path[11:].split("?")[0]] * 2
    next_up, countdown = plan[1], plan[2]
    assert "subtitle=A+seguir+na+Desenhos" in next_up.path or "subtitle=A%20seguir%20na%20Desenhos" in next_up.path
    assert "countdown=false" in next_up.path and next_up.duration == 7
    assert "countdown=true" in countdown.path
    assert next_up.duration + countdown.duration == pytest.approx(900 - 624)


def test_a_gap_too_short_for_the_countdown_is_just_the_coming_up_next():
    plan = _plan(_catalog(AUTOBUMP), episode_seconds=895, block_minutes=15)
    assert len(plan) == 2 and "countdown=false" in plan[1].path
    assert plan[1].duration == pytest.approx(5)


def test_the_break_does_not_depend_on_chance():
    # fill_break used to pick at random between a filler and a message bump for each break
    plans = [_plan(_catalog(AUTOBUMP), episode_seconds=624, block_minutes=15) for _ in range(20)]
    assert {len(p) for p in plans} == {3}
