import glob
import json
import logging
import os
import threading
import time
from pathlib import Path

import httpx

from client.playback import clock
from client.playback.rundown_store import RUNDOWN_PATH

MANIFEST_STATE = "runtime/client_manifest.json"
SERVER_MAIN_CONFIG = "runtime/main_config.server.json"
MAIN_CONFIG = "confs/main_config.json"

# set by the poller when new files or a new rundown are on disk; the player reloads on its next input check
reload_requested = threading.Event()
# set by the player when the rundown doesn't cover now; the poller fetches a fresh one
refresh_requested = threading.Event()

_SYNC_ERRORS = (httpx.HTTPError, OSError, ValueError)


class ClientSync:
    def __init__(self, config, root=".", client=None):
        self.config = config
        self.root = root
        self.client = client or httpx.Client(base_url=config["server_url"], timeout=10)
        self.version = None
        self._last_rundown = None
        self._l = logging.getLogger("ClientSync")

    def _path(self, relative):
        return os.path.join(self.root, relative)

    def _write(self, relative, data):
        path = self._path(relative)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def _read_json(self, relative, default):
        try:
            with open(self._path(relative)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _get(self, url, **params):
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response

    def fetch_version(self):
        data = self._get("/client/version").json()
        clock.set_server_time(data["server_time"])
        return data["version"]

    def sync_files(self):
        manifest = self._get("/client/files").json()
        known = self._read_json(MANIFEST_STATE, {})
        state = {}
        for entry in manifest:
            path = entry["path"]
            if os.path.isabs(path) or ".." in Path(path).parts:
                self._l.warning(f"Skipping server file outside the FS42 directory: {path}")
                continue
            target = SERVER_MAIN_CONFIG if path == MAIN_CONFIG else path
            stamp = [entry["size"], entry["mtime"]]
            if known.get(path) != stamp or not os.path.exists(self._path(target)):
                self._write(target, self._get("/client/file", path=path).content)
            state[path] = stamp

        main_config = self._read_json(SERVER_MAIN_CONFIG, {}) if MAIN_CONFIG in state else {}
        main_config.update(self.config["main_config"])
        self._write(MAIN_CONFIG, json.dumps(main_config, indent=2).encode())

        for conf in glob.glob(self._path("confs/*.json")):
            relative = f"confs/{os.path.basename(conf)}"
            if relative != MAIN_CONFIG and relative not in state:
                os.remove(conf)
        self._write(MANIFEST_STATE, json.dumps(state).encode())

    def sync_rundown(self):
        response = self._get("/client/rundown", hours=24)
        server_time = response.json()["server_time"]
        self._write(RUNDOWN_PATH, response.content)
        clock.set_server_time(server_time)
        self._last_rundown = time.monotonic()

    def _sync_everything(self, version):
        self.sync_files()
        self.sync_rundown()
        self.version = version

    def sync_all(self):
        self._sync_everything(self.fetch_version())

    def initial_sync(self, retry_seconds=5):
        cached = os.path.exists(self._path(RUNDOWN_PATH)) and os.path.exists(self._path(MANIFEST_STATE))
        while True:
            try:
                self.sync_all()
                return
            except _SYNC_ERRORS as e:
                if cached:
                    self._l.warning(f"Server unreachable, starting from the last sync: {e}")
                    return
                self._l.warning(f"Waiting for the server at {self.config['server_url']}: {e}")
                time.sleep(retry_seconds)

    def poll_once(self, rundown_every=3600):
        try:
            version = self.fetch_version()
            if version != self.version or refresh_requested.is_set():
                refresh_requested.clear()
                self._sync_everything(version)
            elif self._last_rundown is None or time.monotonic() - self._last_rundown >= rundown_every:
                self.sync_rundown()
            else:
                return False
        except _SYNC_ERRORS as e:
            self._l.warning(f"Could not reach the server: {e}")
            return False
        except Exception as e:
            # the poller must outlive anything the server sends back, or the client stops updating for good
            self._l.exception(f"Unexpected sync failure: {e}")
            return False
        reload_requested.set()
        return True

    def start_poller(self, interval=10, rundown_every=3600):
        def poll():
            while True:
                time.sleep(interval)
                self.poll_once(rundown_every)

        thread = threading.Thread(target=poll, name="client-sync", daemon=True)
        thread.start()
        return thread
