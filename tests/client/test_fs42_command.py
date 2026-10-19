import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).parents[2]
FS42 = ROOT / "client/platform/fs42"


@pytest.fixture
def run(tmp_path):
    # a fake docker that records how it was called and with which environment
    calls = tmp_path / "calls"
    fake = tmp_path / "bin/docker"
    fake.parent.mkdir()
    fake.write_text(f'#!/bin/sh\necho "$* | window=$FS42_WINDOW | pulse=$PULSE_SOCKET" >> {calls}\n')
    fake.chmod(0o755)
    # called through a symlink, as from ~/.local/bin
    link = tmp_path / "bin/fs42"
    link.symlink_to(FS42)

    def fs42(*args, env=None):
        environment = {"PATH": f"{fake.parent}:/usr/bin:/bin", "HOME": str(tmp_path), **(env or {})}
        result = subprocess.run([str(link), *args], env=environment, capture_output=True, text=True)
        return result, calls.read_text().splitlines() if calls.exists() else []

    return fs42


def test_start_runs_the_tv_fullscreen(run):
    result, calls = run("start")
    assert result.returncode == 0
    assert calls == [f"compose -f {ROOT}/client/compose.yml up -d | window= | pulse="]


def test_start_windowed_plays_in_a_1280x720_window(run):
    _, calls = run("start", "--windowed")
    assert calls[0].endswith("| window=1280x720 | pulse=")


def test_start_windowed_takes_a_size(run):
    _, calls = run("start", "--windowed", "960x540")
    assert "| window=960x540 |" in calls[0]


def test_kill_stops_only_the_client(run):
    _, calls = run("kill")
    assert calls == [f"compose -f {ROOT}/client/compose.yml down | window= | pulse="]


def test_sound_setting_from_the_environment_is_kept(run):
    _, calls = run("start", env={"PULSE_SOCKET": "/run/user/1000/pulse/native"})
    assert calls[0].endswith("| pulse=/run/user/1000/pulse/native")


def test_anything_else_shows_how_to_use_it(run):
    result, calls = run("restart-the-universe")
    assert result.returncode != 0 and "fs42 start" in result.stderr and calls == []
