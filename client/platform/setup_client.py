"""Asks how this TV should work and writes its client.json, keeping anything else already in it.

    python3 client/platform/setup_client.py client.json     # what fs42 setup and install.sh run

Standard library only, so it runs on any machine with Python 3, without the client's packages.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from client.playback.config import LOOKS, OSD_STYLES, RESOLUTIONS  # noqa: E402

DESCRIPTIONS = {
    "original": "the picture as it is",
    "broadcast": "light scanlines and softness, like a 90s broadcast",
    "crt": "a curved CRT tube with a phosphor grille (the heaviest on the GPU)",
    "native": "every file at its own resolution",
    "576": "at most 576 lines, like PAL TV: shows and cartoons look alike",
    "480": "at most 480 lines, like NTSC TV: softer still",
    "vcr": "green terminal text, like a VCR menu",
    "cable": "a dark box with channel, name and programme, like a 90s cable box",
    "kids": "round and colourful, like a kids' channel",
}
# the default may depend on earlier answers: the retro looks suggest PAL's 576 lines, original none
QUESTIONS = [
    ("look", "Picture look", LOOKS, lambda config: "broadcast"),
    ("resolution", "Resolution ceiling", RESOLUTIONS, lambda config: "native" if config["look"] == "original" else "576"),
    ("osd_style", "On-screen display", OSD_STYLES, lambda config: "vcr"),
]


def _choose(title, options, current, input, print):
    print(f"\n{title}:")
    for i, option in enumerate(options, 1):
        print(f"  {i}) {option:<10} {DESCRIPTIONS[option]}{'  [current]' if option == current else ''}")
    while True:
        answer = input(f"Choose 1-{len(options)} (Enter keeps {current}): ").strip()
        if not answer:
            return current
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print(f"  Please answer a number from 1 to {len(options)}.")


def _access_token(config, input, print):
    current = config.get("server_headers", {}).get("CF-Access-Client-Id")
    print("\nCloudflare Access service token - only when the server is reached through Cloudflare Access:")
    client_id = input(f"Client ID (Enter {'keeps ' + current if current else 'skips'}): ").strip()
    if client_id:
        secret = input("Client Secret: ").strip()
        config["server_headers"] = {"CF-Access-Client-Id": client_id, "CF-Access-Client-Secret": secret}


def setup(path, input=input, print=print, web_pages=None):
    config = {}
    if os.path.exists(path) and not os.path.isdir(path):
        with open(path) as f:
            config = json.load(f)
    current = config.get("server_url")
    while True:
        prompt = f"Server URL (Enter keeps {current}): " if current else "Server URL, e.g. http://homelab:4242: "
        answer = input(prompt).strip() or current
        if answer:
            config["server_url"] = answer.rstrip("/")
            break
    for key, title, options, default in QUESTIONS:
        config[key] = _choose(title, options, config.get(key, default(config)), input, print)
    _access_token(config, input, print)
    if web_pages is not None:
        config["web_pages"] = web_pages
    config.setdefault("media", {"method": "http"})
    config.setdefault("main_config", {})
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(f"\nSaved {path}. Restart the client for the changes to show.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    web = {"true": True, "false": False}.get(sys.argv[2]) if len(sys.argv) > 2 else None
    setup(sys.argv[1], web_pages=web)
