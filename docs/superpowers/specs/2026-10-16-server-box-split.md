# Split FieldStation42 into a server and player boxes

Status: draft for review · Base: upstream snapshot `54f7cca` (upstream `06bf018`)

## Goal

One FieldStation42 server in the homelab holds the channels, schedules, catalog and media. Any
number of boxes (the PC in the kid's room, a Raspberry Pi at the grandparents', a laptop) play
those channels. A box is a normal FS42 install switched into box mode: it never builds a
catalog or a schedule and never keeps a copy of the library.

Principles, in priority order:

1. **Channel switching stays as fast as possible.** A tune never waits on the server.
2. **Nothing changes visually.** Every upstream feature looks and behaves as it does today
   (static, scramble FX, OSD and logos, guide, web channels, autobumps, PPV, overlays,
   parental PIN, remotes, cable box, Pico).
3. **Both ends stay light.** A box is never heavier than an upstream install; the server runs
   only what keeps the boxes in sync: scheduling, config and media.
4. **Split, don't redesign.** Change the fewest upstream lines that make the split work.

## Non-goals

HLS/IPTV output, transcoding, pre-tuning neighbour channels (to be benchmarked against HLS
later), per-box channel lineups, logins or tokens, a box registry or console page for boxes,
kiosk/autologin setup, Windows, tracking upstream.

## How it works

```
 server (Docker, always on)                       box (always on, always playing)
 ┌───────────────────────────────┐   rundown,     ┌───────────────────────────────┐
 │ upstream catalog + scheduler  │   config,      │ upstream player (box mode)    │
 │ upstream web console :4242    │   small files  │  local rundown copy, all chans│
 │ schedule agent (moved here)   │ ─────────────► │  MPV, static, FX, OSD, guide  │
 │ /box API + media (HTTP Range) │   media        │ upstream API :4242 (box mode) │
 └───────────────────────────────┘ ─────────────► │  /player/* local, rest proxied│
                                    (or SMB/NFS)  └───────────────────────────────┘
```

**Access.** No logins. Anyone with this code who can reach the home LAN (cable or VPN) can
watch. The server keeps upstream's open console on `:4242`.

**Clock.** Schedules stay in naive local time (upstream). Boxes run in the server's time zone
and correct their clock with the `server_time` the server sends; the play point is
`datetime.now() + offset`, so two boxes on one channel show the same thing.

**Power-on.** The box downloads the config, the small files and a rundown of every channel,
then starts playing (last channel, as upstream). Boot speed is not a goal; the box stays on.

**Background updates.** Every 10 s the box asks `GET /box/version`. When the version changes it
re-downloads what changed. New rundowns take effect at the next block boundary, exactly as
upstream's `reload_data` does today. The rundown is also refreshed every hour so it always
covers the next 24 hours.

**Tune.** A channel change reads the play point from the local rundown (upstream's
`get_play_point`, unchanged), runs the transition effect as today, and opens the media once at
the right offset (`loadfile <url> replace -1 start=<offset>`) instead of play-then-seek.

## Server changes

| Change | Where |
|---|---|
| `/box` router (below) | new `fs42/fs42_server/api/box.py`, registered in `api/__init__.py` |
| Run the live schedule agent in the server process, on by default (`trigger_add_at: day`, `amount_to_add: week` when `schedule_agent` is absent from `main_config.json`) | `fs42_server.py` startup; `live_schedule_agent.py` unchanged |
| One schedule-writer lock across processes: `fcntl` lock on `runtime/schedule.lock` around adding time and resetting schedules, so the agent, web builds and the CLI never write at once | new `fs42/schedule_lock.py`; used in `liquid_schedule.py` and `liquid_manager.py` |
| Server image: Python 3.12 slim, ffmpeg, tk; volumes `confs/`, `catalog/`, `runtime/`; media mounted at the same paths the catalog uses; `TZ` set | new `docker/server/Dockerfile`, `docker/server/compose.yml` |
| Bump FastAPI/Starlette past Starlette 0.49.1 (Range header fix) | `install/requirements*.txt` |

Everything else on the server (console, build endpoints, `/player/*` routes) is left as is.

### `/box` API

All JSON, all unauthenticated, all read-only.

- `GET /box/version` → `{"version": "<hash>", "server_time": "<ISO>"}`. The hash covers the
  `liquid_blocks` table (row count and max id) and the size and mtime of every file in the
  manifest, so any schedule build, catalog rebuild or config edit changes it.
- `GET /box/rundown?hours=24` → `{"version", "server_time", "stations": {network_name: [block]}}`
  with every block where `end_time > now` and `start_time < now + hours`. Read straight from
  SQLite on each call (never the in-memory cache, so CLI builds are seen). A block is
  `{liquid_type, start_time, end_time, title, break_strategy, break_info, sequence_key,
  content, plan, meta}`, where `content` is `{path, title, tag, duration, content_type,
  media_type}` (or a list, or null), `plan` is the stored plan entries unchanged, and `meta` is
  the cached metadata of the content path (as `/schedules` already attaches).
- `GET /box/files` → `[{"path", "size", "mtime"}]`: the files a box must have on disk.
  `confs/*.json` (including `main_config.json`) plus, for each station, `standby_image`,
  `off_air_image`, every file under `content_dir/logo_dir`, and the guide channel's `images` and
  `sound_to_play` (directories expanded).
- `GET /box/file?path=` → the bytes of one manifest path; 404 for anything not in the manifest.
- `GET /box/media?path=` → the media file via `FileResponse` (HTTP Range, so MPV seeks
  directly). Allowed when the normalised path has no `..` and is either under some station's
  `content_dir`, under `runtime/`, or equal to a station media key (`sign_off_video`,
  `off_air_video`, `be_right_back_media`, `standby_image`, `off_air_image`). Symlinks are
  followed. Extensions: the video, audio and image types `media_processor` catalogs.

## Box changes

Box mode is on when `box.json` exists in the FS42 root (git-ignored, written by the installer,
never touched by sync):

```json
{
  "server_url": "http://homelab:4242",
  "media": {"method": "http"},
  "main_config": {"start_channel": 3}
}
```

`media.method` is `http` (default) or `mount` with a `root` (an SMB/NFS mount of the server's
FS42 directory; plan paths are joined to `root`, and the share must resolve the library
symlinks on the server side). `main_config` holds box-only overrides (start channel, recall
last channel, parental theme, and so on) merged over the server's `main_config.json` when it
is written to disk. Volume stays the box's own mixer, as upstream.

| Change | Where |
|---|---|
| Box bootstrap: read `box.json`; download `/box/files` into the FS42 root (owning `confs/*.json`: stale station files are removed) and the rundown into `runtime/rundown.json`; retry every 5 s with the standby image on screen until the first sync succeeds | new `fs42/box/sync.py`, called from `field_player.py` before `StationManager()` |
| Background poller thread: `/box/version` every 10 s, rundown every hour; on change re-sync and queue `reload_data` (upstream's own reload path) | `fs42/box/sync.py`, started in `field_player.py` |
| No schedule building on a box: no live schedule agent; `schedule_panic` becomes "refresh rundown, return FAILED" (upstream already shows standby and retries on FAILED) | `field_player.py`, `station_player.py` |
| Station loading skips the media-exists checks (`content_dir`, `sign_off_video`, `off_air_video`, `standby_image`, `be_right_back_media`), which would otherwise drop every station | `station_io.py` |
| Schedules come from `runtime/rundown.json` instead of SQLite; `get_play_point`, `get_programming_block` and the guide work unchanged on top | `liquid_manager.py` (`reload_schedules`), new `fs42/box/rundown.py` |
| Metadata for overlays and the guide comes from the rundown's `meta` instead of SQLite | `metadata_io.py` (`read`) |
| Play point uses `now + offset` from the last `server_time` | `field_player.py`, `station_player.py` |
| Media path to URL (`/box/media?path=`) or mount path, for plan entries, guide audio and PPV; URLs skip the `os.path.exists` check | new `fs42/box/media.py`, used in `station_player.py` |
| Open once at the offset (`start=`) instead of play-then-seek-verify | `station_player.py` (`play_file`) |
| Local API in box mode: `/player/*` and the PPV `play_file`/`key` posts are handled on the box (as upstream); every other route is proxied to the server. That keeps the `http://127.0.0.1:4242/...` autobump URLs stored in plans, `localhost` web URLs, the web remote, volume and diagnostics working unchanged on the box | `fs42_server.py`, `api/ppv.py`, new `fs42/box/proxy.py` (httpx) |
| Box installer: upstream `install.sh` and `install_services.sh`, plus a prompt for the server URL that writes `box.json`; box requirements without the catalog/build-only packages (moviepy, mutagen, textual, rich, jsonschema) | `install.sh`, new `install/requirements-box.in` |

Unchanged on the box: OSD, overlays, guide, web render, reception effects, remote controller,
cable box, Pico bridge, systemd units and their names. They keep reading the same local files
(`runtime/*.socket`, `confs/`, logo folders), which the box player and sync now provide.

## Failure behaviour

- **Server down at power-on:** standby image, retry every 5 s; plays once the first sync works.
- **Server down later:** the box keeps its last rundown and keeps tuning; media already
  buffered keeps playing; a failed open is upstream's FAILED path (standby, retry each second).
  When the server is back, everything resumes on its own.
- **Rundown doesn't cover now:** refresh the rundown and return FAILED (standby, retry).
- **Catalog rebuilt on the server:** the version changes; the box picks up the new rundown at
  the next block boundary.

## Box requirements

64-bit Linux (PySide6 has no 32-bit ARM builds), an X11 session on `DISPLAY=:0` as upstream,
the server's time zone, Python 3.11–3.13 (upstream's overlays rely on the `fork` start method),
mpv.

## Testing

pytest, matching `test/`:

- `/box` API with a temp DB and confs: version changes on a schedule write and on a config
  edit; rundown includes the block that started before now; manifest lists logos and guide
  assets; `/box/file` rejects non-manifest paths; `/box/media` returns 206 for a Range request
  and rejects `..` and paths outside the allowed roots.
- Parity: a rundown produced by the server and loaded by a box gives the same `get_play_point`
  as the server's own `LiquidManager` at the same instant, for standard, loop, clip, off-air and
  autobump blocks.
- Box sync writes the manifest files, removes stale `confs/*.json`, merges `box.json`
  overrides into `main_config.json`.
- `station_io` in box mode keeps stations whose media paths don't exist locally.
- Media mapping: http URL, mount path, autobump and stream entries left untouched.
- Schedule lock: a second writer waits.

Manual acceptance on real boxes: two boxes on the same channel show the same thing; zapping
feels like upstream or faster; pulling the server's network cable shows standby and recovers;
a schedule rebuild reaches both boxes without touching them.
