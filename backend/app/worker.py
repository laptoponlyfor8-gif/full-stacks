from __future__ import annotations

import asyncio
import logging
import secrets
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import and_, or_, select, update

from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.db.tenant import set_tenant_organization
from app.models import MetaWebhookAccountRoute, WebhookEvent
from app.services.automation_engine import process_webhook_event
from app.api.v1.webhooks import EVENT_STREAM

logger = logging.getLogger("app.worker")
CONSUMER_GROUP = "dm-karo-automation-workers"
DEAD_LETTER_STREAM = "dm-karo:webhook-events:dead"
DELAYED_SET = "dm-karo:webhook-events:delayed"


async def run_worker() -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    redis = Redis.from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=settings.health_check_timeout_seconds,
        socket_timeout=settings.health_check_timeout_seconds,
    )
    consumer = f"{socket.gethostname()}-{secrets.token_hex(8)}"
    try:
        try:
            await redis.xgroup_create(EVENT_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
        except RedisError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        logger.info("automation_worker_started")
        while True:
            await _promote_delayed(redis)
            await _recover_pending(redis, sessions, settings, consumer)
            await _recover_database_outbox(redis, sessions)
            batches = await redis.xreadgroup(
                CONSUMER_GROUP,
                consumer,
                {EVENT_STREAM: ">"},
                count=10,
                block=settings.automation_worker_block_ms,
            )
            for _, entries in batches:
                for stream_id, fields in entries:
                    await _handle_entry(
                        redis,
                        sessions,
                        settings,
                        consumer,
                        stream_id,
                        fields,
                    )
    finally:
        await redis.aclose()
        await engine.dispose()


async def _handle_entry(
    redis: Redis,
    sessions,
    settings,
    consumer: str,
    stream_id: str,
    fields: dict[str, str],
) -> None:
    try:
        event_id = UUID(fields["event_id"])
        organization_id = UUID(fields["organization_id"])
    except (KeyError, ValueError):
        logger.error("automation_worker_invalid_queue_record")
        await redis.xack(EVENT_STREAM, CONSUMER_GROUP, stream_id)
        return
    now = datetime.now(UTC)
    async with sessions() as session:
        await set_tenant_organization(session, organization_id)
        claim = await session.execute(
            update(WebhookEvent)
            .where(
                WebhookEvent.id == event_id,
                WebhookEvent.organization_id == organization_id,
                WebhookEvent.available_at <= now,
                or_(
                    WebhookEvent.processing_status.in_(("received", "retry")),
                    (
                        (WebhookEvent.processing_status == "processing")
                        & (WebhookEvent.processing_started_at < now - timedelta(minutes=5))
                    ),
                ),
            )
            .values(
                processing_status="processing",
                processing_started_at=now,
            )
            .returning(WebhookEvent.id)
        )
        claimed = claim.scalar_one_or_none()
        await session.commit()
    if claimed is None:
        await redis.xack(EVENT_STREAM, CONSUMER_GROUP, stream_id)
        return

    try:
        async with sessions() as session:
            await process_webhook_event(session, settings, event_id, organization_id)
    except Exception as exc:
        logger.exception(
            "automation_event_processing_failed",
            extra={"event_id": str(event_id), "error_type": type(exc).__name__},
        )
        await _schedule_retry(
            redis,
            sessions,
            settings,
            event_id,
            organization_id,
            type(exc).__name__,
        )
    finally:
        await redis.xack(EVENT_STREAM, CONSUMER_GROUP, stream_id)


async def _schedule_retry(redis, sessions, settings, event_id, organization_id, category) -> None:
    async with sessions() as session:
        await set_tenant_organization(session, organization_id)
        event = await session.scalar(
            select(WebhookEvent).where(
                WebhookEvent.id == event_id,
                WebhookEvent.organization_id == organization_id,
            )
        )
        if event is None:
            return
        event.retry_count += 1
        event.error_category = category[:60]
        event.processing_started_at = None
        if event.retry_count >= settings.automation_worker_max_attempts:
            event.processing_status = "failed"
            event.processed_at = datetime.now(UTC)
            await session.commit()
            await redis.xadd(
                DEAD_LETTER_STREAM,
                {
                    "event_id": str(event_id),
                    "organization_id": str(organization_id),
                    "error_category": category[:60],
                },
                maxlen=10_000,
                approximate=True,
            )
            return
        delay = min(2 ** event.retry_count, 300)
        event.processing_status = "retry"
        event.available_at = datetime.now(UTC) + timedelta(seconds=delay)
        await session.commit()
        due_member = f"{event_id}|{organization_id}"
        await redis.zadd(DELAYED_SET, {due_member: (datetime.now(UTC) + timedelta(seconds=delay)).timestamp()})


async def _promote_delayed(redis: Redis) -> None:
    script = """
    local members = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 100)
    for _, member in ipairs(members) do redis.call('ZREM', KEYS[1], member) end
    return members
    """
    due = await redis.eval(script, 1, DELAYED_SET, datetime.now(UTC).timestamp())
    for member in due:
        event_id, organization_id = member.split("|", 1)
        await redis.xadd(EVENT_STREAM, {"event_id": event_id, "organization_id": organization_id})


async def _recover_pending(redis: Redis, sessions, settings, consumer: str) -> None:
    try:
        _, messages, _ = await redis.xautoclaim(
            EVENT_STREAM,
            CONSUMER_GROUP,
            consumer,
            min_idle_time=60_000,
            start_id="0-0",
            count=20,
        )
    except RedisError:
        return
    for stream_id, fields in messages:
        await _handle_entry(redis, sessions, settings, consumer, stream_id, fields)


async def _recover_database_outbox(redis: Redis, sessions) -> None:
    async with sessions() as session:
        routes = list((await session.scalars(select(MetaWebhookAccountRoute.organization_id).distinct())).all())
    for organization_id in routes:
        async with sessions() as session:
            await set_tenant_organization(session, organization_id)
            now = datetime.now(UTC)
            due = and_(
                WebhookEvent.processing_status.in_(("received", "retry")),
                WebhookEvent.available_at <= now,
            )
            stale = and_(
                WebhookEvent.processing_status == "processing",
                WebhookEvent.processing_started_at < now - timedelta(minutes=5),
            )
            pending = list(
                (
                    await session.scalars(
                        select(WebhookEvent)
                        .where(or_(due, stale))
                        .limit(100)
                    )
                ).all()
            )
            queue_items = [
                (str(event.id), str(event.organization_id))
                for event in pending
            ]
        for event_id, org_id in queue_items:
            await redis.xadd(EVENT_STREAM, {"event_id": event_id, "organization_id": org_id})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
