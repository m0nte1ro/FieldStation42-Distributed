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
    # background videos often have no sound; check before relying on it
    probe: bool = False


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
        return AudioSource(_local(params["bg_video"], static_dir), False, 1.0, probe=True)
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
        audio_filter = f"apad,volume={audio.volume}"
        if not job.loop:
            # loops play back to back, so only a one-off bump fades out
            audio_filter += f",afade=t=out:st={max(job.seconds - FADE_SECONDS, 0):.3f}:d={FADE_SECONDS}"
        cmd += ["-filter:a", audio_filter]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", out]
    return cmd


def has_audio(path, run=subprocess.run):
    try:
        probe = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                     "-of", "csv=p=0", path], capture_output=True, text=True)
    except Exception:
        return False
    return bool((probe.stdout or "").strip())


# settled: the fonts are in and the entrance animations (fadeInUp) have finished
SETTLED_JS = "Promise.all([document.fonts.ready, ...document.getAnimations().map(a => a.finished)])"


def record_page(url, seconds, workdir, settle=False):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # no sandbox: it can't run in an unprivileged LXC, and the page is our own
        browser = pw.chromium.launch(args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        size = {"width": WIDTH, "height": HEIGHT}
        context = browser.new_context(viewport=size, record_video_dir=workdir, record_video_size=size)
        started = time.monotonic()
        page = context.new_page()
        page.goto(url, wait_until="load")
        if settle:
            # a loop starts from the finished page, or every pass would replay the entrance
            page.evaluate(SETTLED_JS)
        # the recording starts with the blank page; ffmpeg trims everything before this point
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
        recording, trim = record(url, job.seconds, workdir, settle=True) if job.loop else record(url, job.seconds, workdir)
        audio = audio_source(job.params)
        if audio and audio.probe and not has_audio(audio.path, run):
            audio = None
        try:
            run(ffmpeg_command(recording, trim, job, audio, partial), check=True, capture_output=True)
            os.replace(partial, job.path)
        finally:
            if os.path.exists(partial):
                os.remove(partial)
    return job.path
