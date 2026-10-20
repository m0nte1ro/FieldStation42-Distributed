#!/usr/bin/env bash
# Installs a FieldStation42 client on this machine (Raspberry Pi OS, Debian, Ubuntu, Mint).
# Needs: sudo apt install mpv python3-venv python3-tk
set -e
cd "$(dirname "$0")/../.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

for cmd in python3 mpv; do
  if ! command -v "$cmd" > /dev/null; then
    echo -e "${RED}$cmd is missing - run: sudo apt install mpv python3-venv python3-tk${NC}"
    exit 1
  fi
done

echo -e "${GREEN}Creating the Python environment in env/${NC}"
python3 -m venv env
. env/bin/activate
pip install --upgrade pip > /dev/null

failed=""
while IFS= read -r package || [ -n "$package" ]; do
  [[ -z "$package" || "$package" =~ ^[[:space:]]*# ]] && continue
  pip install "$package" || failed="$failed $package"
done < client/requirements.txt
[ -n "$failed" ] && echo -e "${YELLOW}Could not install:$failed (evdev only matters for IR/keyboard remotes)${NC}"

web_pages=false
read -p "Enable web channels and live autobumps? Installs a browser engine (~300 MB). (y/N): " web
if [[ "$web" =~ ^[Yy]$ ]]; then
  pip install -r client/requirements-web.txt && web_pages=true
fi

mkdir -p runtime confs catalog
for f in static.mp4 standby.png brb.png off_air_pattern.mp4 signoff.mp4; do
  [ -e "runtime/$f" ] || cp "docs/$f" "runtime/$f"
done

# the server, the picture's look and the OSD style; Enter keeps what an existing client.json has
python3 client/platform/setup_client.py client.json "$web_pages"

argon=false
read -p "Argon ONE case with the Argon IR remote? (y/N): " argon_case
if [[ "$argon_case" =~ ^[Yy]$ ]]; then
  sudo apt-get install -y ir-keytable
  # the remote controller reads the receiver through /dev/input
  sudo usermod -aG input "$USER"
  sudo env/bin/python3 -m client.platform.argon_remote setup && argon=true
fi

echo ""
echo -e "${GREEN}Installed.${NC} Start it by hand with: env/bin/python3 -m client.main"
[ "$web_pages" = true ] && echo "On a Raspberry Pi, web pages also need: sudo bash client/platform/web_reqs.sh"
read -p "Start the client on boot (systemd user services)? (Y/n): " services
if [[ ! "$services" =~ ^[Nn]$ ]]; then
  bash client/platform/install_services.sh
fi
if [ "$argon" = true ]; then
  echo ""
  echo -e "${YELLOW}Argon remote: reboot, then teach it the buttons with${NC}"
  echo "  sudo env/bin/python3 -m client.platform.argon_remote learn"
  echo "and make sure fs42-remote-controller.service is enabled."
fi
