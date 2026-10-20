import json

import pytest

from client.playback.config import load_client_config, prepare_station_loading
from shared.stations.io import StationIO


def _write(tmp_path, data):
    path = tmp_path / "client.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_load_client_config_applies_defaults_and_strips_slash(tmp_path):
    config = load_client_config(_write(tmp_path, {"server_url": "http://homelab:4242/"}))
    assert config == {"server_url": "http://homelab:4242", "media": {"method": "http"}, "main_config": {},
                      "local_api_port": None, "web_pages": False, "hwdec": "auto-safe", "look": "broadcast",
                      "osd_style": "vcr"}


def test_load_client_config_keeps_given_media_and_overrides(tmp_path):
    data = {"server_url": "http://h:4242", "media": {"method": "mount", "root": "/mnt/fs42"},
            "main_config": {"start_channel": 3}}
    assert load_client_config(_write(tmp_path, data)) == dict(data, local_api_port=None, web_pages=False,
                                                                 hwdec="auto-safe", look="broadcast",
                                                                 osd_style="vcr")


def test_load_client_config_without_server_url_raises(tmp_path):
    with pytest.raises(ValueError):
        load_client_config(_write(tmp_path, {}))


def test_missing_client_json_exits_with_a_clear_message(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        load_client_config(str(tmp_path / "client.json"))
    assert "run client/platform/install.sh or copy client.example.json" in str(exit_info.value)


def test_prepare_station_loading_turns_off_media_checks(monkeypatch):
    monkeypatch.setattr(StationIO, "check_media", True)
    prepare_station_loading({"web_pages": False})
    assert StationIO.check_media is False


def test_client_json_that_is_a_directory_exits_with_a_clear_message(tmp_path):
    (tmp_path / "client.json").mkdir()  # what a Docker bind mount of a missing file leaves behind
    with pytest.raises(SystemExit) as exit_info:
        load_client_config(str(tmp_path / "client.json"))
    assert "is a directory" in str(exit_info.value) and "client.example.json" in str(exit_info.value)


def test_local_api_port_defaults_to_none(tmp_path):
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242"}))["local_api_port"] is None


def test_web_pages_default_off(tmp_path):
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242"}))["web_pages"] is False


def _station_files(tmp_path):
    confs = tmp_path / "confs"
    confs.mkdir()
    (confs / "web.json").write_text(json.dumps({"station_conf": {
        "network_name": "Weather", "channel_number": 9, "network_type": "web", "web_url": "http://localhost:4242/x"}}))
    (confs / "loop.json").write_text(json.dumps({"station_conf": {
        "network_name": "Loop", "channel_number": 2, "network_type": "loop", "content_dir": "catalog/loop"}}))
    return tmp_path


def _loaded_station_names(tmp_path, monkeypatch, web_pages):
    from shared.stations.manager import StationManager

    monkeypatch.chdir(_station_files(tmp_path))
    StationManager._StationManager__we_are_all_one = {}
    StationManager._initialized = False
    StationManager.stations = []
    monkeypatch.setattr(StationIO, "check_media", True)
    monkeypatch.setattr(StationIO, "excluded_types", set())
    prepare_station_loading({"web_pages": web_pages})
    try:
        return [s["network_name"] for s in StationManager().stations]
    finally:
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []


def test_web_stations_left_out_when_web_pages_off(tmp_path, monkeypatch):
    assert _loaded_station_names(tmp_path, monkeypatch, False) == ["Loop"]


def test_web_stations_kept_when_web_pages_on(tmp_path, monkeypatch):
    assert _loaded_station_names(tmp_path, monkeypatch, True) == ["Loop", "Weather"]


def test_the_look_is_retro_broadcast_unless_chosen(tmp_path, monkeypatch):
    monkeypatch.delenv("FS42_LOOK", raising=False)
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242"}))["look"] == "broadcast"
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242", "look": "crt"}))["look"] == "crt"


def test_fs42_start_look_wins_over_client_json(tmp_path, monkeypatch):
    monkeypatch.setenv("FS42_LOOK", "original")
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242", "look": "crt"}))["look"] == "original"


def test_an_unknown_look_says_which_exist(tmp_path, monkeypatch):
    monkeypatch.delenv("FS42_LOOK", raising=False)
    with pytest.raises(SystemExit, match="original, broadcast, crt"):
        load_client_config(_write(tmp_path, {"server_url": "http://h:4242", "look": "vhs"}))


def test_the_osd_style_is_vcr_unless_chosen(tmp_path, monkeypatch):
    monkeypatch.delenv("FS42_OSD", raising=False)
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242"}))["osd_style"] == "vcr"
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242", "osd_style": "kids"}))["osd_style"] == "kids"
    monkeypatch.setenv("FS42_OSD", "cable")
    assert load_client_config(_write(tmp_path, {"server_url": "http://h:4242", "osd_style": "kids"}))["osd_style"] == "cable"


def test_an_unknown_osd_style_says_which_exist(tmp_path, monkeypatch):
    monkeypatch.delenv("FS42_OSD", raising=False)
    with pytest.raises(SystemExit, match="vcr, cable, kids"):
        load_client_config(_write(tmp_path, {"server_url": "http://h:4242", "osd_style": "neon"}))
