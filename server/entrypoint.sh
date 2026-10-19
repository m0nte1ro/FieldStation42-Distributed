#!/bin/sh
# confs/, catalog/ and runtime/ are volumes; on a fresh install they start empty
set -e
mkdir -p confs catalog runtime
for f in /defaults/runtime/*; do
  [ -e "runtime/$(basename "$f")" ] || cp -r "$f" runtime/
done
exec "$@"
