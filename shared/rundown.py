class BlockPlanEntry:
    def __init__(self, the_path, skip=0, duration=-1, is_stream=False, content_type="feature", media_type="video"):
        self.path = the_path
        self.skip = skip
        self.duration = duration
        self.is_stream = is_stream
        self.content_type = content_type
        self.media_type = media_type

    def toJSON(self):
        return {"path": self.path, "skip": self.skip, "duration": self.duration, "is_stream": self.is_stream, "content_type": self.content_type, "media_type": self.media_type}

    def __str__(self):
        return f"PlanEntry: {self.path} skip={self.skip} duration={self.duration}"


# The rundown is the contract between the server and its clients: blocks with absolute times and
# a plan of entries (path, skip, duration). Both ends work out what plays at a time the same way.

import datetime  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

AUTOBUMP_PREFIX = ":autobump:="


def is_autobump_url(path):
    return path.startswith(AUTOBUMP_PREFIX)


def strip_autobump(path):
    return path[len(AUTOBUMP_PREFIX):] if is_autobump_url(path) else path


class ScheduleQueryNotInBounds(Exception):
    pass


class ScheduleNotFound(Exception):
    pass


class PlayPoint:
    def __init__(self, index, offset, plan, block_title="Unknown"):
        self.index = index
        self.offset = offset
        self.plan: BlockPlanEntry = plan
        self.block_title = block_title

    def __str__(self):
        return f"PlayPoint: title={self.block_title} index={self.index} offet={self.offset} plan_len={len(self.plan)}"


@dataclass
class Content:
    path: str
    title: str
    tag: str
    duration: float
    content_type: str = "feature"
    media_type: str = "video"


@dataclass
class Block:
    liquid_type: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    title: str
    plan: list
    content: object = None
    break_strategy: str = "standard"
    break_info: dict = field(default_factory=dict)
    sequence_key: dict = None


def block_at(blocks, when):
    if not blocks:
        raise ScheduleNotFound("No schedule")
    start, end = blocks[0].start_time, blocks[-1].end_time
    if start > when or end < when:
        raise ScheduleQueryNotInBounds(f"Query for programming at {when} fails because schedule is from {start} to {end}")
    for block in blocks:
        if block.start_time <= when <= block.end_time:
            return block


def _stream_point(station_conf):
    plan = [
        BlockPlanEntry(s["url"], 0, s["duration"], is_stream=True, content_type="stream", media_type=s.get("media_type", "video"))
        for s in station_conf["streams"]
    ]
    return PlayPoint(0, 0, plan)


def play_point(station_conf, blocks, when):
    if station_conf["network_type"] == "streaming":
        return _stream_point(station_conf)

    block = block_at(blocks, when)
    index = 0
    current_mark = block.start_time
    for entry in block.plan:
        next_mark = current_mark + datetime.timedelta(seconds=entry.duration)
        if next_mark > when:
            return PlayPoint(index, (when - current_mark).total_seconds(), block.plan, block.title)
        current_mark = next_mark
        index += 1

    # the plan ran out before the block did - cover the gap with be right back media if the station has it
    gap = (block.end_time - when).total_seconds()
    brb = station_conf.get("be_right_back_media")
    if brb and gap > 0:
        return PlayPoint(0, 0, [BlockPlanEntry(brb, 0, gap, content_type="bump")], block.title)
    return None


def _content(data):
    if data is None:
        return None
    if isinstance(data, list):
        return [_content(c) for c in data]
    return Content(data["path"], data["title"], data["tag"], data["duration"], data["content_type"], data["media_type"])


def decode_block(data):
    return Block(
        liquid_type=data["liquid_type"],
        start_time=datetime.datetime.fromisoformat(data["start_time"]),
        end_time=datetime.datetime.fromisoformat(data["end_time"]),
        title=data["title"],
        plan=[BlockPlanEntry(p["path"], p["skip"], p["duration"], p["is_stream"], p["content_type"], p["media_type"])
              for p in data["plan"]],
        content=_content(data["content"]),
        break_strategy=data["break_strategy"],
        break_info=data["break_info"] or {},
        sequence_key=data["sequence_key"],
    )


def decode_rundown(data):
    return {name: [decode_block(b) for b in blocks] for name, blocks in data["stations"].items()}
