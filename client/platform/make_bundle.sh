#!/usr/bin/env bash
# Builds fs42-client-<version>.tar.gz: what a native client (a Raspberry Pi) needs, nothing of the
# server. Usage: make_bundle.sh [version] [output dir]   (defaults: dev, dist/)
set -e
cd "$(dirname "$0")/../.."
version="${1:-dev}"
out_dir="${2:-dist}"
stage="$(mktemp -d)"
root="$stage/fs42-client"

mkdir -p "$root/docs" "$out_dir"
cp -r client shared "$root/"
cp docs/static.mp4 docs/standby.png docs/brb.png docs/off_air_pattern.mp4 docs/signoff.mp4 "$root/docs/"
cp client.example.json LICENSE "$root/"
cat > "$root/README.md" <<'TEXT'
# FieldStation42 client

Plays the channels of a FieldStation42 server. On a Raspberry Pi (64-bit Pi OS) or any Linux PC:

    sudo apt install mpv python3-venv python3-tk
    bash client/platform/install.sh

The installer asks for the server URL (e.g. http://homelab:4242) and offers to start the client on
boot. Settings live in client.json; see client.example.json and the project README:
https://github.com/m0nte1ro/FieldStation42-Distributed
TEXT
find "$root" -name "__pycache__" -prune -exec rm -rf {} +
rm -f "$root/client/osd/osd.json" "$root/client/client.json"

out="$out_dir/fs42-client-$version.tar.gz"
tar -czf "$out" -C "$stage" fs42-client
rm -rf "$stage"
echo "$out"
