import hashlib
import json
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
        # one loop for any gap length; the client loops it and draws the countdown
        kind = "filler"
        params.update(countdown="false", duration=str(FILLER_SECONDS * 1000))
    else:
        kind = "next_up" if "next_title" in params else "message"

    seconds = int(params.get("duration") or DEFAULT_SECONDS * 1000) / 1000
    key = hashlib.sha1((kind + json.dumps(sorted(params.items()), ensure_ascii=False)).encode()).hexdigest()[:16]
    return RenderJob(kind, key, params, seconds, loop=filler, countdown=filler)
