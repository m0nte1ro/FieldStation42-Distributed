import json
import os

CLIENT_CONFIG_PATH = "client.json"
# how the picture looks: a GPU shader mpv runs over every frame (client/playback/looks/<look>.glsl)
LOOKS = ("original", "broadcast", "crt")
# the most lines a picture keeps before it's scaled to the screen (client/playback/looks/ceiling-<n>.glsl):
# 576 is PAL, 480 NTSC; "native" keeps the file's own
RESOLUTIONS = ("native", "576", "480")
# how the OSD (channel, volume, mute) is drawn: client/osd/styles.py
OSD_STYLES = ("vcr", "cable", "kids")


def load_client_config(path=CLIENT_CONFIG_PATH):
    if os.path.isdir(path):
        # a Docker bind mount of a missing file creates an empty directory in its place
        raise SystemExit(f"{path} is a directory, not a file - remove it and copy client.example.json to {path}")
    if not os.path.isfile(path):
        raise SystemExit(f"{path} not found - run client/platform/install.sh or copy client.example.json")
    with open(path) as f:
        config = json.load(f)
    if not config.get("server_url"):
        raise ValueError(f"{path} must set server_url, e.g. http://homelab:4242")
    config["server_url"] = config["server_url"].rstrip("/")
    config.setdefault("media", {"method": "http"})
    config.setdefault("main_config", {})
    # set when the server runs on the same machine and already owns its port
    config.setdefault("local_api_port", None)
    # web channels and live autobumps need a browser (QtWebEngine); off unless the client has it
    config.setdefault("web_pages", False)
    # mpv's hardware decoding: auto-safe uses the GPU wherever that is known to work, else the CPU
    config.setdefault("hwdec", "auto-safe")
    # sent with every request to the server, e.g. a Cloudflare Access service token
    # ({"CF-Access-Client-Id": ..., "CF-Access-Client-Secret": ...})
    config.setdefault("server_headers", {})
    headers = config["server_headers"]
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise SystemExit(f"server_headers in {path} must map header names to values")
    # fs42 start --look wins over client.json
    config["look"] = os.environ.get("FS42_LOOK") or config.get("look", "broadcast")
    if config["look"] not in LOOKS:
        raise SystemExit(f"look must be one of {', '.join(LOOKS)}, not {config['look']!r}")
    # fs42 start --resolution wins; unset, the retro looks get PAL's 576 lines and original the file's own
    config["resolution"] = str(os.environ.get("FS42_RESOLUTION") or config.get("resolution")
                               or ("native" if config["look"] == "original" else "576"))
    if config["resolution"] not in RESOLUTIONS:
        raise SystemExit(f"resolution must be one of {', '.join(RESOLUTIONS)}, not {config['resolution']!r}")
    # fs42 start --osd wins over client.json
    config["osd_style"] = os.environ.get("FS42_OSD") or config.get("osd_style", "vcr")
    if config["osd_style"] not in OSD_STYLES:
        raise SystemExit(f"osd_style must be one of {', '.join(OSD_STYLES)}, not {config['osd_style']!r}")
    return config


def prepare_station_loading(config):
    # the client has none of the server's media on disk, so station loading must not look for it
    from shared.stations.io import StationIO

    StationIO.check_media = False
    StationIO.excluded_types = set() if config["web_pages"] else {"web"}
