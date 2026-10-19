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


def local_page_url(url, config, server_port):
    # pages stored for the client's own API (autobumps at http://127.0.0.1:<port>, localhost web
    # channels) follow it to local_api_port when the server shares this machine and its port
    port = config.get("local_api_port")
    if not port or port == server_port:
        return url
    for host in ("http://127.0.0.1", "http://localhost"):
        prefix = f"{host}:{server_port}/"
        if url.startswith(prefix):
            return f"http://127.0.0.1:{port}/" + url[len(prefix):]
    return url
