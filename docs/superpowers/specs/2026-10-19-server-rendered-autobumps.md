# Server-rendered autobumps, browser-free clients, one dev environment

Status: approved in chat 2026-10-19 · Builds on `2026-10-16-server-box-split.md`

## Why

An autobump is a bump FieldStation42 builds as a web page (channel name, text, music, upcoming
shows). Today every client renders it live in a Chromium (QtWebEngine) for a few seconds, which
costs 250–400 MB of RAM. That is what keeps a Raspberry Pi 4 with 1 GB from being comfortable.
The server renders them to video instead, once, and clients just play a clip.

## Decisions

1. **The server renders autobumps to video and caches them forever**, keyed by everything that
   shows on screen:
   - **start-of-break bumps** (station title, subtitle, details, music): once per station
     autobump config;
   - **"Coming up next" bumps**: once per show, as "Coming up on <network>" plus the title of
     the show that follows (instead of upstream's three-line lineup with times);
   - **gap fillers** (variable length, with a countdown, including off-air autobumps): one
     30-second loop per station config; the client loops it for the gap and mpv draws the
     countdown.
2. **The schedule in the database is not rewritten.** When a client fetches its rundown, the
   server replaces each autobump entry with its rendered clip if it exists; otherwise the entry
   goes out unchanged.
3. **Chromium lives only in the server image.** Clients install PySide6-Essentials (OSD,
   overlays); QtWebEngine (PySide6-Addons) is an opt-in extra.
4. **Clients have `"web_pages": false` by default** (`client.json`):
   - web channels are left out of that client's lineup (channel up/down skips them, the guide
     doesn't list them);
   - an autobump that isn't rendered yet shows the station's standby image for its length.
   With `"web_pages": true` (and the web extra installed) a client behaves as today. If
   QtWebEngine is missing anyway, a web page shows standby instead of stopping the player.
5. **Text is the owner's language.** Every bump text already comes from the station's autobump
   config except one phrase the server adds, "Coming up on {network}". It becomes
   `next_up_text` in the autobump config (default `"Coming up on {network}"`, e.g.
   `"A seguir na {network}"`). Turning on `normalize_titles` makes "Coming up next" bumps
   per show rather than per episode (documented).
6. **Renders happen as soon as they're needed.** Besides the 5-minute scan, the keeper scans
   right after any catalog or schedule build (web console, CLI) and at server start.
7. **Clients don't need the repository.** GitHub Actions publishes `ghcr.io/m0nte1ro/fs42-server`
   (amd64) and `ghcr.io/m0nte1ro/fs42-client` (amd64 and arm64), and attaches a client-only
   archive (client/, shared/, default media, installer) to each release. A Docker client needs
   only `client/compose.yml` and its `client.json`; the server LXC needs only `compose.yml` and
   `.env`.
8. **Narration** (a pt-PT voice saying the next show) is left for a later round.
9. **One development environment**: a single dev image with the server, the client (including
   the web extra), Chromium for rendering and the test tools. It runs the server, and a client
   can be started in the same container (with its own data directory) and shown on the
   developer's display.

## Server

- `server/bumps/jobs.py`: reads an `:autobump:=` URL and returns a render job: kind
  (`message`, `next_up`, `filler`), cache key, the page parameters to render, length, and
  whether the client loops it with a countdown.
  - `next_up` jobs take the following block's title, rendered through a new bump page parameter
    `next_title` (the page shows that title as its detail line and skips the schedule lookup);
    `next_network` is dropped from the rendered parameters.
  - `filler` jobs render 30 s with `countdown=false`; the export marks them `loop` and
    `countdown`.
  - The key is a hash of the rendered parameters (sorted), so identical bumps share a file.
- `server/bumps/renderer.py`:
  - headless Chromium (Playwright, `--no-sandbox`) opens
    `http://127.0.0.1:<port>/static/bump/bump.html?<params>` at 1280×720 and records the
    page for the bump's length;
  - ffmpeg trims the recording to start when the page has loaded, adds the audio (the
    `bg_music` file, looped when `loopmusic` is on, or the `bg_video`'s own sound unless
    `bg_video_audio=false`), and encodes H.264/AAC MP4 at 30 fps (`yuv420p`, `+faststart`);
  - output goes to `runtime/bumps/<key>.mp4`, written atomically.
- `server/bumps/keeper.py`: a background thread started with the server. Every 5 minutes it
  scans the next 24 hours of every station's schedule, works out the jobs and renders the
  missing ones one at a time. A failed render is logged and retried on the next scan.
- `server/api/rundown_export.py`: swaps rendered autobumps in. A swapped plan entry is
  `{"path": "runtime/bumps/<key>.mp4", "skip": 0, "duration": <unchanged>, "is_stream": false,
  "content_type": "bump", "media_type": "video"}` plus `"loop": true, "countdown": true` for
  fillers.
- `server/api/static/bump/bump.js`: the `next_title` parameter.
- `server/scheduler/autobump_agent.py`: the next-up subtitle comes from `next_up_text`.
- Builds (`server/api/routes/build.py` workers and `server/cli.py` schedule and catalog
  commands) call `request_bump_scan()`; the keeper scans when requested.
- `server/Dockerfile`: Playwright and its Chromium. `compose.yml`: `shm_size: 1gb`.

## Shared

- `BlockPlanEntry` gains `loop` and `countdown` (default `False`; written to JSON only when
  true, so stored plans don't change).

## Client

- A `loop` entry plays with mpv `loop-file=inf` (reset to `no` for every other file).
- A `countdown` entry shows the remaining gap as `M:SS` with mpv `show-text`, refreshed each
  second.
- `client.json`: `"web_pages"` (default `false`). Loading stations leaves out `web` stations
  when it is off.
- `client/requirements.txt` uses `PySide6-Essentials`; `client/requirements-web.txt` adds
  `PySide6-Addons`. `client/Dockerfile` installs the web extra only with `--build-arg
  WEB_PAGES=true`; `client/platform/install.sh` asks (default no) and sets `web_pages`.

## Development

- `dev/Dockerfile`: one image (Debian, system Python) with mpv, Tk, Qt runtime libraries,
  ffmpeg, Playwright Chromium, and the server, client, web and test requirements.
- `compose.dev.yml`: service `dev` runs the server from the checkout; the `tests` profile runs
  the suite.
- `dev/run-client.sh`: starts a client inside the dev container against
  `http://localhost:4242`, with its own data directory (`/tmp/fs42-client`), `local_api_port`
  4243 and `web_pages` on, drawing on the host's display (WSLg or X11, from `.env`).

## Not changing

How schedules are built, live web channels and PPV for clients that enable web pages, the
upstream web guide, and the look of start-of-break bumps and fillers (fillers keep their
countdown, drawn by mpv).

## Testing

- Jobs: classification and keys for each kind; identical bumps share a key; a different show
  title gives a different key; fillers render 30 s without countdown and are marked loop and
  countdown.
- Export: a rendered autobump is swapped for its clip; an unrendered one is left alone; a
  next-up bump with no following block in the window is left alone.
- Renderer: the ffmpeg command for music, looping music, video audio and no audio; the atomic
  write; with a fake Playwright and a fake runner.
- Keeper: renders missing jobs once, skips cached ones, survives a failing render.
- Client: loop and countdown entries; web stations left out with `web_pages` off; an
  unrendered autobump shows standby with `web_pages` off; a missing QtWebEngine shows standby.
- Real run in the dev environment: DevTV with an autobump config renders its bumps (checked with
  `ffprobe`); a client plays them; the client image contains no QtWebEngine or Chromium; the
  server image contains Chromium.
