# Development environment

Runs the server from your checkout (the repo is bind-mounted, so code changes need only a
restart) with a seeded test channel, DevTV on channel 7, made of generated test patterns.

```bash
export FS42_UID=$(id -u) FS42_GID=$(id -g)        # containers write into the checkout as you

docker compose -f compose.dev.yml up -d --build server
docker compose -f compose.dev.yml exec server bash dev/seed.sh
```

The console is at http://localhost:4242 and the client API at http://localhost:4242/client/version.
After changing server code: `docker compose -f compose.dev.yml restart server`.

Run the tests in the container:

```bash
docker compose -f compose.dev.yml --profile test run --rm tests
```

To watch DevTV, run a client on a machine with a display (see the main README) with
`client.json` pointing at `http://<this machine>:4242`.

Stop everything: `docker compose -f compose.dev.yml down`. The seed leaves `catalog/devtv/`,
`confs/devtv.json` and `runtime/` in your checkout (all git-ignored); delete them to start over.
