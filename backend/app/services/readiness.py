import asyncio
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def check_database(engine: AsyncEngine, timeout_seconds: float) -> bool:
    try:
        async def query_database() -> None:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        await asyncio.wait_for(query_database(), timeout=timeout_seconds)
        return True
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        logger.warning(
            "dependency_readiness_check_failed",
            extra={"dependency": "postgresql", "error_type": type(exc).__name__},
        )
        return False


async def check_redis(redis_client: Redis, timeout_seconds: float) -> bool:
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=timeout_seconds)
        return True
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning(
            "dependency_readiness_check_failed",
            extra={"dependency": "redis", "error_type": type(exc).__name__},
        )
        return False
