import json
import os

CLIENT_CONFIG_PATH = "client.json"


def load_client_config(path=CLIENT_CONFIG_PATH):
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found - run client/platform/install.sh or copy client.example.json")
    with open(path) as f:
        config = json.load(f)
    if not config.get("server_url"):
        raise ValueError(f"{path} must set server_url, e.g. http://homelab:4242")
    config["server_url"] = config["server_url"].rstrip("/")
    config.setdefault("media", {"method": "http"})
    config.setdefault("main_config", {})
    return config


def prepare_station_loading():
    # the client has none of the server's media on disk, so station loading must not look for it
    from shared.stations.io import StationIO

    StationIO.check_media = False
