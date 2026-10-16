#!/usr/bin/env bash
# Seeds a DevTV test channel (channel 7): generated clips, its station config,
# a catalog and a day of schedule. Safe to run again: existing clips are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p runtime confs catalog/devtv/shows catalog/devtv/commercials catalog/devtv/bumps
for asset in static.mp4 standby.png brb.png off_air_pattern.mp4 signoff.mp4; do
  [ -f "runtime/$asset" ] || cp "docs/$asset" "runtime/$asset"
done

# clip <path> <seconds> <video source> <tone Hz>
clip() {
  [ -f "$1" ] && return
  echo "making $1"
  ffmpeg -loglevel error -f lavfi -i "$3=size=320x240:rate=15:duration=$2" \
    -f lavfi -i "sine=frequency=$4:duration=$2" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -shortest "$1"
}

for n in 1 2 3; do clip "catalog/devtv/shows/show$n.mp4" 240 testsrc2 $((300 + n * 100)); done
for n in 1 2 3 4; do clip "catalog/devtv/commercials/ad$n.mp4" 15 smptebars $((900 + n * 50)); done
for n in 1 2; do clip "catalog/devtv/bumps/bump$n.mp4" 5 rgbtestsrc 1500; done

cp dev/devtv.json confs/devtv.json
python3 -m server.cli -r DevTV
python3 -m server.cli -d DevTV
