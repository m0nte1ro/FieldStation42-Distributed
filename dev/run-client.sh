#!/usr/bin/env bash
# Starts a client inside the dev container, against the server running in it:
#   docker compose -f compose.dev.yml exec dev bash dev/run-client.sh        # the player
#   docker compose -f compose.dev.yml exec dev bash dev/run-client.sh osd    # its OSD
# The client keeps its own data in /tmp/fs42-client, apart from the server's confs/ and runtime/.
set -e
data="${FS42_CLIENT_DIR:-/tmp/fs42-client}"
mkdir -p "$data/runtime" "$data/confs" "$data/catalog"
for f in static.mp4 standby.png brb.png off_air_pattern.mp4 signoff.mp4; do
  [ -e "$data/runtime/$f" ] || cp "/app/docs/$f" "$data/runtime/$f"
done
[ -f "$data/client.json" ] || cat > "$data/client.json" <<'JSON'
{
  "server_url": "http://localhost:4242",
  "local_api_port": 4243,
  "web_pages": true,
  "media": {"method": "http"},
  "main_config": {}
}
JSON
cd "$data"
export PYTHONPATH=/app
if [ "$1" = "osd" ]; then
  exec python3 -m client.osd.main
fi
exec python3 -m client.main "$@"
