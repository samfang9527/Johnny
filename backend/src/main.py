from __future__ import annotations

import os

from fastapi import FastAPI
import uvicorn

from .api.errors import register_exception_handlers
from .api.routes.activity_health import activity_router, health_router as health_metrics_router
from .api.routes.athlete_profile import router as athlete_profile_router
from .api.routes.conversations import router as conversations_router
from .api.routes.health import router as health_router
from .api.routes.integrations import router as integrations_router
from .api.routes.me import router as me_router
from .api.routes.races import router as races_router
from .api.routes.recommendations import router as recommendations_router
from .api.routes.today import router as today_router
from .api.routes.training_plans import router as training_plans_router
from .infrastructure.logging.logger_config import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Johnny API")
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(athlete_profile_router)
    app.include_router(activity_router)
    app.include_router(conversations_router)
    app.include_router(health_metrics_router)
    app.include_router(integrations_router)
    app.include_router(me_router)
    app.include_router(races_router)
    app.include_router(recommendations_router)
    app.include_router(today_router)
    app.include_router(training_plans_router)
    return app


app = create_app()


def run() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    run()
