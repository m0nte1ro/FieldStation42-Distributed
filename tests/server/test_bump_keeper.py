import datetime
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from server.bumps import keeper  # noqa: E402
from shared.rundown import BlockPlanEntry  # noqa: E402

NOW = datetime.datetime(2026, 10, 19, 20, 0)
MESSAGE = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=Panda&duration=7000&countdown=false"
NEXT_UP = MESSAGE.replace("title=Panda", "title=Panda&next_network=Panda")
STATIONS = [{"network_name": "Panda", "network_type": "standard"}, {"network_name": "Guide", "network_type": "guide"}]


def _block(title, *paths):
    return SimpleNamespace(title=title, plan=[BlockPlanEntry(p, 0, 7) for p in paths])


@pytest.fixture
def schedule(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    blocks = [_block("Bluey", "catalog/a.mp4", MESSAGE, NEXT_UP), _block("Peppa", MESSAGE, NEXT_UP), _block("Panda Kids")]
    fake_io = MagicMock()
    fake_io.return_value.query_liquid_blocks.return_value = blocks
    monkeypatch.setattr(keeper, "LiquidIO", fake_io)
    return blocks


def _fake_render(rendered, fail_first=False, delay=0):
    def render(job):
        if fail_first and not rendered:
            rendered.append("failed")
            raise RuntimeError("chromium crashed")
        time.sleep(delay)
        os.makedirs(os.path.dirname(job.path), exist_ok=True)
        open(job.path, "wb").close()
        rendered.append(job.key)
        return job.path
    return render


def test_pending_jobs_dedupes_and_skips_cached(schedule):
    jobs = keeper.pending_jobs(STATIONS, NOW)
    # one message bump (same look in both blocks), next-up for Peppa and for Panda Kids
    assert sorted(j.kind for j in jobs) == ["message", "next_up", "next_up"]
    assert {j.params.get("next_title") for j in jobs if j.kind == "next_up"} == {"Peppa", "Panda Kids"}
    open_path = jobs[0].path
    os.makedirs(os.path.dirname(open_path), exist_ok=True)
    open(open_path, "wb").close()
    assert len(keeper.pending_jobs(STATIONS, NOW)) == 2


def test_scan_renders_each_missing_job_once(schedule):
    rendered = []
    assert keeper.scan_once(STATIONS, render=_fake_render(rendered), now=NOW) == 3
    assert keeper.scan_once(STATIONS, render=_fake_render(rendered), now=NOW) == 0
    assert len(rendered) == 3


def test_scan_survives_a_failing_render(schedule):
    rendered = []
    assert keeper.scan_once(STATIONS, render=_fake_render(rendered, fail_first=True), now=NOW) == 2


def test_overlapping_scans_do_not_double_render(schedule):
    rendered = []
    render = _fake_render(rendered, delay=0.1)
    threads = [threading.Thread(target=keeper.scan_once, args=(STATIONS,), kwargs={"render": render, "now": NOW}) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(rendered) == 3 and len(set(rendered)) == 3


def _wait_for(scans, count, seconds=1.5):
    deadline = time.time() + seconds
    while len(scans) < count and time.time() < deadline:
        time.sleep(0.01)
    return len(scans)


def test_requested_scan_runs_before_the_interval():
    scans = []
    keeper.start_bump_keeper(interval=600, scan=lambda: scans.append(1), signature=lambda: 1, poll=60)
    assert _wait_for(scans, 1) == 1
    keeper.request_bump_scan()
    assert _wait_for(scans, 2) == 2


def test_schedule_change_triggers_a_scan():
    scans, versions = [], iter([1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2])
    keeper.start_bump_keeper(interval=600, scan=lambda: scans.append(1), signature=lambda: next(versions, 2), poll=0.02)
    assert _wait_for(scans, 2) == 2
    time.sleep(0.2)
    assert len(scans) == 2
