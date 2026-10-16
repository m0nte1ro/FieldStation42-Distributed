import os
import sys
import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Add paths for module imports
cwd = os.getcwd()
parent = os.path.abspath(os.path.join(cwd, os.pardir))
sys.path.append(cwd)
sys.path.append(parent)

from shared.stations.manager import StationManager, StationConfigError
from fs42.schedule_keeper import start_schedule_keeper
from fs42.box.config import is_box, load_box_config
from fs42.box.proxy import build_proxy_router
from .api import routers
from .api.player import router as player_router
from .api.ppv import commands_router as ppv_commands_router

_shutdown_queue = None
player_command_queue = None

# browsers must check for updated files on every load, or they keep running old UI code after an update
REVALIDATE = {"Cache-Control": "no-cache"}


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers.update(REVALIDATE)
        return response

@asynccontextmanager
async def _lifespan(app):
    if _shutdown_queue is not None:
        async def shutdown_monitor():
            while True:
                await asyncio.sleep(1)
                try:
                    msg = _shutdown_queue.get_nowait()
                    if msg == "shutdown":
                        os._exit(0)
                except Exception:
                    pass
        asyncio.get_event_loop().create_task(shutdown_monitor())
    yield

async def _station_config_error_handler(request: Request, exc: StationConfigError):
    # Configuration problems are the operator's to fix, not a server fault -
    # report them instead of letting them take the request (or the process) down
    logging.getLogger("FS42SERVER").error(f"Station configuration error: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})

async def root():
    return FileResponse("fs42/fs42_server/static/index.html", headers=REVALIDATE)

async def remote():
    return FileResponse("fs42/fs42_server/static/remote.html", headers=REVALIDATE)

async def favicon():
    return FileResponse("fs42/fs42_server/static/favicon.ico")


def build_app(box_config):
    app = FastAPI(title="FieldStation42 API", lifespan=_lifespan)
    app.state.player_command_queue = None
    app.add_exception_handler(StationConfigError, _station_config_error_handler)
    if box_config:
        # a box handles its own player and PPV commands; every page and data route lives on the server
        for router in (player_router, ppv_commands_router, build_proxy_router(box_config["server_url"])):
            app.include_router(router)
        return app

    app.get("/")(root)
    app.get("/remote")(remote)
    app.get("/favicon.ico", include_in_schema=False)(favicon)
    for router in routers:
        app.include_router(router)
    return app


fapi = build_app(load_box_config() if is_box() else None)


def _mount_static():
    if is_box():
        return

    follow_symlink = StationManager().server_conf.get("follow_static_symlinks", False)
    if follow_symlink:
        logging.getLogger("FS42SERVER").warning(
            "follow_static_symlinks is on - symlinks in fs42/fs42_server/static and "
            "runtime/guide_videos will be served even if they point outside of those directories."
        )

    fapi.mount(
        "/static",
        RevalidatingStaticFiles(directory="fs42/fs42_server/static", html="true", follow_symlink=follow_symlink),
        name="static",
    )
    os.makedirs("runtime/guide_videos", exist_ok=True)
    fapi.mount(
        "/guide_videos",
        StaticFiles(directory="runtime/guide_videos", follow_symlink=follow_symlink),
        name="guide_videos",
    )


def run_with_shutdown_queue(shutdown_queue, command_queue):
    class PlayerStatusFilter(logging.Filter):
        def filter(self, record):
            return ('/player/status' not in record.getMessage())

    logging.getLogger("uvicorn.access").addFilter(PlayerStatusFilter())

    global player_command_queue, _shutdown_queue
    player_command_queue = command_queue
    _shutdown_queue = shutdown_queue
    fapi.state.player_command_queue = command_queue

    _mount_static()
    conf = StationManager().server_conf
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])


def mount_fs42_api():
    class PlayerStatusFilter(logging.Filter):
        def filter(self, record):
            return ('/player/status' not in record.getMessage())
    
    logging.getLogger("uvicorn.access").addFilter(PlayerStatusFilter())
    
    fapi.state.player_command_queue = None
    _mount_static()
    conf = StationManager().server_conf
    start_schedule_keeper(conf.get("schedule_agent"))
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])


# Method 1: Basic uvicorn.run()
if __name__ == "__main__":
    mount_fs42_api()
