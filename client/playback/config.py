import json
import os

CLIENT_CONFIG_PATH = "client.json"
# how the picture looks: a GPU shader mpv runs over every frame (client/playback/looks/<look>.glsl)
LOOKS = ("original", "broadcast", "crt")


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
    # fs42 start --look wins over client.json
    config["look"] = os.environ.get("FS42_LOOK") or config.get("look", "broadcast")
    if config["look"] not in LOOKS:
        raise SystemExit(f"look must be one of {', '.join(LOOKS)}, not {config['look']!r}")
    return config


def prepare_station_loading(config):
    # the client has none of the server's media on disk, so station loading must not look for it
    from shared.stations.io import StationIO

    StationIO.check_media = False
    StationIO.excluded_types = set() if config["web_pages"] else {"web"}
