# Server-rendered Autobumps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The server renders autobumps to cached MP4s that clients play as ordinary video; clients carry no Chromium by default; one dev container runs both ends.

**Architecture:** `server/bumps/` turns `:autobump:=` URLs into render jobs, renders them with Playwright + ffmpeg in a background keeper, and the rundown export swaps rendered clips in. Plan entries gain `loop`/`countdown`; the client loops fillers and draws the countdown with mpv. `web_pages` in `client.json` (default off) removes web stations and the live autobump fallback.

**Tech Stack:** Python 3.11/3.12, Playwright (Chromium), ffmpeg/libx264, mpv, FastAPI, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-19-server-rendered-autobumps.md`

## Global Constraints

- Chromium and QtWebEngine never enter the client image unless built with `--build-arg WEB_PAGES=true`.
- Stored plans don't change: `BlockPlanEntry.toJSON()` writes `loop`/`countdown` only when true.
- The ends still never import each other (`tests/test_layout.py`).
- Renders: 1280×720, 30 fps, H.264 `yuv420p` + AAC, `-movflags +faststart`, `runtime/bumps/<key>.mp4`, atomic write; fillers 30 s.
- The keeper scans every 300 s, 24 h ahead, renders one job at a time, never crashes on a failed render.
- Full suite green after every task: `env/bin/pytest -q -p no:cacheprovider tests`.
- No AI attribution anywhere.

## Review Focus

1. A station whose autobump config has no `bg_music` and no `bg_video` (silent bump): render must still produce a valid MP4 (add a silent audio track so players don't stall). Test in Task 3.
2. A `next_up` bump at the end of the 24 h window (no following block): left as the live URL, never rendered with an empty title. Test in Task 2.
3. Show titles with quotes, `&`, `#` or non-ASCII must survive into `next_title` and the cache key. Test in Task 2.
4. A client with `web_pages` off and a rundown that still contains an unrendered autobump: standby for exactly the bump's length, no browser. Test in Task 1.
5. Two keeper scans while a render is still running must not render the same job twice. Test in Task 4.

---

### Task 1: Client — loop, countdown, `web_pages`, browser-free requirements

**Files:** `shared/rundown.py`, `client/playback/player.py`, `client/playback/config.py`, `shared/stations/io.py`, `client/requirements.txt`, `client/requirements-web.txt`, `client/Dockerfile`, `client/platform/install.sh`, `client.example.json`; tests in `tests/client/`, `tests/shared/`.

**Interfaces:**
- Produces:
  - `BlockPlanEntry(..., loop=False, countdown=False)`, with `toJSON()` adding `"loop": true` / `"countdown": true` only when set;
  - `decode_block` reads them with default `False`;
  - `load_client_config` sets a default of `web_pages=False`;
  - `prepare_station_loading(config)` sets `StationIO.excluded_types = set() if config["web_pages"] else {"web"}` (`StationIO` skips those network types when loading);
  - the player passes `loop` to `play_file(..., loop=False)`, which sends `mpv.command("set", "loop-file", "inf" if loop else "no")` before loading.
  - Countdown entries: the wait loop calls `mpv.command("show-text", f"{m}:{s:02d}", 1100)` once per second, from the remaining gap.
  - An autobump with `web_pages` off: `play_file` plays the station's `standby_image` (or `runtime/standby.png`) and returns True. It's timed by the wait loop as any entry.
  - `show_web` with no QtWebEngine shows standby and returns `PlayerOutcome(PlayerState.SUCCESS)`.

- [ ] Tests first:
  - `test_plan_entry_json_unchanged_without_loop`;
  - `test_loop_and_countdown_round_trip`;
  - `test_loop_entry_sets_loop_file`;
  - `test_other_entries_reset_loop_file`;
  - `test_countdown_entry_shows_remaining_gap` (FakeMPV, entry 3 s, assert `show-text` with `0:02` or `0:03`);
  - `test_web_stations_left_out_when_web_pages_off`;
  - `test_web_stations_kept_when_web_pages_on`;
  - `test_unrendered_autobump_shows_standby_without_web_pages`;
  - `test_missing_webengine_shows_standby_instead_of_exiting`.

  Run them and watch them fail.
- [ ] Implement.
- [ ] `client/requirements.txt`: replace `PySide6>=6.8` with `PySide6-Essentials>=6.8`. `client/requirements-web.txt`: `PySide6-Addons>=6.8`.
- [ ] `client/Dockerfile`: `ARG WEB_PAGES=false`; install `requirements-web.txt` only when it is `true`.
- [ ] `install.sh`: ask "Enable web channels and live autobumps? (y/N)"; on yes, install the extra and write `"web_pages": true`.
- [ ] Suite green.
- [ ] Commit `feat: clients play bump loops with a countdown and need no browser by default`.

### Task 2: Render jobs and the rundown swap

**Files:** create `server/bumps/__init__.py`, `server/bumps/jobs.py`; modify `server/api/rundown_export.py`, `server/api/static/bump/bump.js`; tests `tests/server/test_bump_jobs.py`.

**Interfaces:**
- Produces in `server/bumps/jobs.py`:
  - `BUMP_DIR = "runtime/bumps"`;
  - a `RenderJob` dataclass with `kind`, `key`, `params` (`dict[str, str]`), `seconds`, `loop`, `countdown`, and the `path` property `f"{BUMP_DIR}/{key}.mp4"`;
  - `job_for(entry_path: str, next_title: str | None) -> RenderJob | None`. It returns `None` for non-autobump paths, and for `next_up` with no `next_title`.
  - Rules: `countdown=true` makes a `filler` (`seconds=30`, params `countdown=false`, `duration=30000`, `loop`/`countdown` true). `next_network` present makes a `next_up` (params minus `next_network`, plus `next_title`). Anything else is a `message`. `seconds = int(params["duration"]) / 1000` (default 7). `key = sha1(kind + json.dumps(sorted params))[:16]`.
- `rundown_export.build_rundown`: for each block, `next_title` is the next block's title in that station's list. Entries whose job file exists are swapped as the spec says.
- `bump.js`: `nextTitle: params.get('next_title')`. When set, show it as the single detail line and skip the schedule fetch.
- `autobump_agent.next_up_bump`: the subtitle is `ab_config.get("next_up_text", "Coming up on {network}").format(network=network_name)` (test `test_next_up_text_is_configurable`).

- [ ] Tests first:
  - `test_message_bump_job`;
  - `test_identical_bumps_share_a_key`;
  - `test_next_up_job_uses_next_title_and_drops_network`;
  - `test_next_up_without_next_title_is_not_rendered`;
  - `test_different_titles_get_different_keys`;
  - `test_awkward_titles_survive` (`"Tom & Jerry's #1 «Ação»"`);
  - `test_filler_job_is_a_30s_loop_with_countdown`;
  - `test_non_autobump_paths_have_no_job`;
  - `test_rundown_swaps_rendered_autobump`;
  - `test_rundown_keeps_unrendered_autobump`;
  - `test_next_up_at_window_end_is_kept`.
- [ ] Implement.
- [ ] Suite green.
- [ ] Commit `feat: work out autobump render jobs and swap rendered clips into rundowns`.

### Task 3: The renderer

**Files:** create `server/bumps/renderer.py`; modify `server/requirements.txt` (`playwright`), `server/Dockerfile` (`playwright install --with-deps chromium`), `compose.yml` (`shm_size: 1gb`); tests `tests/server/test_bump_renderer.py`.

**Interfaces:**
- `ffmpeg_command(recording: str, trim: float, job: RenderJob, audio: str | None, audio_loop: bool, out: str) -> list[str]`:
  - `-ss <trim> -t <seconds>` on the recording;
  - audio from the file (with `-stream_loop -1` when looping), or `anullsrc` when there is none;
  - `-shortest` is not used, so the output is exactly `-t <seconds>`.
- `audio_source(params: dict, static_dir: str = "server/api/static") -> tuple[str | None, bool]`:
  - `bg_music` URLs on our server map to `server/api/static/bump/music/<file>`, and external http URLs pass through;
  - otherwise the `bg_video` file, unless `bg_video_audio == "false"`.
- `render(job: RenderJob, base_url: str, run=subprocess.run, browser_factory=None) -> str`: Playwright records into a temporary directory, measures the load delay as `trim`, runs ffmpeg into `<path>.tmp.mp4`, then `os.replace` to `job.path`. It returns the path.

- [ ] Tests first, with a fake browser and a fake runner:
  - `test_command_with_music`;
  - `test_command_loops_music_when_asked`;
  - `test_command_silent_bump_gets_silent_track`;
  - `test_command_uses_bg_video_audio`;
  - `test_music_on_our_server_maps_to_static_file`;
  - `test_render_writes_atomically_and_returns_path`;
  - `test_failed_ffmpeg_leaves_no_file`.
- [ ] Implement, then the Dockerfile and compose changes.
- [ ] Suite green.
- [ ] Commit `feat: render autobump pages to MP4 on the server`.

### Task 4: The keeper

**Files:** create `server/bumps/keeper.py`; modify `server/api/app.py` (start it in `run()`); tests `tests/server/test_bump_keeper.py`.

**Interfaces:**
- `pending_jobs(stations, now, hours=24) -> list[RenderJob]`, de-duplicated by key, skipping files that exist.
- `scan_once(stations, render=render) -> int`, which returns the number rendered.
- `request_bump_scan() -> None`: wakes the keeper now.
- `start_bump_keeper(interval=300) -> threading.Thread`: a daemon thread that scans at start, every `interval`, or when requested; a lock guarantees one scan at a time.
- `build.py` workers and `server/cli.py` build commands call `request_bump_scan()`; the CLI has no keeper, so there it renders the pending jobs inline.

- [ ] Tests first:
  - `test_pending_jobs_dedupes_and_skips_cached`;
  - `test_scan_renders_each_missing_job_once`;
  - `test_scan_survives_a_failing_render`;
  - `test_overlapping_scans_do_not_double_render`;
  - `test_requested_scan_runs_before_the_interval`.
- [ ] Implement and start it in `server/api/app.run()`.
- [ ] Suite green.
- [ ] Commit `feat: keep autobumps rendered ahead on the server`.

### Task 5: One dev environment, and the real run

**Files:** `dev/Dockerfile`, `dev/Dockerfile.dockerignore`, `compose.dev.yml`, `dev/run-client.sh`, `dev/devtv.json` (add an `autobump` section), `dev/README.md`, `.env.example` (`DISPLAY`, `PULSE_SERVER`), `README.md`.

- [ ] `dev/Dockerfile`:
  - Debian bookworm with system Python;
  - apt: `mpv ffmpeg python3-tk`, the Qt runtime libraries (as in `client/Dockerfile`), and the build tools for evdev;
  - a venv with `server/requirements.txt`, `client/requirements.txt`, `client/requirements-web.txt` and `requirements-dev.txt`;
  - `playwright install --with-deps chromium`.
- [ ] `compose.dev.yml`:
  - service `dev` (server, user-owned bind mount, X11 socket, the pulse socket from `.env`, `shm_size: 1gb`, ports 4242 and 4243);
  - the `tests` profile.
- [ ] `dev/run-client.sh`:
  - makes `/tmp/fs42-client` with the runtime defaults and a `client.json` (`http://localhost:4242`, `local_api_port` 4243, `web_pages` true);
  - runs `PYTHONPATH=/app python3 -m client.main` from there.
- [ ] Verify in the dev container, after seeding:
  - the keeper renders DevTV's bumps;
  - `ffprobe` shows H.264 1280×720 + AAC at the right lengths;
  - a frame grab of each kind is saved for the owner;
  - `dev/run-client.sh` plays them (on WSLg);
  - `docker build -f client/Dockerfile` has no QtWebEngine (`pip show PySide6-Addons` fails) and no Chromium;
  - the server image has Chromium;
  - the suite passes in the container.
- [ ] Commit `feat: one dev environment for both ends`. Push, and confirm CI is green.

### Task 6: Publish images and the client-only download

**Files:** `.github/workflows/publish.yml`, `client/compose.yml`, `compose.yml`, `client/platform/make_bundle.sh`, `README.md`.

- [ ] `publish.yml`: on push to `main` and on tags `v*`, build with buildx and push:
  - `ghcr.io/m0nte1ro/fs42-server` (linux/amd64);
  - `ghcr.io/m0nte1ro/fs42-client` (linux/amd64, linux/arm64);
  - tagged `latest` and the version tag. On tags, also run `make_bundle.sh` and attach `fs42-client-<tag>.tar.gz` to the GitHub release.
- [ ] `make_bundle.sh`: archive `client/`, `shared/`, the five default runtime media files, `client.example.json`, `LICENSE` and a short README. Check with `tar -tzf` that it contains no `server/`.
- [ ] Compose files reference the published image and keep `build:` for local builds. `client/compose.yml` reads `./client.json` next to it, so the folder works on its own.
- [ ] README:
  - the server LXC with only `compose.yml` + `.env`;
  - a Docker client with only `client/compose.yml` + `client.json`;
  - a native Pi from the release archive;
  - making the GHCR packages public once.
- [ ] Verify:
  - `make_bundle.sh` locally (contents listed, no server code);
  - the workflow's syntax with `rhysd/actionlint` in Docker;
  - the compose files with `docker compose config`.
- [ ] Commit `feat: publish server and client images and a client-only download`, push, and confirm CI and the publish workflow on `main`.
