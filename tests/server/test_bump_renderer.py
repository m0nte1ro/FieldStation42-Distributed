import os
import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from server.bumps.jobs import RenderJob  # noqa: E402
from server.bumps.renderer import AudioSource, audio_source, ffmpeg_command, render  # noqa: E402

JOB = RenderJob("message", "abc123", {"title": "Panda", "duration": "7000"}, 7.0)


def _arg_after(cmd, flag, nth=0):
    hits = [i for i, part in enumerate(cmd) if part == flag]
    return cmd[hits[nth] + 1]


def test_command_with_music():
    cmd = ffmpeg_command("rec.webm", 0.8, JOB, AudioSource("server/api/static/bump/music/logo0.mp3", False, 0.3), "out.mp4")
    assert _arg_after(cmd, "-ss") == "0.800" and _arg_after(cmd, "-i", 1) == "server/api/static/bump/music/logo0.mp3"
    assert "-stream_loop" not in cmd and _arg_after(cmd, "-t") == "7.000" and cmd[-1] == "out.mp4"
    audio_filter = _arg_after(cmd, "-filter:a")
    assert "volume=0.3" in audio_filter and "afade=t=out:st=6.000:d=1" in audio_filter
    assert {"libx264", "aac", "+faststart", "yuv420p"} <= set(" ".join(cmd).replace(",", " ").replace("=", " ").split())


def test_command_loops_music_when_asked():
    cmd = ffmpeg_command("rec.webm", 0.5, JOB, AudioSource("music.mp3", True, 0.3), "out.mp4")
    assert cmd[cmd.index("-stream_loop") + 2: cmd.index("-stream_loop") + 4] == ["-i", "music.mp3"]


def test_command_silent_bump_gets_silent_track():
    cmd = ffmpeg_command("rec.webm", 0.5, JOB, None, "out.mp4")
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in cmd and "-filter:a" not in cmd


def test_music_on_our_server_maps_to_static_file():
    source = audio_source({"bg_music": "http://127.0.0.1:4242/static/bump/music/logo%201.mp3", "loopmusic": "true"})
    assert source == AudioSource("server/api/static/bump/music/logo 1.mp3", True, 0.3)


def test_external_music_passes_through():
    assert audio_source({"bg_music": "https://example.com/a.mp3", "loopmusic": "false"}).path == "https://example.com/a.mp3"


def test_command_uses_bg_video_audio():
    source = audio_source({"bg_video": "http://127.0.0.1:4242/static/bump/video/intro.webm"})
    assert source == AudioSource("server/api/static/bump/video/intro.webm", False, 1.0, probe=True)
    assert audio_source({"bg_video": "intro.webm", "bg_video_audio": "false"}) is None
    assert audio_source({"title": "x"}) is None


def _fake_record(url, seconds, workdir):
    path = os.path.join(workdir, "page.webm")
    open(path, "wb").close()
    _fake_record.url = url
    return path, 0.6


def _ffmpeg_writes_output(cmd, **kwargs):
    with open(cmd[-1], "wb") as f:
        f.write(b"mp4")


def test_render_writes_atomically_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert render(JOB, "http://127.0.0.1:4242", run=_ffmpeg_writes_output, record=_fake_record) == JOB.path
    assert open(JOB.path, "rb").read() == b"mp4" and os.listdir("runtime/bumps") == ["abc123.mp4"]
    assert _fake_record.url == "http://127.0.0.1:4242/static/bump/bump.html?title=Panda&duration=7000"


def test_failed_ffmpeg_leaves_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fails(cmd, **kwargs):
        open(cmd[-1], "wb").close()
        raise RuntimeError("ffmpeg failed")

    with pytest.raises(RuntimeError):
        render(JOB, "http://127.0.0.1:4242", run=fails, record=_fake_record)
    assert os.listdir("runtime/bumps") == []


def test_output_is_padded_to_the_exact_length():
    # a recording or a song shorter than the bump must not shorten the clip
    cmd = ffmpeg_command("rec.webm", 0.5, JOB, AudioSource("music.mp3", False, 0.3), "out.mp4")
    assert "tpad=stop_mode=clone:stop_duration=7.000" in _arg_after(cmd, "-vf")
    assert _arg_after(cmd, "-filter:a").startswith("apad,")
    silent = ffmpeg_command("rec.webm", 0.5, JOB, None, "out.mp4")
    assert "tpad=stop_mode=clone:stop_duration=7.000" in _arg_after(silent, "-vf")


def test_loop_clips_do_not_fade_out():
    loop_job = RenderJob("filler", "loop1", {"duration": "0"}, 30.0, loop=True, countdown=True)
    cmd = ffmpeg_command("rec.webm", 0.5, loop_job, AudioSource("music.mp3", False, 0.3), "out.mp4")
    assert "afade" not in _arg_after(cmd, "-filter:a")


def test_background_video_without_sound_renders_with_silence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job = RenderJob("message", "vid1", {"bg_video": "http://127.0.0.1:4242/static/bump/video/silent.mp4"}, 7.0)
    commands = []

    def run(cmd, **kwargs):
        commands.append(cmd)
        if cmd[0] == "ffprobe":
            return MagicMock(stdout="")  # no audio stream
        open(cmd[-1], "wb").close()

    render(job, "http://127.0.0.1:4242", run=run, record=_fake_record)
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in commands[-1]


def test_a_loop_starts_once_the_page_has_settled(tmp_path, monkeypatch):
    # a filler repeats every 30 s: starting on the page's entrance animation would replay it each time
    monkeypatch.chdir(tmp_path)
    settled = []

    def record(url, seconds, workdir, settle=False):
        settled.append(settle)
        return _fake_record(url, seconds, workdir)

    loop_job = RenderJob("filler", "loop2", {"duration": "0"}, 30.0, loop=True, countdown=True)
    render(loop_job, "http://127.0.0.1:4242", run=_ffmpeg_writes_output, record=record)
    render(JOB, "http://127.0.0.1:4242", run=_ffmpeg_writes_output, record=record)
    assert settled == [True, False]
