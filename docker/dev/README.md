# Development environment

Runs the server from your checkout (the repo is bind-mounted, so code changes need only a restart)
and a seeded test channel, DevTV on channel 7, made of generated test patterns.

```bash
export FS42_UID=$(id -u) FS42_GID=$(id -g)        # containers write into the checkout as you

docker compose -f docker/dev/compose.yml up -d --build server
docker compose -f docker/dev/compose.yml exec server bash docker/dev/seed.sh
```

The console is at http://localhost:4242 and the box API at http://localhost:4242/box/version.
After changing server code: `docker compose -f docker/dev/compose.yml restart server`.

Run the tests in the container:

```bash
docker compose -f docker/dev/compose.yml --profile test run --rm tests
```

`test/test_media_folders.py` fails, as in upstream.

To watch DevTV, run a box on a machine with a display (see the main README) with
`box.json` pointing at `http://<this machine>:4242`.

Stop everything: `docker compose -f docker/dev/compose.yml down`. The seed leaves
`catalog/devtv/`, `confs/devtv.json` and `runtime/` in your checkout (all git-ignored); delete
them to start over.
