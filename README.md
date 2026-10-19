# FieldStation42 Distributed

FieldStation42 split into a **server** and **clients**. One server in the homelab holds the channels, schedules, catalog and media. Any number of clients (the PC in the kid's room, a Raspberry Pi at the grandparents', a laptop) play those channels, each on whatever channel it likes, all on the same broadcast timeline. A client never builds a catalog or a schedule and never keeps a copy of the library: rebooting one only starts the player.

On screen nothing changes from FieldStation42: static on tune, scramble effects, OSD and logos, the guide, web channels, autobumps, PPV, overlays, remotes and the cable box.

Based on [shane-mason/FieldStation42](https://github.com/shane-mason/FieldStation42) at commit `06bf018`, licensed under the Mozilla Public License 2.0 (see `LICENSE`). Upstream is not tracked after that point.

![A cable box next to a TV](docs/cable_cover_3.png?raw=true)

## The layout

```
server/      the backend - runs in Docker, built without client/
  catalog/     scanning media, durations, chapters, sequences, NFO metadata
  scheduler/   building schedules, breaks, autobumps, keeping channels scheduled ahead
  api/         web console, data routes, and the client API (/client/*)
  main.py      runs the server · cli.py: catalog and schedule commands · tui/: terminal UI
client/      the frontend - runs on each TV (natively, or in Docker on a PC), built without server/
  playback/    mpv player, tune static and effects, guide, web channels, sync with the server
  osd/         on-screen display, logos, overlays (now playing, ticker, parental PIN, NFO)
  input/       IR/keyboard remote, cable box, Pico/UART, the client's local API on :4242
  platform/    volume, system info, installer, systemd units
  main.py      runs the client
shared/      used by both: station config loading, timings, title parsing, the rundown contract
tests/       server/, client/, shared/ - plus a test that the ends never import each other
dev/         development environment (compose.dev.yml)
```

The ends talk only over HTTP: the [client API](docs/client-api.md).

## Server

On the machine that hosts it (a Debian LXC on Proxmox works: enable nesting for Docker), no repository needed:

```bash
mkdir fs42 && cd fs42
curl -fsSLO https://raw.githubusercontent.com/m0nte1ro/FieldStation42-Distributed/main/compose.yml
curl -fsSL https://raw.githubusercontent.com/m0nte1ro/FieldStation42-Distributed/main/.env.example -o .env   # port, time zone, media folder
docker compose up -d        # pulls ghcr.io/m0nte1ro/fs42-server
```

From a clone of the repository, `docker compose up -d --build` builds the same image from source.

The console is at `http://<server>:4242`. On first start the server creates `confs/`, `catalog/` and `runtime/` next to `compose.yml` and fills `runtime/` with the default standby, static, sign-off and off-air media.

Your library is mounted from `MEDIA_DIR` (default `./media`) and appears at `/media` inside the server. Keep station `content_dir` values relative, as in FieldStation42's examples (`catalog/nbc`), and make the tag folders symlinks into the library, e.g. `ln -s /media/tv/sitcoms catalog/nbc/sitcom` (create them from inside the container, or with the same `/media` path on the host, so they resolve in the server). Logos, standby images and guide images or music must live under `catalog/`, `runtime/` or `confs/` with relative paths: those are the files clients copy, and an absolute `content_dir` would keep logos from reaching them.

Configure channels and build catalogs and schedules from the console as in FieldStation42 ([fieldstation42.com](https://fieldstation42.com/docs/), `docs/STATION_CONFIG_README.md`), or with the CLI: `docker compose exec server python3 -m server.cli --help`. The server keeps every channel scheduled ahead on its own (default: when less than a day is left, add a week; change it with `schedule_agent` in `confs/main_config.json`).

### Autobumps

Autobumps are the bumps FieldStation42 builds from a channel's `autobump` settings ("DevTV — Sempre ligada", "A seguir na DevTV: Bluey"). The server renders each one to a short video once and reuses it forever, so clients only ever play clips:

- one start-of-break bump per channel look, one "coming up next" per show, and one 30-second filler loop per show (the client loops it for the gap and draws the countdown);
- new ones render within seconds of a schedule or catalog build, and the rest every 5 minutes;
- every text comes from the channel's `autobump` settings, including the next-up line: `"next_up_text": "A seguir na {network}"` (default `"Coming up on {network}"`);
- turn on `"normalize_titles": true` in `confs/main_config.json` so "Bluey s01e03" counts as "Bluey": one bump per show instead of per episode.

The server image carries the Chromium that renders them; clients don't need one.

## Client

Every client needs the **same time zone as the server** and a `client.json` (below).

### Raspberry Pi or any Linux PC (native)

Requirements: 64-bit Linux and an X11 session on `DISPLAY=:0` (on Raspberry Pi OS choose X11 in `raspi-config`), Python 3.11–3.13. Download the client-only archive (`fs42-client-<version>.tar.gz`) from the [releases](https://github.com/m0nte1ro/FieldStation42-Distributed/releases):

```bash
sudo apt install mpv python3-venv python3-tk
tar -xzf fs42-client-<version>.tar.gz && cd fs42-client
bash client/platform/install.sh     # asks for the server URL and about web pages, offers to start on boot
```

(From a clone of the repository the same `install.sh` works.) Web pages on a Raspberry Pi also need `sudo bash client/platform/web_reqs.sh`.

### PC with Docker

In a folder with `client/compose.yml` and a `client.json` (from `client.example.json`):

```bash
xhost +local:docker                 # let the containers draw on your display
docker compose up -d                # pulls ghcr.io/m0nte1ro/fs42-client: the player and the OSD
```

In the repository: `cp client.example.json client/client.json`, then `docker compose -f client/compose.yml up -d --build` to build it. The image has no browser; build with `--build-arg WEB_PAGES=true` for web pages.

### Settings: `client.json`

```json
{
  "server_url": "http://homelab:4242",
  "media": {"method": "http"},
  "main_config": {"start_channel": 3}
}
```

- `media.method` is `http` (media streams from the server and mpv seeks straight to the right point) or `mount` with a `root`, e.g. `{"method": "mount", "root": "/mnt/fs42"}` for an SMB/NFS mount of the server's FieldStation42 directory. The share must resolve the library's symlinks on the server side: Samba can, NFS can't.
- `main_config` holds this client's overrides of the server's `main_config.json` (start channel, recall last channel, parental controls theme, ...). Volume is the client's own.
- `web_pages` (default `false`): web channels (guide page, weather, PPV menu, diagnostics) and the live fallback for an autobump that isn't rendered yet. Off, a client leaves web channels out of its lineup and shows standby for a bump that isn't ready; that keeps a 1 GB Pi comfortable. On, it needs the browser engine: answer yes in the installer, or build the Docker client with `--build-arg WEB_PAGES=true`.
- `local_api_port`: only when the server runs on the same machine. The client's own API normally uses the server's port (4242); with the server there already, set e.g. `4243`. The web remote is then at `:4243/remote`, and an IR remote script needs `FS42_PORT=4243`.

On power-on the client downloads the configs, the small files and a 24-hour rundown of every channel, then plays the last channel. A client that synced before starts from its last copy even when the server is down. While running it checks the server for changes every 10 seconds; new schedules take effect at the next block.

Each client answers its web remote at `http://<client>:4242/remote` (the page itself comes from the server). The OSD reads its layout from `client/osd/osd.json` (start from `client/osd/osd.json.example`).

## Access

There are no logins: anyone with this code who can reach the home network, by cable or over a VPN (WireGuard, Tailscale), can watch. Don't expose port 4242 to the internet.

## Development

```bash
python3 -m venv env && env/bin/pip install -r requirements-dev.txt
env/bin/pytest -q tests
```

Or one Docker container with both ends, Chromium for autobumps and a seeded test channel you can watch on your screen: see `dev/README.md`.

## Publishing

Pushing to `main` publishes both images (`latest`); a version tag (`git tag v1.0.0 && git push --tags`) publishes them with the version and attaches the client archive to a GitHub release. The first time, make the two packages public under the GitHub profile's Packages tab, or `docker login ghcr.io` on the machines that pull them.

## Support upstream

If you're getting value from FieldStation42, consider supporting its author on [Patreon](https://www.patreon.com/cw/FieldStation42).
