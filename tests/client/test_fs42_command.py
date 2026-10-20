import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).parents[2]
FS42 = ROOT / "client/platform/fs42"


def _client_copy(tmp_path):
    # the script in a client folder of its own, so this machine's local files don't leak in
    client = tmp_path / "repo/client"
    (client / "platform").mkdir(parents=True)
    (client / "platform/fs42").write_text(FS42.read_text())
    (client / "platform/fs42").chmod(0o755)
    (client / "compose.yml").write_text("services: {}\n")
    return client


@pytest.fixture
def client(tmp_path):
    return _client_copy(tmp_path)


@pytest.fixture
def run(tmp_path, client):
    # a fake docker that records how it was called and with which environment
    calls = tmp_path / "calls"
    fake = tmp_path / "bin/docker"
    fake.parent.mkdir()
    fake.write_text(f'#!/bin/sh\necho "$* | window=$FS42_WINDOW | pulse=$PULSE_SOCKET | look=$FS42_LOOK" >> {calls}\n')
    fake.chmod(0o755)
    # called through a symlink, as from ~/.local/bin
    link = tmp_path / "bin/fs42"
    link.symlink_to(client / "platform/fs42")

    def fs42(*args, env=None):
        environment = {"PATH": f"{fake.parent}:/usr/bin:/bin", "HOME": str(tmp_path), **(env or {})}
        result = subprocess.run([str(link), *args], env=environment, capture_output=True, text=True)
        return result, calls.read_text().splitlines() if calls.exists() else []

    return fs42


def test_start_runs_the_tv_fullscreen(run, client):
    result, calls = run("start")
    assert result.returncode == 0
    assert calls == [f"compose -f {client}/compose.yml up -d | window= | pulse= | look="]


def test_start_windowed_plays_in_a_1280x720_window(run):
    _, calls = run("start", "--windowed")
    assert calls[0].endswith("| window=1280x720 | pulse= | look=")


def test_start_windowed_takes_a_size(run):
    _, calls = run("start", "--windowed", "960x540")
    assert "| window=960x540 |" in calls[0]


def test_kill_stops_only_the_client(run, client):
    _, calls = run("kill")
    assert calls == [f"compose -f {client}/compose.yml down | window= | pulse= | look="]


def test_sound_setting_from_the_environment_is_kept(run):
    _, calls = run("start", env={"PULSE_SOCKET": "/run/user/1000/pulse/native"})
    assert "| pulse=/run/user/1000/pulse/native |" in calls[0]


def test_anything_else_shows_how_to_use_it(run):
    result, calls = run("restart-the-universe")
    assert result.returncode != 0 and "fs42 start" in result.stderr and calls == []


def test_a_local_override_file_is_added_when_present(run, client):
    # client/compose.override.yml holds this machine's own settings (e.g. WSL's GPU), outside git
    (client / "compose.override.yml").write_text("services: {}\n")
    _, calls = run("start")
    assert calls[0].startswith(f"compose -f {client}/compose.yml -f {client}/compose.override.yml up -d")


def test_start_with_a_look(run):
    _, calls = run("start", "--look", "crt")
    assert calls[0].endswith("| window= | pulse= | look=crt")


def test_look_and_window_in_any_order(run):
    _, first = run("start", "--look", "original", "--windowed", "960x540")
    assert first[0].endswith("| window=960x540 | pulse= | look=original")
    _, both = run("start", "--windowed", "--look", "broadcast")
    assert both[1].endswith("| window=1280x720 | pulse= | look=broadcast")


def test_an_unknown_start_option_is_refused(run):
    result, calls = run("start", "--loook", "crt")
    assert result.returncode != 0 and calls == []
