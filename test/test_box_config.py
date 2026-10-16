import json

import pytest

from fs42.box.config import is_box, load_box_config


def _write(tmp_path, data):
    path = tmp_path / "box.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_load_box_config_applies_defaults_and_strips_slash(tmp_path):
    config = load_box_config(_write(tmp_path, {"server_url": "http://homelab:4242/"}))
    assert config == {"server_url": "http://homelab:4242", "media": {"method": "http"}, "main_config": {}}


def test_load_box_config_keeps_given_media_and_overrides(tmp_path):
    data = {"server_url": "http://h:4242", "media": {"method": "mount", "root": "/mnt/fs42"},
            "main_config": {"start_channel": 3}}
    assert load_box_config(_write(tmp_path, data)) == data


def test_load_box_config_without_server_url_raises(tmp_path):
    with pytest.raises(ValueError):
        load_box_config(_write(tmp_path, {}))


def test_is_box_follows_box_json_in_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not is_box()
    _write(tmp_path, {"server_url": "http://h:4242"})
    assert is_box()
