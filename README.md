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

```bash
git clone https://github.com/m0nte1ro/FieldStation42-Distributed
cd FieldStation42-Distributed
cp .env.example .env        # optional: port, time zone, media folder
docker compose up -d --build
```

The console is at `http://<server>:4242`. On first start the server creates `confs/`, `catalog/` and `runtime/` next to `compose.yml` and fills `runtime/` with the default standby, static, sign-off and off-air media.

Your library is mounted from `MEDIA_DIR` (default `./media`) and appears at `/media` inside the server: point station `content_dir` values, or the symlinks in `catalog/`, there. Configure channels and build catalogs and schedules from the console as in FieldStation42 ([fieldstation42.com](https://fieldstation42.com/docs/), `docs/STATION_CONFIG_README.md`). The server keeps every channel scheduled ahead on its own (default: when less than a day is left, add a week; change it with `schedule_agent` in `confs/main_config.json`).

Logos, standby images and guide images or music must live under the server's directory (relative paths, as in FieldStation42's examples) to reach the clients.

## Client

### Raspberry Pi or any Linux PC (native)

Requirements: 64-bit Linux, an X11 session on `DISPLAY=:0` (on Raspberry Pi OS choose X11 in `raspi-config`), the **same time zone as the server**, Python 3.11–3.13.

```bash
sudo apt install mpv python3-venv python3-tk
git clone https://github.com/m0nte1ro/FieldStation42-Distributed
cd FieldStation42-Distributed
bash client/platform/install.sh     # asks for the server URL, offers to start on boot
```

Web channels and autobumps on a Raspberry Pi also need `sudo bash client/platform/web_reqs.sh`.

### PC with Docker

```bash
cp client.example.json client.json  # set server_url
xhost +local:docker                 # let the container draw on your display
docker compose -f client/compose.yml up -d --build
```

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

On power-on the client downloads the configs, the small files and a 24-hour rundown of every channel, then plays the last channel. A client that synced before starts from its last copy even when the server is down. While running it checks the server for changes every 10 seconds; new schedules take effect at the next block.

Each client answers its web remote at `http://<client>:4242/remote` (the page itself comes from the server). The OSD reads its layout from `client/osd/osd.json` (start from `client/osd/osd.json.example`).

## Access

There are no logins: anyone with this code who can reach the home network, by cable or over a VPN (WireGuard, Tailscale), can watch. Don't expose port 4242 to the internet.

## Development

```bash
python3 -m venv env && env/bin/pip install -r requirements-dev.txt
env/bin/pytest -q tests
```

Or in Docker, with a seeded test channel: see `dev/README.md`.

## Support upstream

If you're getting value from FieldStation42, consider supporting its author on [Patreon](https://www.patreon.com/cw/FieldStation42).
