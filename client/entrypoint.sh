#!/bin/sh
# confs/, catalog/ and runtime/ are volumes holding what the client synced from the server
set -e
mkdir -p confs catalog runtime
for f in /defaults/runtime/*; do
  [ -e "runtime/$(basename "$f")" ] || cp -r "$f" runtime/
done
exec "$@"
