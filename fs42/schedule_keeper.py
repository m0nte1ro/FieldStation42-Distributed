import logging
import multiprocessing
import threading
import time

from fs42.live_schedule_agent import LiveScheduleAgent

# boxes never build schedules, so the server keeps every channel scheduled ahead on its own
DEFAULT_AGENT_CONF = {"trigger_add_at": "day", "amount_to_add": "week"}


def start_schedule_keeper(agent_conf, interval=60):
    def keep():
        log = logging.getLogger("ScheduleKeeper")
        agent = LiveScheduleAgent(agent_conf or DEFAULT_AGENT_CONF, multiprocessing.Lock())
        while True:
            try:
                agent.tick()
            except Exception as e:
                log.error(f"Schedule keeper tick failed: {e}")
            time.sleep(interval)

    thread = threading.Thread(target=keep, name="schedule-keeper", daemon=True)
    thread.start()
    return thread
