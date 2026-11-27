from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import health
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.anyio


async def test_root_health_endpoint(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


async def test_versioned_health_endpoint(client) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_returns_ready_when_dependencies_respond(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "check_database", AsyncMock(return_value=True))
    monkeypatch.setattr(health, "check_redis", AsyncMock(return_value=True))

    response = await client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }


@pytest.mark.parametrize(
    ("database_available", "redis_available", "expected_checks"),
    [
        (False, True, {"database": "unavailable", "redis": "ok"}),
        (True, False, {"database": "ok", "redis": "unavailable"}),
        (False, False, {"database": "unavailable", "redis": "unavailable"}),
    ],
)
async def test_readiness_is_unavailable_if_a_dependency_fails(
    client,
    monkeypatch: pytest.MonkeyPatch,
    database_available: bool,
    redis_available: bool,
    expected_checks: dict[str, str],
) -> None:
    monkeypatch.setattr(health, "check_database", AsyncMock(return_value=database_available))
    monkeypatch.setattr(health, "check_redis", AsyncMock(return_value=redis_available))

    response = await client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": expected_checks}
    assert "password" not in response.text.lower()
    assert "localhost" not in response.text.lower()


async def test_readiness_performs_real_checks_and_returns_safe_unavailable_status() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://127.0.0.1:1/test_db",
        redis_url="redis://127.0.0.1:1/0",
        cors_allowed_origins=["http://localhost:5173"],
        health_check_timeout_seconds=0.2,
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable", "redis": "unavailable"},
    }
    assert "127.0.0.1" not in response.text
