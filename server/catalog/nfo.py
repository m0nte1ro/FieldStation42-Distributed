import os
import logging

_logger = logging.getLogger("NFOAgent")

MAX_NFO_LINES = 5


class NFOAgent:
    """Reads NFO sidecar files and shapes their metadata for listings (catalog scans, PPV)."""

    @staticmethod
    def parse_nfo_string(content):
        """Parse an NFO sidecar's contents into a normalized metadata dict.

        Handles any Kodi-format XML root tag (musicvideo, movie,
        episodedetails, tvshow, plus a generic fallback for other tags) and a
        plain-text fallback for non-XML files. Returns a dict carrying a `type`
        discriminator, or None if nothing usable could be parsed.

        Empty string fields are dropped so the stored JSON stays tidy.
        """
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            # Not XML — fall back to plain text, one field per non-empty line.
            lines = [l.strip() for l in content.splitlines() if l.strip()][:MAX_NFO_LINES]
            if not lines:
                return None
            return {"type": "plaintext", "title": lines[0], "lines": lines}

        def get(field):
            el = root.find(field)
            return el.text.strip() if el is not None and el.text else ""

        def as_int(raw):
            return int(raw) if raw.isdigit() else raw

        tag = root.tag
        if tag == "musicvideo":
            meta = {
                "type": "music",
                "title": get("title"),
                "artist": get("artist"),
                "album": get("album"),
                "year": get("year") or get("premiered")[:4],
                "genre": get("genre"),
            }
        elif tag == "movie":
            meta = {
                "type": "movie",
                "title": get("title"),
                "year": get("year") or get("premiered")[:4],
                "plot": get("plot") or get("outline"),
                "genre": get("genre"),
            }
        elif tag == "episodedetails":
            meta = {
                "type": "episode",
                "title": get("title"),
                "show_title": get("showtitle"),
                "season": as_int(get("season")),
                "episode": as_int(get("episode")),
                "aired": get("aired"),
                "plot": get("plot") or get("outline"),
            }
        elif tag == "tvshow":
            meta = {
                "type": "tvshow",
                "title": get("title"),
                "year": get("year") or get("premiered")[:4],
                "plot": get("plot") or get("outline"),
                "genre": get("genre"),
            }
        else:
            # Unknown/unsupported Kodi root tag — keep the title and any of the
            # common fields that happen to be present.
            title = get("title")
            if not title:
                return None
            meta = {"type": tag, "title": title}
            for opt in ("year", "plot", "genre"):
                opt_value = get(opt)
                if opt_value:
                    meta[opt] = opt_value

        # Drop empty-string fields; keep non-string values (e.g. int season).
        meta = {k: v for k, v in meta.items() if v != ""}

        # Require at least one real field beyond the type discriminator.
        return meta if len(meta) > 1 else None

    @staticmethod
    def read_metadata_from_disk(file_path):

        nfo_path = os.path.splitext(file_path)[0] + ".nfo"

        if not os.path.exists(nfo_path):
            return None

        try:
            with open(nfo_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            _logger.warning(f"Failed to read NFO file {nfo_path}: {e}")
            return None

        meta = NFOAgent.parse_nfo_string(content)
        if meta is None:
            _logger.warning(f"NFO file {nfo_path} could not be parsed")
        return meta

    @staticmethod
    def display_fields(meta):

        if not meta:
            return None

        meta_type = meta.get("type")
        title = str(meta.get("title", ""))

        if meta_type == "music":
            info = str(meta.get("artist", ""))
            description = str(meta.get("album", ""))
        elif meta_type == "episode":
            info = str(meta.get("show_title", ""))
            description = str(meta.get("plot", ""))
        elif meta_type == "plaintext":
            lines = meta.get("lines", [])
            if not title and lines:
                title = lines[0]
            info = lines[1] if len(lines) > 1 else ""
            description = lines[2] if len(lines) > 2 else ""
        else:  # movie, tvshow, generic
            info = str(meta.get("year", ""))
            description = str(meta.get("plot", ""))

        return {"title": title, "info": info, "description": description}
