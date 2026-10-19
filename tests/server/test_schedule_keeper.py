import time

from server.scheduler import schedule_keeper
from server.scheduler.schedule_keeper import start_schedule_keeper


class FakeAgent:
    instances = []

    def __init__(self, conf, lock, fail_first=False):
        self.conf = conf
        self.ticks = 0
        self.fail_first = fail_first
        FakeAgent.instances.append(self)

    def tick(self):
        self.ticks += 1
        if self.fail_first and self.ticks == 1:
            raise RuntimeError("database is locked")


def _wait_for_ticks(count):
    deadline = time.time() + 1
    while time.time() < deadline:
        if FakeAgent.instances and FakeAgent.instances[-1].ticks >= count:
            return FakeAgent.instances[-1]
        time.sleep(0.005)
    raise AssertionError("keeper did not tick")


def test_keeper_uses_defaults_and_ticks(monkeypatch):
    FakeAgent.instances = []
    monkeypatch.setattr(schedule_keeper, "LiveScheduleAgent", FakeAgent)
    start_schedule_keeper(None, interval=0.01)
    agent = _wait_for_ticks(2)
    assert agent.conf == {"trigger_add_at": "day", "amount_to_add": "week"}


def test_keeper_uses_configured_agent_settings(monkeypatch):
    FakeAgent.instances = []
    monkeypatch.setattr(schedule_keeper, "LiveScheduleAgent", FakeAgent)
    start_schedule_keeper({"trigger_add_at": "week", "amount_to_add": "month"}, interval=0.01)
    assert _wait_for_ticks(1).conf == {"trigger_add_at": "week", "amount_to_add": "month"}


def test_keeper_survives_a_failing_tick(monkeypatch):
    FakeAgent.instances = []
    monkeypatch.setattr(schedule_keeper, "LiveScheduleAgent",
                        lambda conf, lock: FakeAgent(conf, lock, fail_first=True))
    start_schedule_keeper(None, interval=0.01)
    _wait_for_ticks(2)
