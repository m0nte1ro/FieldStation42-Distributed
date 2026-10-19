import datetime
import logging
import os
import threading
import time

from server.bumps.jobs import plan_jobs
from server.bumps.renderer import render as render_job
from server.scheduler.liquid_io import LiquidIO
from shared.stations.manager import StationManager

# Renders the autobumps the next day of schedule needs, once each, so clients only ever play clips.

_log = logging.getLogger("BumpKeeper")
_scan_lock = threading.Lock()
_wake = threading.Event()
_keeper_running = False


def pending_jobs(stations, now, hours=24):
    end = now + datetime.timedelta(hours=hours)
    liquid = LiquidIO()
    jobs = {}
    for station in stations:
        if station["network_type"] in ("guide", "streaming"):
            continue
        blocks = liquid.query_liquid_blocks(station["network_name"], str(now), str(end))
        for i, block in enumerate(blocks):
            following = blocks[i + 1].title if i + 1 < len(blocks) else None
            for _, job in plan_jobs(block.plan, block.title, following):
                if job.key not in jobs and not os.path.exists(job.path):
                    jobs[job.key] = job
    return list(jobs.values())


def _render_here(job):
    return render_job(job, f"http://127.0.0.1:{StationManager().server_conf['server_port']}")


def scan_once(stations, render=_render_here, now=None):
    # one scan at a time, so a job is never rendered twice
    with _scan_lock:
        rendered = 0
        for job in pending_jobs(stations, now or datetime.datetime.now()):
            try:
                render(job)
                rendered += 1
                _log.info(f"Rendered {job.kind} bump {job.key}")
            except Exception as e:
                _log.error(f"Rendering {job.kind} bump {job.key} failed, retrying next scan: {e}")
        return rendered


def scan_now():
    return scan_once(StationManager().stations)


def _schedule_signature():
    # changes whenever a schedule is built or reset, by this process, the web console or the CLI
    return LiquidIO().signature()


def request_bump_scan():
    # after a build in this process: scan now instead of at the next poll
    _wake.set()


def start_bump_keeper(interval=300, scan=scan_now, signature=_schedule_signature, poll=30):
    global _keeper_running

    def keep():
        last_signature, last_scan = None, 0.0
        while True:
            try:
                current = signature()
            except Exception:
                current = None
            if _wake.is_set() or current != last_signature or time.monotonic() - last_scan >= interval:
                _wake.clear()
                try:
                    scan()
                except Exception as e:
                    _log.error(f"Bump scan failed: {e}")
                last_signature, last_scan = current, time.monotonic()
            _wake.wait(poll)

    _keeper_running = True
    thread = threading.Thread(target=keep, name="bump-keeper", daemon=True)
    thread.start()
    return thread
