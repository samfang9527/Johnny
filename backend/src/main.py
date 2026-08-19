from __future__ import annotations

import os

from fastapi import FastAPI
import uvicorn

from .api.routes.health import router as health_router
from .infrastructure.logging.logger_config import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Johnny API")
    app.include_router(health_router)
    return app


app = create_app()


def run() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    run()
