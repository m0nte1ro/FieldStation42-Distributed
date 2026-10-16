import json
import os

from shared.rundown import ScheduleNotFound, block_at, decode_rundown, play_point

RUNDOWN_PATH = "runtime/rundown.json"

# the synced rundown, loaded by the player (and inherited by its guide and overlay processes)
schedules = {}
metadata = {}


def load(path=RUNDOWN_PATH):
    global schedules, metadata
    if not os.path.exists(path):
        schedules, metadata = {}, {}
        return
    with open(path) as f:
        data = json.load(f)
    schedules = decode_rundown(data)
    metadata = data.get("meta", {})


def blocks(network_name):
    return schedules.get(network_name, [])


def programming_block(network_name, when):
    return block_at(blocks(network_name), when)


def station_play_point(station_conf, when):
    return play_point(station_conf, blocks(station_conf["network_name"]), when)


def meta(path):
    return metadata.get(path)


__all__ = ["RUNDOWN_PATH", "ScheduleNotFound", "load", "blocks", "programming_block", "station_play_point", "meta"]
