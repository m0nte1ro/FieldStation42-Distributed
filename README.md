# FieldStation42 Distributed

FieldStation42 split into a **server** and **player boxes**. One server in the homelab holds the channels, schedules, catalog and media. Any number of boxes (the PC in the kid's room, a Raspberry Pi at the grandparents', a laptop) play those channels, each on whatever channel it likes, all on the same broadcast timeline. A box never builds a catalog or a schedule and never keeps a copy of the library: rebooting one only starts the player.

On screen nothing changes: static on tune, scramble effects, OSD and logos, the guide, web channels, autobumps, PPV, overlays, remotes and the cable box all behave as in FieldStation42.

This project is based on [shane-mason/FieldStation42](https://github.com/shane-mason/FieldStation42) at commit `06bf018` and is licensed under the Mozilla Public License 2.0 (see `LICENSE`). Upstream is not tracked after that point. Design: `docs/superpowers/specs/2026-10-16-server-box-split.md`.

![A cable box next to a TV](docs/cable_cover_3.png?raw=true)

## What FieldStation42 does

FieldStation42 turns a Linux computer or Raspberry Pi into a broadcast and cable TV simulator. Instead of picking something to watch, you flip channels. Scheduled programming plays on its own timeline, with commercials, station bumps, and all the in-between stuff that made old-school TV feel alive. Learn more at [fieldstation42.com](https://fieldstation42.com).

- **Scheduled programming** — build real TV schedules with daily lineups, prime time blocks, marathons, and seasonal programming
- **Multiple channel types** — network TV, movie channels, guide channels, radio stations, IPTV streams, and looping displays
- **Commercials and bumps** — short clips fill the breaks between shows, just like real TV
- **Web console** — configure and manage your stations from a browser
- **Web remote** — change channels and control playback from your phone or any device on the network
- **IR remote support** — use any IR remote with a Flirc USB receiver
- **On-screen display** — channel banners and now-playing info overlay on the screen
- **Extensive REST API** — control playback, change channels, query status, and build your own tools and integrations

Channel configuration is FieldStation42's: see [fieldstation42.com](https://fieldstation42.com/docs/) and `docs/STATION_CONFIG_README.md`.

## Server and boxes

```
 server (always on)                         box (always on, always playing)
 catalog + scheduler + web console :4242    player, OSD, effects, guide
 schedule agent, /box API, media  ───────►  local API :4242 (/player/* here, the rest proxied)
```

### Server

The server runs the web console on port 4242, keeps every channel scheduled ahead on its own (default: when less than a day is left, add a week; override with `schedule_agent` in `confs/main_config.json`), and serves boxes their config, rundowns and media.

```bash
docker compose -f docker/server/compose.yml up -d --build
```

`confs/`, `catalog/` and `runtime/` are mounted from the repo directory. Mount your media at the **same path** your catalog uses (the paths your `catalog/` symlinks point to), and set `TZ` to your time zone. Then configure channels, build catalogs and schedules from the console at `http://<server>:4242` as in FieldStation42.

Logos, standby images and guide images or music must live under the FieldStation42 directory (relative paths, as in upstream's examples) to reach the boxes.

### Box

Requirements: 64-bit Linux (Raspberry Pi OS 64-bit, Debian, Ubuntu, Mint), an X11 session on `DISPLAY=:0`, the **same time zone as the server**, Python 3.11–3.13, and `sudo apt install mpv python3-venv python3-tk`.

```bash
git clone https://github.com/m0nte1ro/FieldStation42-Distributed
cd FieldStation42-Distributed
bash install.sh                      # enter the server URL when asked, e.g. http://homelab:4242
bash install/install_services.sh     # start on boot (fs42, plus the OSD/remote/cable box if wanted)
```

On power-on the box downloads the configs, small files and a 24-hour rundown of every channel, then plays the last channel. A box that has synced before starts from its last copy even if the server is down. While running it checks the server for changes every 10 seconds; new schedules take effect at the next block.

The box keeps its settings in `box.json` in the FieldStation42 directory:

```json
{
  "server_url": "http://homelab:4242",
  "media": {"method": "http"},
  "main_config": {"start_channel": 3}
}
```

- `media.method` is `http` (default: media streams from the server, MPV seeks straight to the right point) or `mount` with a `root`, e.g. `{"method": "mount", "root": "/mnt/fs42"}` for an SMB/NFS mount of the server's FieldStation42 directory. The share must resolve the library symlinks on the server side: Samba can, NFS can't.
- `main_config` holds this box's overrides of the server's `main_config.json` (start channel, recall last channel, parental controls theme, ...). Volume is the box's own.

Each box serves its own web remote at `http://<box>:4242/remote`.

### Access

There are no logins: anyone with this code who can reach the home network, by cable or over a VPN (WireGuard, Tailscale), can watch. Don't expose port 4242 to the internet.

## Development

`env/bin/pytest -q -p no:cacheprovider` runs the tests (create `env/` with `python3 -m venv env` and install `install/requirements.in` plus `install/requirements-dev.in`). `test/test_media_folders.py` fails as in upstream (it tests a function upstream never added).

## Support upstream

If you're getting value from FieldStation42, consider supporting its author on [Patreon](https://www.patreon.com/cw/FieldStation42).
