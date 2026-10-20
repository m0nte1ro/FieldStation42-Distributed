import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from client.input.player_routes import router as player_router
from client.input.ppv_commands import router as ppv_router
from client.input.proxy import build_proxy_router
from client.playback.config import load_client_config
from shared.stations.manager import StationManager

# The client's own API on :4242. Player and PPV commands act on this client; every page and data
# route is proxied to the server, so autobump pages stored as http://127.0.0.1:4242/... and
# localhost web channel URLs work here unchanged.

_shutdown_queue = None


@asynccontextmanager
async def _lifespan(app):
    if _shutdown_queue is not None:
        async def shutdown_monitor():
            while True:
                await asyncio.sleep(1)
                try:
                    if _shutdown_queue.get_nowait() == "shutdown":
                        os._exit(0)
                except Exception:
                    pass
        asyncio.get_event_loop().create_task(shutdown_monitor())
    yield


def build_app(server_url, headers=None):
    app = FastAPI(title="FieldStation42 client", lifespan=_lifespan)
    app.state.player_command_queue = None
    proxy_router = build_proxy_router(server_url, headers=headers) if headers else build_proxy_router(server_url)
    for router in (player_router, ppv_router, proxy_router):
        app.include_router(router)
    return app


def run(shutdown_queue, command_queue):
    global _shutdown_queue

    class PlayerStatusFilter(logging.Filter):
        def filter(self, record):
            return "/player/status" not in record.getMessage()

    logging.getLogger("uvicorn.access").addFilter(PlayerStatusFilter())
    _shutdown_queue = shutdown_queue
    config = load_client_config()
    app = build_app(config["server_url"], config["server_headers"])
    app.state.player_command_queue = command_queue
    conf = StationManager().server_conf
    port = config["local_api_port"] or conf["server_port"]
    logging.getLogger("LocalAPI").info(f"Client API on port {port}")
    uvicorn.run(app, host=conf["server_host"], port=port)
