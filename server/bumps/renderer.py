import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlencode, urlsplit

from server.bumps.jobs import BUMP_DIR

STATIC_DIR = "server/api/static"
WIDTH, HEIGHT, FPS = 1280, 720, 30
MUSIC_VOLUME = 0.3  # what the bump page plays its music at
FADE_SECONDS = 1


@dataclass
class AudioSource:
    path: str
    loop: bool
    volume: float


def _local(url, static_dir):
    # our own static files are read from disk, anything else is fetched by ffmpeg
    parts = urlsplit(url)
    ours = parts.hostname in (None, "127.0.0.1", "localhost")
    if ours and parts.path.startswith("/static/"):
        return os.path.join(static_dir, unquote(parts.path[len("/static/"):]))
    return url


def audio_source(params, static_dir=STATIC_DIR):
    # the page plays bg_music (and mutes the video then), else the background video's own sound
    if params.get("bg_music"):
        return AudioSource(_local(params["bg_music"], static_dir), params.get("loopmusic") != "false", MUSIC_VOLUME)
    if params.get("bg_video") and params.get("bg_video_audio") != "false":
        return AudioSource(_local(params["bg_video"], static_dir), False, 1.0)
    return None


def ffmpeg_command(recording, trim, job, audio, out):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{trim:.3f}", "-i", recording]
    if audio:
        cmd += (["-stream_loop", "-1"] if audio.loop else []) + ["-i", audio.path]
    else:
        # a silent track, so players treat it like any other bump
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    cmd += ["-map", "0:v:0", "-map", "1:a:0", "-t", f"{job.seconds:.3f}",
            # pad with the last frame and silence, then -t cuts every clip to exactly its length
            "-vf", f"scale={WIDTH}:{HEIGHT},fps={FPS},tpad=stop_mode=clone:stop_duration={job.seconds:.3f},format=yuv420p"]
    if audio:
        fade_start = max(job.seconds - FADE_SECONDS, 0)
        cmd += ["-filter:a", f"apad,volume={audio.volume},afade=t=out:st={fade_start:.3f}:d={FADE_SECONDS}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", out]
    return cmd


def record_page(url, seconds, workdir):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # no sandbox: it can't run in an unprivileged LXC, and the page is our own
        browser = pw.chromium.launch(args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        size = {"width": WIDTH, "height": HEIGHT}
        context = browser.new_context(viewport=size, record_video_dir=workdir, record_video_size=size)
        started = time.monotonic()
        page = context.new_page()
        page.goto(url, wait_until="load")
        # the recording starts with the blank page; ffmpeg trims everything before the load
        trim = time.monotonic() - started
        page.wait_for_timeout(seconds * 1000 + 300)
        video = page.video
        context.close()
        path = video.path()
        browser.close()
    return path, trim


def render(job, base_url, run=subprocess.run, record=record_page):
    url = f"{base_url}/static/bump/bump.html?{urlencode(job.params, quote_via=quote)}"
    os.makedirs(BUMP_DIR, exist_ok=True)
    partial = f"{job.path}.tmp.mp4"
    with tempfile.TemporaryDirectory() as workdir:
        recording, trim = record(url, job.seconds, workdir)
        try:
            run(ffmpeg_command(recording, trim, job, audio_source(job.params), partial), check=True, capture_output=True)
            os.replace(partial, job.path)
        finally:
            if os.path.exists(partial):
                os.remove(partial)
    return job.path
