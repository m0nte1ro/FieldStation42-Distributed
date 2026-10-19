import hashlib
import json
import logging
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from shared.rundown import is_autobump_url, strip_autobump

# An autobump is stored in plans as ":autobump:=<bump page URL>". The server renders each one to
# video once, named by what shows on screen, and swaps the clip in when it sends a rundown.

BUMP_DIR = "runtime/bumps"
FILLER_SECONDS = 30
DEFAULT_SECONDS = 7


@dataclass
class RenderJob:
    kind: str
    key: str
    params: dict
    seconds: float
    loop: bool = False
    countdown: bool = False

    @property
    def path(self):
        return f"{BUMP_DIR}/{self.key}.mp4"


def page_params(entry_path):
    return dict(parse_qsl(urlsplit(strip_autobump(entry_path)).query, keep_blank_values=True))


def job_for(entry_path, next_title=None):
    if not is_autobump_url(entry_path):
        return None
    params = page_params(entry_path)
    filler = params.get("countdown") == "true"

    if params.get("next_network"):
        # "coming up next" is rendered per show: the page shows the title it's given
        if not next_title:
            return None
        params.pop("next_network")
        params["next_title"] = next_title

    if filler:
        # one loop for any gap length; the client loops it and draws the countdown. The page gets
        # no duration, so it never fades out at the loop point.
        kind = "filler"
        params.update(countdown="false", duration="0")
        seconds = FILLER_SECONDS
    else:
        kind = "next_up" if "next_title" in params else "message"
        # fractional when the length comes from a background video (ffprobe)
        seconds = float(params.get("duration") or DEFAULT_SECONDS * 1000) / 1000
    key = hashlib.sha1((kind + json.dumps(sorted(params.items()), ensure_ascii=False)).encode()).hexdigest()[:16]
    return RenderJob(kind, key, params, seconds, loop=filler, countdown=filler)


def next_show_title(later_content_types, current_title, following_title):
    # a break inside a show leads back into that show; only the last break leads to the next one
    if any(kind not in ("bump", "commercial") for kind in later_content_types):
        return current_title
    return following_title


def _field(entry, name):
    return entry[name] if isinstance(entry, dict) else getattr(entry, name)


def plan_jobs(plan, current_title, following_title):
    """(index, job) for each autobump in a block's plan that can be rendered."""
    for i, entry in enumerate(plan):
        later = [_field(e, "content_type") for e in plan[i + 1:]]
        try:
            job = job_for(_field(entry, "path"), next_show_title(later, current_title, following_title))
        except (ValueError, KeyError) as e:
            logging.getLogger("BumpJobs").warning(f"Ignoring an autobump that can't be rendered: {e}")
            job = None
        if job:
            yield i, job
