import asyncio
from types import SimpleNamespace

import pytest

from client.platform import volume


@pytest.fixture
def ran(monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout="Volume: front-left: 32768 /  50% / -18 dB [50%] [on] Mute: no", stderr="")

    monkeypatch.setattr(volume.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("backend, unmute", [
    (volume._volume_pulseaudio, ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"]),
    (volume._volume_amixer, ["amixer", "sset", "Master", "unmute"]),
    (volume._volume_wireplumber, ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"]),
])
@pytest.mark.parametrize("action", ["up", "down"])
def test_changing_the_volume_unmutes_like_a_tv(ran, backend, unmute, action):
    asyncio.run(backend(action))
    assert unmute in ran


def test_mute_still_toggles(ran):
    asyncio.run(volume._volume_pulseaudio("mute"))
    assert ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"] in ran
    assert ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"] not in ran
