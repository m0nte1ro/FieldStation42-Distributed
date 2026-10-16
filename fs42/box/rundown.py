import datetime
import json
import os

from fs42.block_plan import BlockPlanEntry
from fs42.catalog_entry import CatalogEntry
from fs42.liquid_io import LiquidIO
from fs42.metadata_io import MetadataIO

RUNDOWN_PATH = "runtime/rundown.json"

# metadata of every path in the loaded rundown, read by MetadataIO on a box
META = {}

_CONTENT_FIELDS = ("path", "title", "tag", "duration", "content_type", "media_type")


def _content_to_json(content):
    if content is None:
        return None
    if isinstance(content, list):
        return [_content_to_json(c) for c in content]
    return {field: getattr(content, field) for field in _CONTENT_FIELDS}


def _content_from_json(data):
    if data is None:
        return None
    if isinstance(data, list):
        return [_content_from_json(c) for c in data]
    entry = CatalogEntry(data["path"], data["duration"], data["tag"], [], 0, data["content_type"], data["media_type"])
    entry.title = data["title"]
    return entry


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


def block_from_json(data):
    block = LiquidIO._block_factory(data["liquid_type"], (
        _content_from_json(data["content"]),
        datetime.datetime.fromisoformat(data["start_time"]),
        datetime.datetime.fromisoformat(data["end_time"]),
        data["title"],
        data["break_strategy"],
        data["break_info"],
    ))
    block.sequence_key = data["sequence_key"]
    block.plan = [BlockPlanEntry(p["path"], p["skip"], p["duration"], p["is_stream"], p["content_type"], p["media_type"])
                  for p in data["plan"]]
    return block


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


def load_rundown(path=RUNDOWN_PATH):
    global META
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        data = json.load(f)
    META = data.get("meta", {})
    return {name: [block_from_json(b) for b in blocks] for name, blocks in data["stations"].items()}


def box_meta(path):
    return META.get(path)
