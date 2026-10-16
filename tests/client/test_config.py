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
    assert config == {"server_url": "http://homelab:4242", "media": {"method": "http"}, "main_config": {}}


def test_load_client_config_keeps_given_media_and_overrides(tmp_path):
    data = {"server_url": "http://h:4242", "media": {"method": "mount", "root": "/mnt/fs42"},
            "main_config": {"start_channel": 3}}
    assert load_client_config(_write(tmp_path, data)) == data


def test_load_client_config_without_server_url_raises(tmp_path):
    with pytest.raises(ValueError):
        load_client_config(_write(tmp_path, {}))


def test_missing_client_json_exits_with_a_clear_message(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        load_client_config(str(tmp_path / "client.json"))
    assert "run client/platform/install.sh or copy client.example.json" in str(exit_info.value)


def test_prepare_station_loading_turns_off_media_checks(monkeypatch):
    monkeypatch.setattr(StationIO, "check_media", True)
    prepare_station_loading()
    assert StationIO.check_media is False
