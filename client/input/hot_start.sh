#!/usr/bin/env bash
# Starts the player and the Pico/UART remote bridge without systemd.
cd "$(dirname "$0")/../.." || exit 1
. env/bin/activate

python3 -m client.main 1>/dev/null 2>/dev/null & disown
python3 -m client.input.uart_bridge 1>/dev/null 2>/dev/null & disown
