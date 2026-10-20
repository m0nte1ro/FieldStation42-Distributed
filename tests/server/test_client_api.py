import datetime
import json
import os
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from server.catalog.catalog_io import CatalogIO  # noqa: E402
from server.catalog.fluid_statements import FluidStatements  # noqa: E402
from server.api.routes import client as client_api  # noqa: E402
from server.api.routes.client import router  # noqa: E402
from server.scheduler.liquid_io import LiquidIO  # noqa: E402
from shared.stations.manager import StationManager  # noqa: E402

DB = "runtime/fs42.db"
SHOW = "catalog/toons/a b#1.mp4"
TOONS = {
    "network_name": "Toons", "network_type": "standard", "channel_number": 3,
    "content_dir": "catalog/toons", "logo_dir": "logos", "standby_image": "runtime/standby.png",
    "sign_off_video": "runtime/signoff.mp4",
}
GUIDE = {
    "network_name": "Guide", "network_type": "guide", "channel_number": 0,
    "images": ["runtime/guide/g1.png"], "sound_to_play": "runtime/guide/music",
}


def _touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _insert_block(start, end, title="A", liquid_type="LiquidBlock", plan_path=SHOW):
    plan = [{"path": plan_path, "skip": 0, "duration": (end - start).total_seconds(), "is_stream": False,
             "content_type": "feature", "media_type": "video"}]
    with sqlite3.connect(DB) as conn:
        conn.execute(
            "INSERT INTO liquid_blocks (station, liquid_type, start_time, end_time, break_strategy, title,"
            " sequence_key, break_info, content_json, plan_json) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
            ("Toons", liquid_type, str(start), str(end), "standard", title, "1", json.dumps(plan)),
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    StationManager._StationManager__we_are_all_one = {
        "_initialized": True,
        "stations": [TOONS, GUIDE],
        "server_conf": {"db_path": DB, "normalize_titles": False, "title_patterns": []},
        "_name_index": {"Toons": TOONS, "Guide": GUIDE},
        "_number_index": {3: TOONS, 0: GUIDE},
    }
    os.makedirs("confs")
    with open("confs/toons.json", "w") as f:
        json.dump({"station_conf": TOONS}, f)
    for path in ("catalog/toons/logos/a.png", "runtime/standby.png", "runtime/guide/g1.png",
                 "runtime/guide/music/1.mp3", "runtime/guide/music/2.mp3", "catalog/toons/notes.json"):
        _touch(path)
    _touch(SHOW, bytes(range(100)))
    LiquidIO()
    CatalogIO()
    with sqlite3.connect(DB) as conn:
        FluidStatements.init_db(conn)
        conn.execute(
            "INSERT INTO catalog_entries (id, station, path, title, duration, tag, count, hints, realpath)"
            " VALUES (1, 'Toons', ?, 'a b#1', 1320, 'toons', 0, '[]', ?)",
            (SHOW, os.path.realpath(SHOW)),
        )
        conn.execute("INSERT INTO file_meta (path, meta) VALUES (?, ?)",
                     (os.path.realpath(SHOW), json.dumps({"type": "episode", "title": "Pilot"})))
    # the preset StationManager can't load from disk; tests that care replace this
    monkeypatch.setattr(StationManager, "_reload_stations", lambda self: None, raising=False)
    monkeypatch.setattr(client_api, "_conf_signature", None)
    monkeypatch.setattr(client_api, "LiquidManager", lambda: type("L", (), {"reload_schedules": lambda self: None})())
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []


def _now():
    return datetime.datetime.now().replace(microsecond=0)


def _rundown_titles(client, hours=24):
    data = client.get("/client/rundown", params={"hours": hours}).json()
    return [b["title"] for b in data["stations"]["Toons"]], data


def test_rundown_includes_block_that_started_before_now(client):
    now = _now()
    _insert_block(now - datetime.timedelta(hours=15), now + datetime.timedelta(hours=9), "Loop")
    titles, _ = _rundown_titles(client)
    assert titles == ["Loop"]


def test_rundown_excludes_blocks_ending_before_now_and_beyond_hours(client):
    now = _now()
    _insert_block(now - datetime.timedelta(hours=2), now - datetime.timedelta(hours=1), "Past")
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "Now")
    _insert_block(now + datetime.timedelta(hours=25), now + datetime.timedelta(hours=26), "Later")
    titles, data = _rundown_titles(client)
    assert titles == ["Now"]
    assert "Guide" not in data["stations"]


def test_rundown_carries_plan_paths_unchanged_and_meta(client):
    now = _now()
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20))
    _, data = _rundown_titles(client)
    block = data["stations"]["Toons"][0]
    assert block["plan"][0]["path"] == SHOW and block["content"]["path"] == SHOW
    assert data["meta"][SHOW]["title"] == "Pilot"
    assert data["version"] and data["server_time"]


def test_version_changes_when_a_block_is_added(client):
    before = client.get("/client/version").json()["version"]
    now = _now()
    _insert_block(now, now + datetime.timedelta(minutes=30))
    assert client.get("/client/version").json()["version"] != before


def test_version_changes_when_a_conf_file_changes(client):
    before = client.get("/client/version").json()["version"]
    with open("confs/toons.json", "w") as f:
        json.dump({"station_conf": dict(TOONS, channel_number=4)}, f)
    os.utime("confs/toons.json", (2_000_000_000, 2_000_000_000))
    assert client.get("/client/version").json()["version"] != before


def test_files_lists_confs_logos_standby_and_guide_assets(client):
    paths = [f["path"] for f in client.get("/client/files").json()]
    assert paths == [
        "catalog/toons/logos/a.png", "confs/toons.json", "runtime/guide/g1.png",
        "runtime/guide/music/1.mp3", "runtime/guide/music/2.mp3", "runtime/standby.png",
    ]


def test_file_in_manifest_is_served(client):
    response = client.get("/client/file", params={"path": "catalog/toons/logos/a.png"})
    assert response.status_code == 200 and response.content == b"x"


def test_file_outside_manifest_is_404(client):
    assert client.get("/client/file", params={"path": DB}).status_code == 404


def test_media_range_request_returns_206(client):
    response = client.get("/client/media", params={"path": SHOW}, headers={"Range": "bytes=0-9"})
    assert response.status_code == 206 and response.content == bytes(range(10))


@pytest.mark.parametrize("path", [
    "../confs/toons.json", "catalog/../confs/toons.json", "catalog/toons/notes.json", "/etc/passwd", "",
    "catalog/toons/../../confs/toons.json",
])
def test_media_refuses_escapes_and_non_media(client, path):
    assert client.get("/client/media", params={"path": path}).status_code == 403


def test_media_allows_station_media_keys_and_runtime(client):
    _touch("runtime/signoff.mp4")
    assert client.get("/client/media", params={"path": "runtime/signoff.mp4"}).status_code == 200


def test_media_missing_allowed_file_is_404(client):
    assert client.get("/client/media", params={"path": "catalog/toons/missing.mp4"}).status_code == 404


def test_stations_reload_when_conf_files_change_on_disk(client, monkeypatch):
    reloads = []
    monkeypatch.setattr(StationManager, "_reload_stations", lambda self: reloads.append(1), raising=False)
    client.get("/client/version")
    client.get("/client/rundown")
    assert len(reloads) == 1
    with open("confs/news.json", "w") as f:
        json.dump({"station_conf": {"network_name": "News"}}, f)
    client.get("/client/rundown")
    assert len(reloads) == 2


def test_media_in_the_catalog_is_allowed_outside_content_dir(client, tmp_path):
    shared = tmp_path / "shared" / "ad 1.mp4"
    _touch(str(shared), b"ad")
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT INTO catalog_entries (station, path, title, duration, tag, count, hints)"
                     " VALUES ('Toons', ?, 'ad', 15, '/shared', 0, '[]')", (str(shared),))
    assert client.get("/client/media", params={"path": str(shared)}).status_code == 200
    assert client.get("/client/media", params={"path": str(tmp_path / "shared" / "other.mp4")}).status_code == 403


def test_media_requests_skip_manifest_and_version_work(client, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("tune path built the manifest")

    monkeypatch.setattr(client_api, "file_manifest", boom)
    monkeypatch.setattr(client_api, "compute_version", boom)
    assert client.get("/client/media", params={"path": SHOW}).status_code == 200


def test_conf_change_also_reloads_the_schedule_cache(client, monkeypatch):
    reloads = []
    monkeypatch.setattr(client_api, "LiquidManager", lambda: type("L", (), {"reload_schedules": lambda self: reloads.append(1)})())
    client.get("/client/version")
    assert reloads == [1]


AUTOBUMP = (":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=Panda&subtitle=A%20seguir%20na%20Panda"
            "&next_network=Toons&duration=7000&countdown=false")
MESSAGE = ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=Panda&duration=7000&countdown=false"


def _rendered(job):
    _touch(job.path, b"mp4")
    return job


def test_rundown_swaps_rendered_autobump(client):
    from server.bumps.jobs import job_for

    now = _now()
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "A", plan_path=MESSAGE)
    job = _rendered(job_for(MESSAGE))
    entry = client.get("/client/rundown").json()["stations"]["Toons"][0]["plan"][0]
    assert entry["path"] == job.path and entry["content_type"] == "bump" and "loop" not in entry


def test_rundown_keeps_unrendered_autobump(client):
    now = _now()
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "A", plan_path=MESSAGE)
    assert client.get("/client/rundown").json()["stations"]["Toons"][0]["plan"][0]["path"] == MESSAGE


def test_next_up_swaps_with_the_following_show(client):
    from server.bumps.jobs import job_for

    now = _now()
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "A", plan_path=AUTOBUMP)
    _insert_block(now + datetime.timedelta(minutes=20), now + datetime.timedelta(minutes=50), "Bluey")
    job = _rendered(job_for(AUTOBUMP, "Bluey"))
    assert client.get("/client/rundown").json()["stations"]["Toons"][0]["plan"][0]["path"] == job.path


def test_next_up_at_window_end_is_kept(client):
    now = _now()
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "A", plan_path=AUTOBUMP)
    assert client.get("/client/rundown").json()["stations"]["Toons"][0]["plan"][0]["path"] == AUTOBUMP


def test_version_changes_when_a_bump_is_rendered(client):
    before = client.get("/client/version").json()["version"]
    _touch("runtime/bumps/abc.mp4", b"mp4")
    assert client.get("/client/version").json()["version"] != before


def test_bad_autobump_never_breaks_the_rundown(client):
    now = _now()
    odd = MESSAGE.replace("duration=7000", "duration=not-a-number")
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "A", plan_path=odd)
    response = client.get("/client/rundown")
    assert response.status_code == 200 and response.json()["stations"]["Toons"][0]["plan"][0]["path"] == odd


def test_mid_show_next_up_names_the_show_that_resumes(client):
    from server.bumps.jobs import job_for

    now = _now()
    plan = [{"path": SHOW, "skip": 0, "duration": 600, "is_stream": False, "content_type": "feature", "media_type": "video"},
            {"path": AUTOBUMP, "skip": 0, "duration": 7, "is_stream": False, "content_type": "bump", "media_type": "video"},
            {"path": SHOW, "skip": 600, "duration": 600, "is_stream": False, "content_type": "feature", "media_type": "video"}]
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT INTO liquid_blocks (station, liquid_type, start_time, end_time, break_strategy, title,"
                     " sequence_key, break_info, content_json, plan_json) VALUES ('Toons', 'LiquidBlock', ?, ?, 'standard',"
                     " 'A', NULL, NULL, '1', ?)", (str(now - datetime.timedelta(minutes=5)), str(now + datetime.timedelta(minutes=20)), json.dumps(plan)))
    _insert_block(now + datetime.timedelta(minutes=20), now + datetime.timedelta(minutes=50), "Peppa")
    resumes = _rendered(job_for(AUTOBUMP, "A"))
    _rendered(job_for(AUTOBUMP, "Peppa"))
    assert client.get("/client/rundown").json()["stations"]["Toons"][0]["plan"][1]["path"] == resumes.path


def test_a_client_gets_bumps_in_its_osd_style(client):
    from server.bumps.jobs import job_for
    from server.bumps.styles import styles_in_use

    now = _now()
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "A", plan_path=MESSAGE)
    station, cable = _rendered(job_for(MESSAGE)), _rendered(job_for(MESSAGE, style="cable"))
    plan = lambda query: client.get("/client/rundown" + query).json()["stations"]["Toons"][0]["plan"][0]["path"]
    assert plan("?osd_style=cable") == cable.path
    assert plan("") == station.path
    assert plan("?osd_style=neon") == station.path  # unknown: the station's look
    assert "cable" in styles_in_use()


def test_a_style_not_rendered_yet_leaves_the_autobump_for_the_client(client):
    now = _now()
    _insert_block(now - datetime.timedelta(minutes=10), now + datetime.timedelta(minutes=20), "A", plan_path=MESSAGE)
    assert client.get("/client/rundown?osd_style=kids").json()["stations"]["Toons"][0]["plan"][0]["path"] == MESSAGE
