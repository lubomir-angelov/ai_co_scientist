# memory_service/app.py

from __future__ import annotations

from fastapi import FastAPI

from .routers import episodes, queries


def create_app() -> FastAPI:
    app = FastAPI(
        title="Co-Scientist Memory Service",
        version="0.1.0",
    )

    app.include_router(episodes.router, prefix="/v1/memory")
    app.include_router(queries.router, prefix="/v1/memory")

    return app


app = create_app()
