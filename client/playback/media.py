import os
from urllib.parse import quote

from shared.rundown import is_autobump_url


def media_location(path, config):
    # stream URLs and autobump pages already say where to go; files the client has play locally
    # (standby, static, synced guide audio); everything else streams from the server
    if "://" in path or is_autobump_url(path) or os.path.exists(path):
        return path
    media = config["media"]
    if media["method"] == "mount":
        return f"{media['root'].rstrip('/')}/{path.lstrip('/')}"
    return f"{config['server_url']}/client/media?path={quote(path, safe='')}"
