import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from server.scheduler import liquid_manager  # noqa: E402
from server.scheduler.liquid_manager import LiquidManager  # noqa: E402


class FakeTable:
    """The liquid_blocks table as the CLI, the console's build workers and the server all see it."""

    def __init__(self):
        self.blocks = {"Toons": []}
        self.writes = 0
        self.loads = 0

    def signature(self):
        return (sum(len(b) for b in self.blocks.values()), self.writes)

    def get_blocks(self, conf):
        self.loads += 1
        return list(self.blocks[conf["network_name"]])

    def build(self, name, blocks):
        # another process (the CLI) writes a schedule
        self.blocks[name] = blocks
        self.writes += 1


@pytest.fixture
def table(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(liquid_manager.LiquidAPI, "signature", fake.signature, raising=False)
    monkeypatch.setattr(liquid_manager.LiquidAPI, "get_blocks", fake.get_blocks)
    stations = MagicMock()
    stations.return_value.stations = [{"network_name": "Toons", "network_type": "standard"}]
    monkeypatch.setattr(liquid_manager, "StationManager", stations)
    return fake


def _started_server():
    manager = LiquidManager.__new__(LiquidManager)
    manager.reload_schedules()
    return manager


def test_a_schedule_built_by_the_cli_shows_up_without_a_restart(table):
    manager = _started_server()
    assert manager.get_summary_json("Toons") == {"network_id": "Toons", "start": None, "end": None}

    block = MagicMock()
    block.start_time.isoformat.return_value = "2026-10-19T14:00:00"
    block.end_time.isoformat.return_value = "2026-10-19T14:30:00"
    table.build("Toons", [block])

    assert manager.get_summary_json("Toons")["start"] == "2026-10-19T14:00:00"
    assert manager.get_schedule_by_name("Toons") == [block]


def test_an_unchanged_schedule_is_not_read_again(table):
    manager = _started_server()
    manager.get_summary_json("Toons")
    manager.get_schedule_by_name("Toons")
    assert table.loads == 1
