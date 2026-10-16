import datetime
import glob
import hashlib
import json
import mimetypes
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from fs42.box.rundown import build_rundown
from fs42.media_processor import MediaProcessor
from fs42.station_manager import StationManager

router = APIRouter(prefix="/box", tags=["box"])

IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
MEDIA_KEYS = ("sign_off_video", "off_air_video", "be_right_back_media", "standby_image", "off_air_image")


def _files_under(path):
    found = []
    for root, dirs, files in os.walk(path, followlinks=True):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found.extend(os.path.join(root, f) for f in files if not f.startswith("."))
    return found


def _expand(value):
    values = value if isinstance(value, list) else [value]
    paths = []
    for item in values:
        if isinstance(item, str):
            paths.extend(_files_under(item) if os.path.isdir(item) else [item])
    return paths


def file_manifest(stations, confs_dir="confs"):
    candidates = glob.glob(os.path.join(confs_dir, "*.json"))
    for station in stations:
        for key in ("standby_image", "off_air_image", "images", "sound_to_play"):
            if key in station:
                candidates.extend(_expand(station[key]))
        if station.get("content_dir") and station.get("logo_dir"):
            candidates.extend(_files_under(os.path.join(station["content_dir"], station["logo_dir"])))

    manifest = {}
    for path in candidates:
        path = os.path.normpath(path)
        if path not in manifest and os.path.isfile(path):
            stat = os.stat(path)
            manifest[path] = {"path": path, "size": stat.st_size, "mtime": stat.st_mtime}
    return [manifest[p] for p in sorted(manifest)]


def compute_version(db_path, manifest):
    try:
        with sqlite3.connect(db_path) as conn:
            count, max_id = conn.execute("SELECT count(*), max(id) FROM liquid_blocks").fetchone()
    except sqlite3.Error:
        count, max_id = 0, 0
    digest = hashlib.sha1(f"{count}:{max_id or 0}".encode())
    digest.update(json.dumps(manifest, sort_keys=True).encode())
    return digest.hexdigest()


def _is_under(path, root):
    root = os.path.normpath(root)
    return path == root or path.startswith(root + os.sep)


def media_allowed(path, stations):
    if not path or "\x00" in path or ".." in Path(path).parts:
        return False
    norm = os.path.normpath(path)
    extension = os.path.splitext(norm)[1].lower().lstrip(".")
    if extension not in MediaProcessor.supported_formats and extension not in IMAGE_FORMATS:
        return False
    if _is_under(norm, "runtime"):
        return True
    for station in stations:
        if station.get("content_dir") and _is_under(norm, station["content_dir"]):
            return True
        if any(isinstance(station.get(k), str) and norm == os.path.normpath(station[k]) for k in MEDIA_KEYS):
            return True
    return False


def _state():
    manager = StationManager()
    manifest = file_manifest(manager.stations)
    return manager, manifest, compute_version(manager.server_conf["db_path"], manifest)


@router.get("/version")
def get_version():
    _, _, version = _state()
    return {"version": version, "server_time": datetime.datetime.now().isoformat()}


@router.get("/rundown")
def get_rundown(hours: int = 24):
    manager, _, version = _state()
    rundown = build_rundown(manager.stations, datetime.datetime.now(), hours)
    rundown["version"] = version
    return rundown


@router.get("/files")
def get_files():
    return file_manifest(StationManager().stations)


@router.get("/file")
def get_file(path: str):
    if path not in {f["path"] for f in file_manifest(StationManager().stations)}:
        raise HTTPException(status_code=404, detail="not a box file")
    return FileResponse(path)


@router.get("/media")
def get_media(path: str):
    if not media_allowed(path, StationManager().stations):
        raise HTTPException(status_code=403, detail="not a media path")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="media not found")
    media_type, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=media_type or "application/octet-stream")
