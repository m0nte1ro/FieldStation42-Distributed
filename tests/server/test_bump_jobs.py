import sys
from unittest.mock import MagicMock
from urllib.parse import urlencode

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from server.bumps.jobs import BUMP_DIR, job_for  # noqa: E402

PAGE = "http://127.0.0.1:4242/static/bump/bump.html"


def bump(**params):
    base = {"title": "Canal Panda", "subtitle": "Desenhos todo o dia", "variation": "retro", "duration": "7000",
            "bg_music": "http://127.0.0.1:4242/static/bump/music/logo0.mp3", "loopmusic": "true", "countdown": "false"}
    base.update(params)
    return f":autobump:={PAGE}?{urlencode(base)}"


def test_message_bump_job():
    job = job_for(bump())
    assert (job.kind, job.seconds, job.loop, job.countdown) == ("message", 7.0, False, False)
    assert job.params["title"] == "Canal Panda" and job.path == f"{BUMP_DIR}/{job.key}.mp4"


def test_identical_bumps_share_a_key():
    assert job_for(bump()).key == job_for(bump()).key
    assert job_for(bump()).key != job_for(bump(title="Outro")).key


def test_next_up_job_uses_next_title_and_drops_network():
    job = job_for(bump(next_network="Panda", subtitle="A seguir na Panda"), "Bluey")
    assert job.kind == "next_up" and job.params["next_title"] == "Bluey" and "next_network" not in job.params


def test_next_up_without_next_title_is_not_rendered():
    assert job_for(bump(next_network="Panda"), None) is None


def test_different_titles_get_different_keys():
    assert job_for(bump(next_network="Panda"), "Bluey").key != job_for(bump(next_network="Panda"), "Peppa").key


def test_awkward_titles_survive():
    title = "Tom & Jerry's #1 «Ação»"
    job = job_for(bump(next_network="Panda"), title)
    assert job.params["next_title"] == title and job.key == job_for(bump(next_network="Panda"), title).key


def test_filler_job_is_a_30s_loop_with_countdown():
    short = job_for(bump(next_network="Panda", countdown="true", duration="133000"), "Bluey")
    long = job_for(bump(next_network="Panda", countdown="true", duration="2400000"), "Bluey")
    assert (short.kind, short.seconds, short.loop, short.countdown) == ("filler", 30.0, True, True)
    assert short.params["countdown"] == "false" and short.params["duration"] == "0"  # no fade-out at the loop point
    assert short.key == long.key  # one loop whatever the gap


def test_non_autobump_paths_have_no_job():
    assert job_for("catalog/toons/a.mp4", "Bluey") is None
    assert job_for("https://example.com/live.m3u8", None) is None


def test_fractional_durations_are_fine():
    # bg_video bumps get their length from ffprobe, e.g. 12345.678 ms
    job = job_for(bump(duration="12345.678"))
    assert job.seconds == pytest.approx(12.345678)


def test_filler_page_never_fades_out_between_loops():
    job = job_for(bump(next_network="Panda", countdown="true", duration="133000"), "Bluey")
    assert job.params["duration"] == "0" and job.seconds == 30.0


def test_next_show_is_the_current_one_when_it_resumes_after_the_break():
    from server.bumps.jobs import next_show_title

    assert next_show_title(["commercial", "bump", "feature"], "Bluey", "Peppa") == "Bluey"
    assert next_show_title(["commercial", "bump"], "Bluey", "Peppa") == "Peppa"
    assert next_show_title([], "Bluey", None) is None
