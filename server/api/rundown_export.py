import datetime

from server.catalog.metadata_io import MetadataIO
from server.scheduler.liquid_io import LiquidIO

# Encodes the server's Liquid blocks into the rundown JSON that clients decode with
# shared.rundown.decode_rundown.

_CONTENT_FIELDS = ("path", "title", "tag", "duration", "content_type", "media_type")


def _content_to_json(content):
    if content is None:
        return None
    if isinstance(content, list):
        return [_content_to_json(c) for c in content]
    return {field: getattr(content, field) for field in _CONTENT_FIELDS}


def block_to_json(block):
    return {
        "liquid_type": type(block).__name__,
        "start_time": block.start_time.isoformat(),
        "end_time": block.end_time.isoformat(),
        "title": block.title,
        "break_strategy": block.break_strategy,
        "break_info": block.break_info,
        "sequence_key": block.sequence_key,
        "content": _content_to_json(block.content),
        "plan": [entry.toJSON() for entry in block.plan],
    }


def _content_paths(content):
    if content is None:
        return []
    if isinstance(content, list):
        return [c.path for c in content]
    return [content.path]


def build_rundown(stations, now, hours):
    end = now + datetime.timedelta(hours=hours)
    liquid = LiquidIO()
    by_station = {}
    paths = set()
    for station in stations:
        if station["network_type"] in ("guide", "streaming"):
            continue
        blocks = liquid.query_liquid_blocks(station["network_name"], str(now), str(end))
        by_station[station["network_name"]] = [block_to_json(b) for b in blocks]
        for block in blocks:
            paths.update(_content_paths(block.content))
            paths.update(entry.path for entry in block.plan)
    local_paths = sorted(p for p in paths if "://" not in p)
    return {
        "server_time": now.isoformat(),
        "stations": by_station,
        "meta": MetadataIO.read_many(local_paths),
    }
