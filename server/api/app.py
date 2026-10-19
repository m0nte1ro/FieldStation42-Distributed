import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from server.bumps.keeper import start_bump_keeper
from server.scheduler.schedule_keeper import start_schedule_keeper
from shared.stations.manager import StationConfigError, StationManager

from .routes import routers

STATIC_DIR = "server/api/static"

# browsers must check for updated files on every load, or they keep running old UI code after an update
REVALIDATE = {"Cache-Control": "no-cache"}


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers.update(REVALIDATE)
        return response


async def _station_config_error_handler(request: Request, exc: StationConfigError):
    # Configuration problems are the operator's to fix, not a server fault -
    # report them instead of letting them take the request (or the process) down
    logging.getLogger("FS42SERVER").error(f"Station configuration error: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})


async def root():
    return FileResponse(f"{STATIC_DIR}/index.html", headers=REVALIDATE)


async def remote():
    # served here, used through a client: the client proxies the page and answers its /player calls
    return FileResponse(f"{STATIC_DIR}/remote.html", headers=REVALIDATE)


async def favicon():
    return FileResponse(f"{STATIC_DIR}/favicon.ico")


def build_app():
    app = FastAPI(title="FieldStation42 server")
    app.add_exception_handler(StationConfigError, _station_config_error_handler)
    app.get("/")(root)
    app.get("/remote")(remote)
    app.get("/favicon.ico", include_in_schema=False)(favicon)
    for router in routers:
        app.include_router(router)
    # behind a TLS reverse proxy (Cloudflare, nginx), redirects keep the browser's https
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    return app


fapi = build_app()


def _mount_static(app):
    follow_symlink = StationManager().server_conf.get("follow_static_symlinks", False)
    if follow_symlink:
        logging.getLogger("FS42SERVER").warning(
            f"follow_static_symlinks is on - symlinks in {STATIC_DIR} and "
            "runtime/guide_videos will be served even if they point outside of those directories."
        )
    app.mount("/static", RevalidatingStaticFiles(directory=STATIC_DIR, html="true", follow_symlink=follow_symlink),
              name="static")
    os.makedirs("runtime/guide_videos", exist_ok=True)
    app.mount("/guide_videos", StaticFiles(directory="runtime/guide_videos", follow_symlink=follow_symlink),
              name="guide_videos")


def run():
    conf = StationManager().server_conf
    _mount_static(fapi)
    start_schedule_keeper(conf.get("schedule_agent"))
    start_bump_keeper()
    uvicorn.run(fapi, host=conf["server_host"], port=conf["server_port"])
