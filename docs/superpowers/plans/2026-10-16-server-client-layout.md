# Server/Client Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganise the code into `server/`, `client/`, `shared/` and `tests/` so every file is visibly backend or frontend, drop the box/all-in-one switches, get CI green, and make `docker compose up -d --build` work after a clone.

**Architecture:** Moves follow the mapping table below. Behaviour is unchanged except: the client always plays from a server (no `is_box()` branches), and "box" becomes "client". `shared/rundown.py` holds the only play-point calculation.

**Tech Stack:** Python 3.11+, FastAPI, mpv (python-mpv-jsonipc), PySide6/Tk on the client, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-16-server-box-split.md` (section "Code layout").

## Global Constraints

- Nothing changes on screen; no behaviour change beyond removing all-in-one mode and renaming box → client.
- Every task ends with the whole suite green: `env/bin/pytest -q -p no:cacheprovider tests` (after Task 1 there are no expected failures).
- `client/` and `shared/` never import `server`; `server/` and `shared/` never import `client`. The server image is built without `client/` and the client image without `server/` (per-Dockerfile `.dockerignore`).
- The `/client` HTTP API is the only contract between the ends; `docs/client-api.md` documents it so another client (e.g. an Android TV app) can implement it.
- Packages are imported as `server.…`, `client.…`, `shared.…`; processes run with the repo root as working directory (data dirs `confs/`, `catalog/`, `runtime/` stay at the root).
- No AI attribution in commits or docs.

## Review Focus

1. A string path still pointing into `fs42/` (static dirs, schema, systemd `ExecStart`, scripts): grep for `fs42/` and `fs42.` must return only docs history and data paths. Checked in Task 5.
2. Processes started with `multiprocessing` (guide, overlays, web render) must import the moved modules by their new names. Covered by importing every module in Task 4.
3. The server's own views (console schedule pages) must still get play points and blocks after `LiquidManager` delegates to `shared/rundown.py`. Test in Task 2.
4. `docker compose up -d --build` on a clean clone with no `.env`. Checked in Task 5.
5. A client whose `client.json` is missing must fail with a clear message, not a traceback deep in sync. Test in Task 4.

## Mapping

| From | To |
|---|---|
| `GuideWindowConf` (defaults + `check_config`) from `fs42/guide_tk.py` | `shared/stations/guide_conf.py` (so loading stations never imports Tk) |
| `fs42/station_manager.py`, `station_io.py`, `config_processor.py`, `station_config_schema.json`, `slot_reader.py`, `schedule_hint.py` | `shared/stations/manager.py`, `io.py`, `config_processor.py`, `schema.json`, `slot_reader.py`, `schedule_hint.py` |
| `fs42/timings.py`, `title_parser.py` | `shared/timings.py`, `shared/title_parser.py` |
| `fs42/block_plan.py`; `PlayPoint`, `ScheduleNotFound`, `ScheduleQueryNotInBounds`, `get_programming_block`/`get_play_point` logic from `liquid_manager.py`; the decode half of `box/rundown.py`; autobump prefix test | `shared/rundown.py` |
| `fs42/catalog*.py`, `media_processor.py`, `fluid_*.py`, `sequence*.py`, `metadata_io.py`, `path_query.py`, NFO parsing half of `nfo_agent.py` | `server/catalog/` (`nfo.py` for the parser) |
| `fs42/liquid_*.py`, `reel_cutter.py`, `marathon_agent.py`, `hint_agent.py`, `autobump_agent.py`, `live_schedule_agent.py`, `schedule_keeper.py`, `schedule_lock.py` | `server/scheduler/` |
| `fs42/fs42_server/fs42_server.py`, `api/*.py` except `player.py`, `static/`, `box/rundown.py` encode half, `api/box.py` | `server/api/app.py`, `server/api/routes/`, `server/api/static/`, `server/api/routes/client.py` |
| `station_42.py` | `server/cli.py` (all flags) + `server/main.py` (runs the server) |
| `fs42/ux/` (Textual TUI), `page_stream/` | `server/tui/`, `server/page_stream/` |
| `field_player.py` | `client/main.py` |
| `fs42/station_player.py`, `reception.py`, `command_executor.py`, `guide_tk.py`, `guide_builder.py`, `webrender/web_render.py`, `box/sync.py`, `box/clock.py`, `box/media.py`, `box/config.py` | `client/playback/player.py`, `reception.py`, `executable.py`, `guide_tk.py`, `guide_builder.py`, `web_render.py`, `sync.py`, `clock.py`, `media.py`, `config.py`, plus new `rundown_store.py` (rundown + metadata on disk) |
| `fs42/osd/`, `osd/` (examples), `fs42/overlay/`, overlay half of `nfo_agent.py` | `client/osd/` (`overlays/now_playing.py`, `ticker.py`, `parental_controls.py`, `nfo_overlay.py`, `examples/`) |
| `fs42/pi/remote_controller.py`, `pi/cable_box.py`, `pico/aerial_listener.py`, `command_input.py`, `hot_start.sh`; `api/player.py` + PPV command routes + `box/proxy.py` | `client/input/` (`uart_bridge.py`, `local_api.py`, `proxy.py`) |
| volume and system-info helpers from `api/player.py`; `install/systemd/`, `install/install_services.sh`, `uninstall_services.sh`, `web_reqs*.sh`; client part of `install.sh` | `client/platform/` (`volume.py`, `system_info.py`, `systemd/`, `install.sh`, …) |
| `install/requirements-server.in`, `requirements-box.in`, `requirements-dev.in` | `server/requirements.txt`, `client/requirements.txt`, `requirements-dev.txt` |
| `docker/server/*`, `docker/dev/*` | `server/Dockerfile`, `compose.yml`, `compose.dev.yml`, `server/dev/` (seed) |
| `test/*` | `tests/server/`, `tests/client/`, `tests/shared/` by what they test |
| removed | `fs42/` (emptied), `fs42/remote/` (never started), `fs42/diagchannel/` (dead), root `install.sh`, `Makefile`, `docker/` (upstream all-in-one GUI image), `test/test_media_folders.py` (tests a function that doesn't exist), `box.json` handling |

---

### Task 1: Green CI on the current tree
**Files:** `.github/workflows/unit_tests.yml`, `install/requirements.txt`, delete `test/test_media_folders.py`
- [ ] Add `requests` to `install/requirements.txt`; CI matrix `["3.11", "3.12"]`; remove `continue-on-error`.
- [ ] Delete `test/test_media_folders.py`.
- [ ] Run the suite: 0 failures. Push and confirm both CI jobs pass with `gh pr checks 1`.
- [ ] Commit `fix: make CI pass on Python 3.11 and 3.12`.

### Task 2: `shared/`
**Files:** create `shared/` per the mapping; update importers; move tests to `tests/shared/`.
**Interfaces (produces):**
- `shared/rundown.py`:
  - `BlockPlanEntry`, `PlayPoint`, `ScheduleNotFound`, `ScheduleQueryNotInBounds`
  - `AUTOBUMP_PREFIX = ":autobump:="` and `is_autobump_url(path) -> bool`
  - `block_at(blocks: list, when: datetime)`, which raises `ScheduleNotFound` / `ScheduleQueryNotInBounds` as `LiquidManager.get_programming_block` does
  - `play_point(station_conf: dict, blocks: list, when: datetime) -> PlayPoint | None`, which is the body of `LiquidManager.get_play_point`, streaming channels included
  - `Block` (`start_time`, `end_time`, `title`, `plan`, `content` as dict/list/None, `liquid_type`, `break_strategy`, `break_info`, `sequence_key`)
  - `decode_rundown(data: dict) -> dict[str, list[Block]]`
- `shared/stations/manager.py`: `StationManager` unchanged.
- [ ] Move `test_play_point_gaps.py` to `tests/shared/` and point it at `shared.rundown.play_point`. Add `test_server_play_point_delegates_to_shared` (server `LiquidManager.get_play_point` returns the same `PlayPoint` as `play_point` for one block). Add `test_decode_rundown_round_trip` (from the old `test_box_rundown.py` round-trip cases, server encoder → `decode_rundown`).
- [ ] Watch them fail, move the code, update every import, then run the suite green.
- [ ] Commit `refactor: move station config and the rundown contract to shared/`.

### Task 3: `server/`
**Files:** per the mapping; `server/api/routes/client.py` serves `/client/version`, `/client/rundown`, `/client/files`, `/client/file` and `/client/media` (formerly `/box/*`); tests to `tests/server/`.
- [ ] Add `tests/test_layout.py`: `client/` and `shared/` have no `server` imports; `server/` and `shared/` have no `client` imports. It fails now (no packages yet) or is skipped for missing dirs; it must pass from Task 4 on.
- [ ] Move the modules and static files, and fix static and schema paths (`server/api/static`, `shared/stations/schema.json`). Remove the server-side box branches (`MetadataIO`, `LiquidManager`, `StationIO` box checks).
- [ ] `server/main.py` runs the app with the schedule keeper. `server/cli.py` is `station_42.py` with its imports updated.
- [ ] Suite green. Commit `refactor: move the backend to server/`.

### Task 4: `client/`
**Files:** per the mapping; tests to `tests/client/`.
- [ ] Client modules lose every `is_box()` branch: the player always maps media through `client/playback/media.py` (local files first), always loads schedules from `client/playback/rundown_store.py`, never builds schedules, and always runs sync.
- [ ] `client/playback/config.py` reads `client.json`. A missing file raises `SystemExit` with "client.json not found - run client/platform/install.sh or copy client.example.json" (`test_missing_client_json_exits_with_a_clear_message`).
- [ ] Add `test_every_module_imports` (imports every module under `server`, `client`, `shared` with `tkinter` and PySide6 stubbed).
- [ ] `tests/test_layout.py` passes. Suite green. Commit `refactor: move the frontend to client/`.

### Task 5: Docker, installers, docs
**Files:** `server/Dockerfile`, `server/Dockerfile.dockerignore` (excludes `client/`), `client/Dockerfile` + `client/Dockerfile.dockerignore` (excludes `server/`) + `client/compose.yml` (X11 and PulseAudio passthrough for a PC client), `docs/client-api.md`, `server/entrypoint.sh`, `compose.yml`, `.env.example`, `compose.dev.yml`, `server/dev/seed.sh`, `client/platform/install.sh`, systemd templates, `client.example.json`, `README.md`, `.gitignore`, `.dockerignore`.
- [ ] `compose.yml` runs one service `server`, built from `server/Dockerfile`:
  - port `${FS42_PORT:-4242}:4242` and `TZ=${TZ:-Europe/Lisbon}`;
  - volumes `./confs`, `./catalog`, `./runtime`, and `${MEDIA_DIR:-./media}:${MEDIA_DIR:-/media}:ro`.
- [ ] `server/entrypoint.sh` creates `confs/`, `catalog/` and `runtime/`, copies upstream's default runtime media from the image when missing, then execs `python3 -m server.main`.
- [ ] `client/platform/install.sh`: venv, `client/requirements.txt`, the runtime defaults, writes `client.json` from a prompt, installs the systemd user units (`ExecStart` = `python3 -m client.main`, the OSD and inputs).
- [ ] Verify:
  - `grep -rn "fs42/\|from fs42\|import fs42"` over code, scripts and templates returns nothing;
  - in a fresh clone at `/tmp`, `docker compose up -d --build`, `curl :4242/client/version` and the console `/` both answer, then `docker compose down` and delete the clone;
  - `compose.dev.yml` seed and the tests profile pass;
  - `bash -n` on all scripts;
  - the built server image contains no `/app/client` and the built client image no `/app/server`.
- [ ] README: the tree, server in three commands, client install, `client.json`.
- [ ] Commit `refactor: one-command server and a client installer`, push, and confirm CI is green on the PR.
