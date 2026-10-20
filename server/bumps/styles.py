import datetime
import json
import os

# Clients pick an OSD style; their bumps are rendered to match it (the bump page's variation of the
# same name). Only the styles clients have asked for lately are rendered, plus the station's own look
# for clients that send none.

STYLES = ("vcr", "cable", "kids")
# outside runtime/bumps, which /client/version watches: noting a style must not make clients resync
STYLES_FILE = "runtime/bump_styles.json"
KEEP_DAYS = 30
_STATION = "station"


def _load():
    try:
        with open(STYLES_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def note_style(style, today=None):
    """Record that a client asked for this style (None: the station's look). True when it's new."""
    today = (today or datetime.date.today()).isoformat()
    key = style or _STATION
    seen = _load()
    if seen.get(key) == today:
        return False
    new = key not in seen
    seen[key] = today
    os.makedirs(os.path.dirname(STYLES_FILE), exist_ok=True)
    with open(STYLES_FILE, "w") as f:
        json.dump(seen, f)
    return new


def styles_in_use(today=None):
    """The styles to render: asked for in the last KEEP_DAYS days; None stands for the station's look."""
    today = today or datetime.date.today()
    recent = [key for key, day in _load().items()
              if (today - datetime.date.fromisoformat(day)).days <= KEEP_DAYS]
    if not recent:
        return [None]
    return [None] * (_STATION in recent) + sorted(k for k in recent if k != _STATION)
