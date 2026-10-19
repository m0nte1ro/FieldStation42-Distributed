from .summary import router as summary_router
from .catalogs import router as catalogs_router
from .schedules import router as schedules_router
from .build import router as build_router
from .themes import router as themes_router
from .stations import router as stations_router
from .ppv import router as ppv_router
from .media import router as media_router
from .client import router as client_router

routers = [
    summary_router,
    catalogs_router,
    schedules_router,
    build_router,
    themes_router,
    stations_router,
    ppv_router,
    media_router,
    client_router,
]
