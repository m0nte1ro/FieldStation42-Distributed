import contextlib
import fcntl
import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("ffmpeg", MagicMock())
sys.modules.setdefault("moviepy", MagicMock())
sys.modules.setdefault("moviepy.editor", MagicMock())

from fs42 import liquid_schedule  # noqa: E402
from fs42.liquid_schedule import LiquidSchedule  # noqa: E402
from fs42.schedule_lock import schedule_write_lock  # noqa: E402


def test_second_writer_is_blocked_while_lock_is_held(tmp_path):
    lock = tmp_path / "runtime" / "schedule.lock"
    with schedule_write_lock(str(lock)):
        with open(lock) as other, pytest.raises(BlockingIOError):
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_lock_is_released_after_the_block(tmp_path):
    lock = tmp_path / "schedule.lock"
    with schedule_write_lock(str(lock)):
        pass
    with open(lock) as other:
        fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _recording_lock(events):
    @contextlib.contextmanager
    def lock():
        events.append("enter")
        yield
        events.append("exit")

    return lock


def test_adding_time_runs_under_the_lock(monkeypatch):
    events = []
    monkeypatch.setattr(liquid_schedule, "schedule_write_lock", _recording_lock(events))
    schedule = LiquidSchedule.__new__(LiquidSchedule)
    schedule.conf = {"network_type": "streaming"}
    schedule._blocks = []
    schedule._load_blocks = lambda: events.append("load")
    schedule._increment = lambda amount: events.append(amount)
    schedule.add_days(2)
    assert events == ["enter", "load", "day", "day", "exit"]


def test_reset_schedule_deletes_under_the_lock(monkeypatch):
    from fs42 import liquid_manager
    from fs42.liquid_manager import LiquidManager

    events = []
    monkeypatch.setattr(liquid_manager, "schedule_write_lock", _recording_lock(events))
    monkeypatch.setattr(liquid_manager.LiquidAPI, "delete_blocks", lambda conf: events.append("delete"))
    manager = LiquidManager.__new__(LiquidManager)
    manager.reset_sequences = lambda conf: events.append("sequences")
    manager.reload_schedules = lambda: events.append("reload")
    manager.reset_schedule({"_has_schedule": True, "network_name": "Toons"})
    assert events == ["enter", "sequences", "delete", "exit", "reload"]
