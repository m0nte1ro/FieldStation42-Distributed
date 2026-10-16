# Server/Box Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one FS42 install the server (scheduling, config, media) and any other install a box that plays from it, with no visual change and a box lighter than upstream.

**Architecture:** The server keeps upstream as is and adds a read-only `/box` API, runs the schedule agent itself and serialises schedule writers with a file lock. A box is upstream with a `box.json`: it mirrors config and small files, keeps a 24-hour rundown of every channel in `runtime/rundown.json`, plays media over HTTP (or a mount), and runs upstream's API locally with `/player/*` handled on the box and everything else proxied to the server.

**Tech Stack:** Python 3.12 (box 3.11–3.13), FastAPI/Starlette, httpx (new, box and tests only), SQLite, mpv via python-mpv-jsonipc, pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-server-box-split.md`

## Global Constraints

- Without `box.json` in the FS42 root every code path behaves exactly as upstream. Box-only branches are guarded by `is_box()`.
- Nothing changes visually: transitions, FX, OSD, guide, overlays, web channels, autobumps, PPV look and behave as upstream.
- The only new dependency is `httpx`. A box installs `install/requirements-box.in`, which must not contain moviepy, mutagen, textual, rich or jsonschema.
- Paths stay CWD-relative to the FS42 root, as upstream (`confs/`, `runtime/`, `catalog/`).
- Run tests from the repo root: `env/bin/pytest -q -p no:cacheprovider`. Baseline: 332 passed, 5 failed. The 5 failures are all in `test/test_media_folders.py` (upstream calls a missing `media.list_folders`) and must stay the only failures.
- New tests are pytest functions in `test/test_box_*.py` or `test/test_schedule_*.py`. Stub `ffmpeg`/`moviepy` through `sys.modules.setdefault(..., MagicMock())` before importing `fs42` modules, as `test/test_play_point_gaps.py` does. Reset the `StationManager` Borg state as `test/test_station_drafts.py` does.
- Commits: `feat:`/`fix:`/`docs:`/`test:` prefix, subject under 72 characters, body says why. No AI attribution anywhere.
- `/box` endpoints: `GET /box/version`, `GET /box/rundown?hours=24`, `GET /box/files`, `GET /box/file?path=`, `GET /box/media?path=`. Poll every 10 s, rundown every 3600 s, first-sync retry every 5 s.

## Review Focus

1. Server unreachable while a box runs (cable pulled, VPN down): the poller logs and keeps looping, and the box keeps playing and tuning from its last rundown. Test in Task 5.
2. A manifest entry that is absolute or contains `..` must never be written on the box. Test in Task 5.
3. `/box/media` path escapes (`../confs/main_config.json`, `catalog/../confs/x.json`, a `.json` file under `content_dir`) are refused. Test in Task 3.
4. A block that started before the rundown window (day-long loop blocks, a movie started an hour ago) must be in the rundown, or the box can't tune. Test in Task 3.
5. Media paths with spaces, `#`, `?`, `&` or non-ASCII characters must survive the URL round trip to `/box/media`. Test in Task 6.

---

### Task 1: Schedule write lock

**Files:**
- Create: `fs42/schedule_lock.py`
- Modify: `fs42/liquid_schedule.py` (`_increment`), `fs42/liquid_manager.py` (`reset_all_schedules`, `reset_schedule`)
- Test: `test/test_schedule_lock.py`

**Interfaces:**
- Produces: `schedule_write_lock(lock_path: str = "runtime/schedule.lock") -> ContextManager[None]`, an exclusive `fcntl.flock` on the file (created along with its directory if missing), held for the `with` block.

- [ ] **Step 1: Write the failing tests**

```python
def test_second_writer_is_blocked_while_lock_is_held(tmp_path):
    lock = tmp_path / "runtime" / "schedule.lock"
    with schedule_write_lock(str(lock)):
        with open(lock) as other, pytest.raises(BlockingIOError):
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

def test_lock_is_released_after_the_block(tmp_path):
    lock = tmp_path / "schedule.lock"
    with schedule_write_lock(str(lock)):
        pass
    with open(lock) as other:
        fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

def test_increment_runs_under_the_lock(monkeypatch):
    # patch fs42.liquid_schedule.schedule_write_lock with a context manager that records entry,
    # build LiquidSchedule via __new__ with conf {"network_type": "streaming"} and _blocks = [],
    # call _increment("day"): the recorder was entered exactly once.
```

- [ ] **Step 2: Run** `env/bin/pytest -q -p no:cacheprovider test/test_schedule_lock.py` and expect FAIL (`ModuleNotFoundError: fs42.schedule_lock`).
- [ ] **Step 3: Implement** `schedule_write_lock`. Wrap the body of `LiquidSchedule._increment` and of `LiquidManager.reset_all_schedules` and `reset_schedule` (the delete part, not `reload_schedules`) in `with schedule_write_lock():`. Don't nest the lock: `reset_*` never calls `_increment`.
- [ ] **Step 4: Run** the new tests, then the full suite: 5 known failures only.
- [ ] **Step 5: Commit** `feat: serialise schedule writers with a file lock`

### Task 2: Box config, clock and rundown codec

**Files:**
- Create: `fs42/box/__init__.py` (empty), `fs42/box/config.py`, `fs42/box/clock.py`, `fs42/box/rundown.py`
- Modify: `.gitignore` (add `box.json`)
- Test: `test/test_box_rundown.py`, `test/test_box_config.py`

**Interfaces:**
- Produces in `fs42/box/config.py`:
  - `BOX_CONFIG_PATH = "box.json"`
  - `is_box() -> bool`, which checks `os.path.exists(BOX_CONFIG_PATH)` at call time.
  - `load_box_config(path: str = BOX_CONFIG_PATH) -> dict`. It returns the parsed JSON with defaults `media={"method": "http"}` and `main_config={}`, and `server_url` with its trailing `/` stripped. It raises `ValueError` when `server_url` is missing.
- Produces in `fs42/box/clock.py`:
  - `set_server_time(server_time: str, received_at: datetime | None = None) -> None` stores `offset = fromisoformat(server_time) - (received_at or datetime.now())`.
  - `now() -> datetime` returns `datetime.now() + offset`. The offset is 0 until set, so it is safe to call outside box mode.
- Produces in `fs42/box/rundown.py`:
  - `RUNDOWN_PATH = "runtime/rundown.json"`
  - `META: dict[str, dict]`
  - `block_to_json(block) -> dict` gives `{liquid_type, start_time, end_time (isoformat), title, break_strategy, break_info, sequence_key, content, plan}`. `content` is `None`, one `{path, title, tag, duration, content_type, media_type}` dict, or a list of them. `plan` is `[entry.toJSON()]`.
  - `block_from_json(data: dict)` returns a Liquid*Block through `LiquidIO._block_factory`. It rebuilds `CatalogEntry(path, duration, tag, [], 0, content_type, media_type)` with `title` set, `sequence_key`, and a `BlockPlanEntry` plan.
  - `build_rundown(stations: list[dict], now: datetime, hours: int) -> dict` gives `{"server_time": now.isoformat(), "stations": {name: [block_to_json]}, "meta": {path: meta}}`.
    - It covers stations whose `network_type` is not `guide` or `streaming`, the same rule as `LiquidManager.reload_schedules`.
    - Blocks come from `LiquidIO().query_liquid_blocks(name, str(now), str(now + timedelta(hours=hours)))`.
    - `meta` is `MetadataIO.read_many` over every content path and plan path.
  - `load_rundown(path: str = RUNDOWN_PATH) -> dict[str, list]` rebuilds the blocks and replaces `META`. It returns `{}` if the file is missing.
  - `box_meta(path: str) -> dict | None` looks up `META`.

- [ ] **Step 1: Write the failing tests**

```python
def test_round_trip_gives_the_same_play_point_for_each_block_type():
    # build in memory: a LiquidBlock (content CatalogEntry, plan of feature + commercial + bump),
    # a LiquidOffAirBlock, and a LiquidWebBlock whose plan path is ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?title=X"
    # for each: box = block_from_json(json.loads(json.dumps(block_to_json(block))))
    # with LiquidManager.__new__ manager, get_programming_block returning the block (as in test_play_point_gaps),
    # at block.start_time + 100 s: index, offset, block_title and [e.toJSON() for e in plan] are equal for both

def test_clip_block_content_list_survives_round_trip():
    # LiquidClipBlock with two CatalogEntry -> block_from_json(...).content paths == the two paths

def test_load_rundown_fills_meta_and_returns_blocks_by_station(tmp_path):
    # write {"server_time": ..., "stations": {"Toons": [block_to_json(b)]}, "meta": {"catalog/t/a.mp4": {"title": "A"}}}
    # load_rundown(path)["Toons"][0].title == b.title and box_meta("catalog/t/a.mp4") == {"title": "A"}

def test_load_rundown_missing_file_is_empty(tmp_path):
    assert load_rundown(str(tmp_path / "nope.json")) == {}

def test_clock_follows_server_time_even_when_local_clock_is_years_off():
    set_server_time("2026-10-16T20:00:00", received_at=datetime(2001, 1, 1, 0, 0))
    assert abs((now() - datetime.now()) - (datetime(2026, 10, 16, 20) - datetime(2001, 1, 1))) < timedelta(seconds=1)

def test_load_box_config_applies_defaults_and_strips_slash(tmp_path):
    # {"server_url": "http://homelab:4242/"} -> server_url "http://homelab:4242", media {"method": "http"}, main_config {}

def test_load_box_config_without_server_url_raises(tmp_path):
    # {} -> pytest.raises(ValueError)
```

- [ ] **Step 2: Run** both test files and expect FAIL (`ModuleNotFoundError: fs42.box`).
- [ ] **Step 3: Implement** the three modules as specified. Reset the clock offset in a test fixture. `build_rundown` is tested in Task 3.
- [ ] **Step 4: Run** both files, then the full suite.
- [ ] **Step 5: Commit** `feat: add box config, server clock and rundown codec`

### Task 3: Server `/box` API

**Files:**
- Create: `fs42/fs42_server/api/box.py`
- Modify: `fs42/fs42_server/api/__init__.py` (add `box_router` to `routers`), `install/requirements.in` (`fastapi>=0.120`, `starlette>=0.49.1`), `install/requirements.txt` (pin `fastapi`, `starlette` and their resolved dependencies to the versions in `env/bin/pip freeze`)
- Test: `test/test_box_api.py`

**Interfaces:**
- Consumes: `build_rundown` (Task 2), `StationManager().stations`, `StationManager().server_conf["db_path"]`.
- Produces:
  - `file_manifest(stations: list[dict], confs_dir: str = "confs") -> list[dict]` gives `[{"path", "size", "mtime"}]`, sorted by path, de-duplicated, existing regular files only, paths `os.path.normpath`'d. Sources:
    - every `confs/*.json`;
    - each station's `standby_image` and `off_air_image`;
    - every file under `os.path.join(content_dir, logo_dir)`;
    - the guide station's `images` and `sound_to_play` (a string file, a directory expanded to its files, or a list).
  - `compute_version(db_path: str, manifest: list[dict]) -> str` is the sha1 hex of `liquid_blocks` `count(*)`, `max(id)` and the JSON of the manifest. It is `0:0` for the table part when the table is missing.
  - `media_allowed(path: str, stations: list[dict]) -> bool`. It returns False for an empty path, a NUL byte, or `..` in `Path(path).parts`. Otherwise, with `norm = os.path.normpath(path)`, it returns True when:
    - the extension (lowercased, without the dot) is in `MediaProcessor.supported_formats` or `{png, jpg, jpeg, gif, bmp, webp}`; and
    - `norm` is under some station's normalised `content_dir` or under `runtime`, or equals the normalised value of `sign_off_video`, `off_air_video`, `be_right_back_media`, `standby_image` or `off_air_image`.
  - `router = APIRouter(prefix="/box", tags=["box"])` with:
    - `GET /version` gives `{"version", "server_time": datetime.now().isoformat()}`;
    - `GET /rundown?hours=24` gives `build_rundown(...)` plus `"version"`;
    - `GET /files` gives the manifest;
    - `GET /file?path=` gives a `FileResponse` when the path is in the manifest, else 404;
    - `GET /media?path=` gives 403 when not `media_allowed`, 404 when not a file, else `FileResponse` with the type from `mimetypes`.

- [ ] **Step 1: Write the failing tests.** They run under `monkeypatch.chdir(tmp_path)`, with `confs/`, `catalog/toons/` and `runtime/` created. `fs42.fs42_server.api.box.StationManager` is patched to stations `[{"network_name": "Toons", "network_type": "standard", "content_dir": "catalog/toons", "logo_dir": "logos", "standby_image": "runtime/standby.png"}]` and `server_conf={"db_path": "runtime/fs42.db"}`. Tables come from `LiquidIO()`/`CatalogIO()`, and rows are inserted with raw SQL. Use `TestClient` on a `FastAPI()` that includes only `router`.

```python
def test_rundown_includes_block_that_started_before_now():          # loop block 00:00-24:00 today, now = 15:00 -> present
def test_rundown_excludes_blocks_ending_before_now_and_beyond_hours(): # ended 14:00 absent; starts now+25h absent with hours=24
def test_rundown_carries_plan_paths_unchanged_and_meta():           # plan path "catalog/toons/a b#1.mp4" kept verbatim
def test_version_changes_when_a_block_is_added():
def test_version_changes_when_a_conf_file_changes():                 # rewrite confs/toons.json with new mtime
def test_files_lists_confs_logos_and_standby_image():
def test_file_outside_manifest_is_404():                             # /box/file?path=runtime/fs42.db -> 404
def test_media_range_request_returns_206():                          # headers={"Range": "bytes=0-9"} -> 206, 10 bytes
def test_media_refuses_escapes_and_non_media():
    # "../confs/toons.json", "catalog/../confs/toons.json", "catalog/toons/notes.json", "/etc/passwd" -> 403
def test_media_missing_allowed_file_is_404():
```

- [ ] **Step 2: Run** `test/test_box_api.py` and expect FAIL (`ModuleNotFoundError` for `fs42.fs42_server.api.box`).
- [ ] **Step 3: Implement** `box.py` as specified and register it in `api/__init__.py`. Handlers that touch SQLite or the filesystem are plain `def`, so they run in the threadpool. Update the requirement pins.
- [ ] **Step 4: Run** the new file, then the full suite.
- [ ] **Step 5: Commit** `feat: add read-only /box API for player boxes`

### Task 4: Schedule keeper on the server and the server image

**Files:**
- Create: `fs42/schedule_keeper.py`, `install/requirements-server.in`, `docker/server/Dockerfile`, `docker/server/compose.yml`
- Modify: `fs42/fs42_server/fs42_server.py` (`mount_fs42_api` starts the keeper)
- Test: `test/test_schedule_keeper.py`

**Interfaces:**
- Produces:
  - `DEFAULT_AGENT_CONF = {"trigger_add_at": "day", "amount_to_add": "week"}`
  - `start_schedule_keeper(agent_conf: dict | None, interval: float = 60) -> threading.Thread`. This is a daemon thread that builds `LiveScheduleAgent(agent_conf or DEFAULT_AGENT_CONF, multiprocessing.Lock())` and calls `tick()` every `interval` seconds, logging and surviving exceptions.

- [ ] **Step 1: Write the failing tests**

```python
def test_keeper_uses_defaults_and_ticks(monkeypatch):
    # patch fs42.schedule_keeper.LiveScheduleAgent with a fake recording conf and tick count;
    # start_schedule_keeper(None, interval=0.01); wait up to 1 s for >= 2 ticks
    # assert fake conf == {"trigger_add_at": "day", "amount_to_add": "week"}

def test_keeper_survives_a_failing_tick(monkeypatch):
    # fake tick raises on first call; still reaches >= 2 calls
```

- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** the keeper. In `mount_fs42_api` (server mode only; not `run_with_shutdown_queue`), call `start_schedule_keeper(StationManager().server_conf.get("schedule_agent"))` before `uvicorn.run`.
  - `install/requirements-server.in`: `ffmpeg-python`, `fastapi>=0.120`, `starlette>=0.49.1`, `uvicorn`, `jsonschema`, `requests`, `mutagen`, `rich`, `pillow`.
  - Dockerfile:
    - `FROM python:3.12-slim`;
    - `apt-get install -y --no-install-recommends ffmpeg libtk8.6`;
    - `WORKDIR /app`, then `COPY . .`;
    - `pip install -r install/requirements-server.in`;
    - `EXPOSE 4242`, `CMD ["python3", "station_42.py", "--server"]`.
  - `compose.yml`: one service `fs42-server`, built from the repo root with this Dockerfile. It has `ports: ["4242:4242"]`, `environment: [TZ=Europe/Lisbon]` and `restart: unless-stopped`. Volumes:
    - `../../confs:/app/confs`, `../../catalog:/app/catalog`, `../../runtime:/app/runtime`;
    - `/etc/localtime:/etc/localtime:ro`;
    - a commented example media mount at an identical path (`# - /mnt/media:/mnt/media:ro`).
- [ ] **Step 4: Run** the new tests and the full suite. Read the Dockerfile and compose file back. Do not build or run Docker.
- [ ] **Step 5: Commit** `feat: run the schedule agent on the server and add a server image`

### Task 5: Box sync

**Files:**
- Create: `fs42/box/sync.py`
- Modify: `install/requirements-dev.in`, `install/requirements-dev.txt` (add `httpx`)
- Test: `test/test_box_sync.py`

**Interfaces:**
- Consumes: `load_box_config`, `clock.set_server_time`, `RUNDOWN_PATH` (Task 2); the `/box` routes (Task 3).
- Produces:
  - `reload_requested = threading.Event()` and `refresh_requested = threading.Event()`
  - `MANIFEST_STATE = "runtime/box_manifest.json"` and `SERVER_MAIN_CONFIG = "runtime/main_config.server.json"`
  - `class BoxSync(config: dict, root: str = ".", client: httpx.Client | None = None)`. The default client is `httpx.Client(base_url=config["server_url"], timeout=10)`. Methods:
    - `fetch_version() -> str` calls `GET /box/version` and `set_server_time`.
    - `sync_files() -> None`:
      - Skips manifest paths that are absolute or contain `..`.
      - Downloads an entry when its `[size, mtime]` differs from `MANIFEST_STATE` or the file is missing, with an atomic write (tmp file and `os.replace`). It downloads `confs/main_config.json` to `SERVER_MAIN_CONFIG` instead.
      - Writes `confs/main_config.json` as the server copy (or `{}`) updated with `config["main_config"]`.
      - Removes `confs/*.json` files that aren't in the manifest (keeping `main_config.json`), then saves `MANIFEST_STATE`.
    - `sync_rundown() -> None` calls `GET /box/rundown?hours=24`, writes `RUNDOWN_PATH` atomically and calls `set_server_time`.
    - `sync_all() -> None` runs `fetch_version`, `sync_files` and `sync_rundown`, then stores the version.
    - `initial_sync(retry_seconds: float = 5) -> None`. If `RUNDOWN_PATH` and `MANIFEST_STATE` exist, it tries `sync_all` once and returns either way. Otherwise it repeats `sync_all` until it succeeds, sleeping `retry_seconds` between attempts.
    - `poll_once(rundown_every: float = 3600) -> bool`:
      - Calls `sync_all` when the version changed or `refresh_requested` is set, else `sync_rundown` when `rundown_every` has passed since the last one.
      - Sets `reload_requested` and returns True when anything was synced.
      - Catches `httpx.HTTPError` and `OSError`, logs them and returns False.
    - `start_poller(interval: float = 10, rundown_every: float = 3600) -> threading.Thread` is a daemon looping `poll_once` every `interval`.

- [ ] **Step 1: Write the failing tests.** They use a fake server built with `httpx.MockTransport` (dict-based routes, with a version you can bump) and `root=tmp_path`.

```python
def test_initial_sync_writes_files_rundown_and_merged_main_config(tmp_path):
    # manifest: confs/main_config.json {"time_format": "%H:%M", "start_channel": 1}, confs/toons.json, catalog/toons/logos/a.png
    # box main_config {"start_channel": 3} -> confs/main_config.json == {"time_format": "%H:%M", "start_channel": 3}
def test_unchanged_files_are_not_downloaded_again(tmp_path):        # second sync_files: no /box/file requests
def test_stale_station_conf_is_removed(tmp_path):                     # confs/old.json gone after sync, main_config.json kept
def test_absolute_and_dotdot_manifest_paths_are_skipped(tmp_path):   # "/etc/evil.json", "../evil.json" never requested or written
def test_poll_after_version_change_resyncs_and_requests_reload(tmp_path):
def test_poll_with_server_down_returns_false_and_keeps_files(tmp_path):  # transport raises httpx.ConnectError
def test_refresh_requested_forces_a_resync(tmp_path):
def test_initial_sync_with_cache_returns_even_if_server_is_down(tmp_path):
def test_initial_sync_without_cache_retries_until_server_answers(tmp_path):  # first 2 calls ConnectError, retry_seconds=0
```

- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** `sync.py` as specified. Add `httpx` to the dev requirements.
- [ ] **Step 4: Run** the new file and the full suite.
- [ ] **Step 5: Commit** `feat: sync config, files and rundown from the server on boxes`

### Task 6: Box data layer and media locations

**Files:**
- Create: `fs42/box/media.py`
- Modify: `fs42/station_io.py` (`FILE_CHECKS` loop in `_process_single_config`), `fs42/liquid_manager.py` (`reload_schedules`), `fs42/metadata_io.py` (`read`, `read_many`)
- Test: `test/test_box_data.py`

**Interfaces:**
- Consumes: `is_box`, `load_rundown`, `box_meta` (Task 2).
- Produces: `media_location(path: str, config: dict) -> str`.
  - `path` is returned unchanged when `"://" in path` or `AutoBumpAgent.is_autobump_url(path)` is true.
  - With `media.method == "http"` the result is `f"{server_url}/box/media?path={quote(path, safe='')}"`.
  - With `mount` the result is `f"{root.rstrip('/')}/{path.lstrip('/')}"`.
- Behaviour in box mode:
  - `StationIO` skips the `FILE_CHECKS` existence checks.
  - `LiquidManager.reload_schedules` sets `self.schedules[name] = load_rundown().get(name, [])`, using the same station filter as upstream.
  - `MetadataIO.read` returns `box_meta(file_path)`.
  - `MetadataIO.read_many` returns `{p: m for p in file_paths if (m := box_meta(p))}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_http_location_round_trips_awkward_names():
    p = "catalog/toons/Ep 1 #2 ?&ção.mp4"
    url = media_location(p, {"server_url": "http://homelab:4242", "media": {"method": "http"}})
    assert parse_qs(urlparse(url).query)["path"] == [p]
def test_mount_location_joins_root():                     # root "/mnt/fs42/" + "catalog/a.mp4" -> "/mnt/fs42/catalog/a.mp4"
def test_streams_and_autobumps_are_left_alone():          # "https://x/live.m3u8", ":autobump:=http://127.0.0.1:4242/static/bump/bump.html?t=1"
def test_box_mode_keeps_station_with_missing_media(tmp_path, monkeypatch):
    # chdir tmp, write box.json, station with content_dir "catalog/missing" (as _complete_station in test_station_drafts)
    # StationManager().stations has the station; without box.json it is skipped
def test_box_mode_schedules_come_from_rundown(tmp_path, monkeypatch):   # LiquidManager().schedules["Toons"] from runtime/rundown.json
def test_box_mode_metadata_comes_from_rundown(tmp_path, monkeypatch):   # MetadataIO.read("catalog/toons/a.mp4") == rundown meta
```

- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4: Run** the new file and the full suite.
- [ ] **Step 5: Commit** `feat: load stations, schedules and metadata from the rundown on boxes`

### Task 7: Player in box mode and single-open tuning

**Files:**
- Modify: `fs42/station_player.py` (`__init__`, `play_file`, `play_and_wait`, `schedule_panic`; keep `_seek_with_verify` as the fallback), `field_player.py` (`input_check`, `main_loop`, `__main__`)
- Test: `test/test_box_player.py`

**Interfaces:**
- Consumes: `BoxSync`, `reload_requested`, `refresh_requested` (Task 5); `media_location` (Task 6); `clock.now` (Task 2); `is_box`, `load_box_config`.
- Behaviour:
  - `StationPlayer.__init__`:
    - Assigns `self.mpv = mpv` when an mpv is passed. Upstream never assigns it, which is a bug.
    - Sets `self.box_config = load_box_config() if is_box() else None`.
  - `play_file`:
    - Plays `target = media_location(file_path, self.box_config)` when on a box, else `file_path`.
    - The existence check accepts `os.path.exists(target) or is_stream or autobump or "://" in target`.
    - The status socket and overlays keep the original `file_path`.
    - Before loading it sends `mpv.command("set", "start", str(offset_seconds))` for a non-stream with `offset_seconds > 0`, else `mpv.command("set", "start", "none")`. It then loads once, as now.
    - Once `time_pos` is available, if a non-stream with `offset_seconds > 0` is more than 1.0 s away from the offset, it falls back to the existing `_seek_with_verify` (kept unchanged until real HTTP files prove the single open).
  - `play_and_wait` maps its path with `media_location` on a box.
  - `schedule_panic` on a box sets `refresh_requested` and returns without building anything.
  - `field_player.py`:
    - `__main__`, on a box: `sync = BoxSync(load_box_config())`, then `sync.initial_sync()` before the API process starts, and `sync.start_poller()` after it.
    - `main_loop` doesn't create `LiveScheduleAgent` on a box.
    - The two `datetime.datetime.now()` calls that feed `play_slot` and its log line use `clock.now()`.
    - `input_check`, when `reload_requested` is set: clear it, `StationManager()._reload_stations()`, `LiquidManager().reload_schedules()`, then carry on with the normal checks.

- [ ] **Step 1: Write the failing tests.** They use a `FakeMPV` that records `command(*args)` and `play(path)`, with `time_pos = 0.0`, `duration = 600.0`, and settable `vf`, `panscan` and `keepaspect`. Patch `fs42.station_player.StationManager` (`server_conf` with `status_socket` in tmp, `date_time_format`, `video_seek_timeout: 1`), `StationPlayer._apply_vfx` to a no-op, and `StationPlayer._nfo_overlay_data` to return None.

```python
def test_tune_opens_once_at_the_offset():
    # play_file("catalog/a.mp4", file_duration=600, offset_seconds=120) with the file existing
    # commands include ("set", "start", "120") before play("catalog/a.mp4"); play called once; no ("seek", ...) command
def test_zero_offset_resets_start():                       # ("set", "start", "none")
def test_open_that_misses_the_offset_falls_back_to_seek():  # FakeMPV time_pos stays 0.0 with offset 120 -> _seek_with_verify called once
def test_box_plays_server_url_but_reports_original_path(tmp_path, monkeypatch):
    # box.json present; play_file("catalog/a.mp4", ...) -> play(url from media_location); status file file_path == "catalog/a.mp4"
def test_box_schedule_panic_requests_refresh_and_builds_nothing(monkeypatch):
    # patch LiquidSchedule to fail if constructed; refresh_requested is set
def test_input_check_reloads_when_sync_requests_it(monkeypatch, tmp_path):
    # reload_requested.set(); patched StationManager (channel_socket in tmp) and LiquidManager;
    # field_player.input_check() -> _reload_stations and reload_schedules called once, event cleared
```

- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4: Run** the new file and the full suite. Also run `env/bin/python -c "import field_player"` from the repo root without `box.json`: it imports without error.
- [ ] **Step 5: Commit** `feat: play from the server on boxes and tune with one open`

### Task 8: Box local API

**Files:**
- Create: `fs42/box/proxy.py`
- Modify: `fs42/fs42_server/api/ppv.py` (move the two POST routes to `commands_router`; skip `os.path.exists` on a box), `fs42/fs42_server/api/__init__.py` (add `ppv_commands_router` to `routers`), `fs42/fs42_server/fs42_server.py` (`build_app`)
- Test: `test/test_box_api_local.py`

**Interfaces:**
- Consumes: `load_box_config`, `is_box` (Task 2).
- Produces:
  - `build_proxy_router(server_url: str, transport: httpx.AsyncBaseTransport | None = None) -> APIRouter`. It has a catch-all `/{path:path}` for GET, POST, PUT, PATCH, DELETE and HEAD, and it reuses one `httpx.AsyncClient(base_url=server_url, follow_redirects=False, timeout=httpx.Timeout(10, read=None))`.
    - It forwards the method, path, raw query string, body and request headers. The request headers exclude `host` and the hop-by-hop set: `connection`, `keep-alive`, `proxy-authenticate`, `proxy-authorization`, `te`, `trailer`, `transfer-encoding`, `upgrade`.
    - It sends with `stream=True` and returns a `StreamingResponse` over `aiter_raw()`, so bytes pass through untouched. That keeps `content-encoding`, `content-length`, `content-range` and `accept-ranges` valid.
    - Response headers are the upstream ones minus the hop-by-hop set. Redirects (3xx with `location`) pass through as is. The upstream response is closed by a `BackgroundTask` when streaming ends.
    - A connection error returns 502 `{"detail": "server unreachable"}`.
  - In `ppv.py`: `commands_router = APIRouter(prefix="/ppv", tags=["ppv"])`, holding `play_file` and `send_key` unchanged apart from the box exists-skip.
  - In `fs42_server.py`: `build_app(box_config: dict | None) -> FastAPI`.
    - Without a config it is upstream's app: all `routers`, plus `/`, `/remote` and `/favicon.ico`.
    - With a config it has only `player_router`, `ppv.commands_router` and `build_proxy_router(box_config["server_url"])`, in that order.
    - `fapi = build_app(load_box_config() if is_box() else None)`, and `_mount_static()` does nothing on a box.

- [ ] **Step 1: Write the failing tests.** They use `TestClient(build_app({"server_url": "http://server:4242"}))`, with the proxy transport injected through a monkeypatched `build_proxy_router` or a module-level transport hook, and an `httpx.MockTransport` that records requests.

```python
def test_data_routes_are_proxied_with_query_and_status():  # GET /schedules/Toons?start=a&end=b -> recorded URL; upstream 404 passes through as 404
def test_post_body_is_proxied():                            # POST /build/catalog/all body b"{}" arrives
def test_static_pages_are_proxied():                        # GET /static/bump/bump.html -> recorded
def test_redirect_is_passed_through_not_followed():         # upstream 307 location /static/x -> client sees 307 with same location, one upstream request
def test_range_request_and_response_pass_through():         # client Range bytes=0-9 reaches upstream; 206 + content-range returned
def test_compressed_body_passes_through_raw():              # upstream gzip bytes + content-encoding gzip -> identical bytes and header
def test_hop_by_hop_headers_are_dropped():                  # upstream connection/keep-alive headers absent; x-custom kept
def test_unreachable_server_is_502():                       # transport raises httpx.ConnectError -> 502
def test_player_routes_stay_local():                        # GET /player/status/queue_connected -> {"queue_connected": False}; transport not called
def test_ppv_play_file_is_local_and_skips_exists_on_box(tmp_path, monkeypatch):
    # box.json present; app.state.player_command_queue = queue.Queue();
    # POST /ppv/7/play_file {"file_path": "catalog/ppv/m.mp4"} (not on disk) -> 200 and queued play_file command
def test_full_app_unchanged_without_box_config():           # build_app(None) still serves GET /remote and /box/version
```

- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** as specified.
- [ ] **Step 4: Run** the new file and the full suite.
- [ ] **Step 5: Commit** `feat: run the local API on boxes and proxy data to the server`

### Task 9: Box installer and docs

**Files:**
- Create: `install/requirements-box.in`
- Modify: `install.sh`, `README.md`
- Test: manual (`bash -n install.sh`)

**Interfaces:**
- `install/requirements-box.in`: `python-mpv-jsonipc`, `ffmpeg-python`, `pillow`, `PySide6>=6.8`, `fastapi>=0.120`, `starlette>=0.49.1`, `uvicorn`, `httpx`, `requests`, `pyserial`, `evdev`.
- `install.sh`:
  - After the confirmation prompt, ask `read -p "Server URL for a player box (leave empty for a full install): " FS42_SERVER_URL`.
  - If it is non-empty, write `box.json` as `{"server_url": "<url>", "media": {"method": "http"}, "main_config": {}}`, using `python3 -c` with `json.dump`. Then install from `install/requirements-box.in` instead of `install/requirements.in`. The existing per-line loop reads `$REQ_FILE`.

- [ ] **Step 1: Implement** the requirements file and the installer change.
- [ ] **Step 2: Verify:**
  - `bash -n install.sh` exits 0.
  - `grep -E "moviepy|mutagen|textual|rich|jsonschema" install/requirements-box.in` prints nothing.
  - Run the `box.json` writer line on its own in a temp directory, then `python3 -m json.tool box.json`.
- [ ] **Step 3: Document.** Rewrite the top of `README.md` to say what this project is: FieldStation42 split into a server and player boxes, based on upstream `shane-mason/FieldStation42` at `06bf018` under MPL-2.0. Keep upstream's feature description. Add a section "Server and boxes" covering:
  - Server: `docker compose -f docker/server/compose.yml up -d` with the media mounted at the paths the catalog uses.
  - Box: `bash install.sh` and enter the server URL, then `bash install/install_services.sh`. A box needs 64-bit Linux, an X11 session, the server's time zone and mpv.
  - `box.json` fields: `media.method` is `http` or `mount` with a `root`. For a mount, the share must resolve the library symlinks on the server side; Samba can, NFS can't. `main_config` holds overrides.
  - Logos and standby images must live under the FS42 directory to reach boxes.
- [ ] **Step 4: Run** the full suite once more. It should show 5 known failures only, plus all the new tests passing.
- [ ] **Step 5: Commit** `feat: install player boxes and document server and boxes`

### Task 10: Docker development environment

**Files:**
- Create: `docker/dev/compose.yml`, `docker/dev/seed.sh`, `docker/dev/devtv.json`, `docker/dev/README.md`
- Test: manual (build and run in the dev project only)

**Interfaces:**
- Consumes: `docker/server/Dockerfile` (Task 4), the `/box` API (Task 3).
- `docker/dev/compose.yml`, project name `fs42-dev`, has two services built from `docker/server/Dockerfile`, both with the repo bind-mounted at `/app`:
  - `server`: `python3 station_42.py --server` on `4242:4242`, `TZ=Europe/Lisbon`, `restart: "no"`.
  - `tests` (profile `test`): installs `pytest httpx` on top and runs `pytest -q -p no:cacheprovider`.
- `docker/dev/seed.sh`, run inside the `server` container:
  - Uses `ffmpeg -f lavfi` `testsrc2`/`sine` to write short clips into `catalog/devtv/`: 3 × 60 s `shows`, 4 × 15 s `commercials`, 2 × 5 s `bumps`.
  - Copies `docker/dev/devtv.json` to `confs/devtv.json`.
  - Runs `python3 station_42.py -r devtv` then `python3 station_42.py -d devtv`.
  - It is idempotent: existing clips are kept.
- `docker/dev/devtv.json`:
  - A standard station `DevTV` on channel 7 with `content_dir: "catalog/devtv"`, `commercial_dir: "commercials"`, `bump_dir: "bumps"` and `schedule_increment: 0`.
  - Every day uses one template with all 24 hours set to `{"tags": "shows"}`.

- [ ] **Step 1: Implement** the four files. `docker/dev/README.md` explains:
  - `docker compose -f docker/dev/compose.yml up -d --build server`;
  - `docker compose -f docker/dev/compose.yml exec server bash docker/dev/seed.sh`;
  - the `tests` profile;
  - that a box is run on a machine with a display, with `box.json` pointing at `http://<dev host>:4242`.
- [ ] **Step 2: Verify** in the `fs42-dev` project only:
  - Build, `up`, then run the seed.
  - `curl -s localhost:4242/box/version` returns a version.
  - `curl -s "localhost:4242/box/rundown?hours=1"` contains `DevTV` blocks.
  - `curl -s -H "Range: bytes=0-99" -o /dev/null -w "%{http_code}" "localhost:4242/box/media?path=<a plan path>"` prints `206`.
  - `docker compose --profile test run --rm tests` passes with the 5 known failures only.
  - Then `docker compose -f docker/dev/compose.yml down`. Never touch other projects' containers.
- [ ] **Step 3: Commit** `feat: add a Docker development environment with a seeded test channel`
