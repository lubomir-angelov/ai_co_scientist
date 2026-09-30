"""
FastAPI application for the temporal knowledge-graph memory service.

Run with the app factory so configuration is validated at startup:
    uvicorn memory_service.app:create_app --factory --port 8005
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.exceptions import ConnectionError as RedisConnectionError

from shared_library.memory_interface import PaperMemoryBackend

from .config import Settings
from .dependencies import BackendUnavailableError, MemoryRuntime, get_runtime
from .routers import episodes, queries

logger = logging.getLogger(__name__)

SERVICE_NAME = "memory"


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format=f"%(asctime)s %(levelname)s {SERVICE_NAME} %(name)s: %(message)s",
    )


def _build_default_backend(settings: Settings) -> PaperMemoryBackend:
    # Imported here so tests that inject a backend never construct Graphiti clients.
    from .graphiti_client import build_graphiti
    from .graphiti_paper_backend import GraphitiPaperMemoryBackend

    return GraphitiPaperMemoryBackend(
        lambda: build_graphiti(settings),
        max_concurrent_episodes=settings.max_concurrent_episodes,
    )


async def _init_with_retries(runtime: MemoryRuntime) -> None:
    attempts = runtime.settings.init_retries
    for attempt in range(1, attempts + 1):
        try:
            await runtime.ensure_ready()
            logger.info("Memory backend ready")
            return
        except BackendUnavailableError:
            logger.warning("Memory backend not ready (attempt %d/%d)", attempt, attempts)
            if attempt < attempts:
                await asyncio.sleep(runtime.settings.init_retry_delay_seconds)
    # Keep serving: /health reports ready=false and requests retry initialisation lazily.
    logger.error("Memory backend unavailable after %d attempts; will retry on demand", attempts)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BackendUnavailableError)
    async def _backend_unavailable(request: Request, exc: BackendUnavailableError) -> JSONResponse:
        return _error(503, "backend_unavailable", str(exc))

    @app.exception_handler(RedisConnectionError)
    async def _graph_unavailable(request: Request, exc: RedisConnectionError) -> JSONResponse:
        logger.error(
            "FalkorDB connection failed on %s %s: %s", request.method, request.url.path, exc
        )
        return _error(503, "graph_unavailable", "graph database is not reachable")

    @app.exception_handler(openai.APIError)
    async def _model_error(request: Request, exc: openai.APIError) -> JSONResponse:
        logger.error(
            "LLM/embedding call failed on %s %s: %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
            exc,
        )
        return _error(502, "model_unavailable", "local LLM or embedding service call failed")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error(500, "internal_error", "internal error in memory service")


def create_app(
    settings: Settings | None = None, backend: PaperMemoryBackend | None = None
) -> FastAPI:
    """
    Build the app. ``settings`` default to environment variables; ``backend`` defaults
    to Graphiti on FalkorDB and can be injected for tests.
    """
    settings = settings or Settings()
    _configure_logging(settings.log_level)
    runtime = MemoryRuntime(backend=backend or _build_default_backend(settings), settings=settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Starting memory service: %s", settings.summary())
        await _init_with_retries(runtime)
        try:
            yield
        finally:
            await runtime.backend.close()
            logger.info("Memory service stopped")

    app = FastAPI(title="Co-Scientist Memory Service", version="0.2.0", lifespan=lifespan)
    app.state.memory = runtime

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        rt = get_runtime(request)
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "ready": rt.ready,
            "graph_name": rt.settings.graph_name,
        }

    app.include_router(episodes.router, prefix="/v1/memory")
    app.include_router(queries.router, prefix="/v1/memory")
    _register_error_handlers(app)
    return app
