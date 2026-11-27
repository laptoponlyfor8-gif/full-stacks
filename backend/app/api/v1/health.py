import asyncio

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.readiness import check_database, check_redis

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Check API liveness")
async def versioned_health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse, summary="Check service dependencies")
async def readiness(request: Request) -> ReadinessResponse:
    engine = getattr(request.app.state, "db_engine", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    timeout = request.app.state.settings.health_check_timeout_seconds

    if engine is None or redis_client is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ReadinessResponse(
                status="not_ready",
                checks={"database": "unavailable", "redis": "unavailable"},
            ).model_dump(),
        )

    database_ok, redis_ok = await asyncio.gather(
        check_database(engine, timeout),
        check_redis(redis_client, timeout),
    )
    checks = {
        "database": "ok" if database_ok else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
    }
    response = ReadinessResponse(
        status="ready" if database_ok and redis_ok else "not_ready",
        checks=checks,
    )
    if not database_ok or not redis_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )
    return response
