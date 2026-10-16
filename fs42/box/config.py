import json
import os

BOX_CONFIG_PATH = "box.json"


def is_box():
    return os.path.exists(BOX_CONFIG_PATH)


def load_box_config(path=BOX_CONFIG_PATH):
    with open(path) as f:
        config = json.load(f)
    if not config.get("server_url"):
        raise ValueError(f"{path} must set server_url, e.g. http://homelab:4242")
    config["server_url"] = config["server_url"].rstrip("/")
    config.setdefault("media", {"method": "http"})
    config.setdefault("main_config", {})
    return config
