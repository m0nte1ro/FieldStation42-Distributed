from urllib.parse import quote

from fs42.autobump_agent import AutoBumpAgent


def media_location(path, config):
    # stream URLs and autobump pages already say where to go; everything else is a server path
    if "://" in path or AutoBumpAgent.is_autobump_url(path):
        return path
    media = config["media"]
    if media["method"] == "mount":
        return f"{media['root'].rstrip('/')}/{path.lstrip('/')}"
    return f"{config['server_url']}/box/media?path={quote(path, safe='')}"
