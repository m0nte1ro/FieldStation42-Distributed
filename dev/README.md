# Development environment

One container with both ends: it runs the server from your checkout (bind-mounted, so code changes
need only a restart), renders autobumps with its Chromium, and can start a client that draws on
your display. A seeded test channel, DevTV on channel 7, comes from generated test patterns and
has Portuguese autobumps.

```bash
export FS42_UID=$(id -u) FS42_GID=$(id -g)       # the container writes into the checkout as you

docker compose -f compose.dev.yml up -d --build dev
docker compose -f compose.dev.yml exec dev bash dev/seed.sh
```

The console is at http://localhost:4242. Within a couple of minutes the server renders DevTV's
bumps into `runtime/bumps/` (watch `docker logs -f fs42-dev | grep BumpKeeper`).

Watch it like a TV, from the same container:

```bash
docker compose -f compose.dev.yml exec dev bash dev/run-client.sh        # the player
docker compose -f compose.dev.yml exec dev bash dev/run-client.sh osd    # its OSD, in another terminal
```

The client keeps its data in `/tmp/fs42-client` inside the container and answers its own API
(web remote) on http://localhost:4243/remote. On WSL the window and sound go through WSLg with the
defaults; on Linux set `X11_SOCKET` and `PULSE_SOCKET` in `.env` (see `.env.example`) and run
`xhost +local:docker` once.

After changing server code: `docker compose -f compose.dev.yml restart dev`. Tests:

```bash
docker compose -f compose.dev.yml --profile test run --rm tests
```

Stop everything: `docker compose -f compose.dev.yml down`. The seed leaves `catalog/devtv/`,
`confs/devtv.json` and `runtime/` in your checkout (all git-ignored); delete them to start over.
