from types import SimpleNamespace

import pytest

from client.platform import volume


@pytest.mark.parametrize("tool, output, muted", [
    ("pactl", "Mute: yes", True), ("pactl", "Mute: no", False),
    ("amixer", "Front Left: Playback 52 [80%] [-5.00dB] [off]", True),
    ("amixer", "Front Left: Playback 52 [80%] [-5.00dB] [on]", False),
    ("wpctl", "Volume: 0.80 [MUTED]", True), ("wpctl", "Volume: 0.80", False),
])
def test_the_mute_state_is_read_from_whichever_mixer_answers(monkeypatch, tool, output, muted):
    monkeypatch.setattr(volume.shutil, "which", lambda name: name == tool)
    monkeypatch.setattr(volume.subprocess, "run",
                        lambda cmd, **kw: SimpleNamespace(stdout=output, returncode=0))
    assert volume.current_mute_state() is muted


def test_no_mixer_means_unknown(monkeypatch):
    monkeypatch.setattr(volume.shutil, "which", lambda name: False)
    assert volume.current_mute_state() is None
