import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import create_database_engine, create_session_factory
from app.schemas.health import HealthResponse
from app.utils.request_id import new_request_id

logger = logging.getLogger("app.http")


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    configure_logging(application_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(application_settings.database_url.get_secret_value())
        redis_client = Redis.from_url(
            application_settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=application_settings.health_check_timeout_seconds,
            socket_timeout=application_settings.health_check_timeout_seconds,
        )
        app.state.db_engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.redis_client = redis_client
        try:
            yield
        finally:
            try:
                await redis_client.aclose()
            finally:
                await engine.dispose()

    app = FastAPI(
        title=application_settings.app_name,
        version="0.1.0",
        description="DM Karo service foundation.",
        docs_url="/docs" if application_settings.docs_enabled else None,
        redoc_url="/redoc" if application_settings.docs_enabled else None,
        openapi_url="/openapi.json" if application_settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = application_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=application_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-CSRF-Token",
            "X-Request-ID",
            "X-Hub-Signature-256",
        ],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.middleware("http")
    async def log_http_request(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = new_request_id()
        start_time = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith(("/api/v1/auth/", "/api/v1/meta/", "/api/v1/ai/")):
            response.headers["Cache-Control"] = "no-store"
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def root_health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
