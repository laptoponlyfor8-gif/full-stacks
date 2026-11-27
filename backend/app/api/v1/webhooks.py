import hashlib
import hmac
import logging
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import PlainTextResponse

from app.db.session import get_db_session
from app.db.tenant import set_tenant_organization
from app.models import MetaWebhookAccountRoute, SocialAccount, WebhookEvent
from app.services.meta_webhooks import (
    decode_request,
    event_idempotency_key,
    parse_webhook_payload,
    verify_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/meta", tags=["Meta webhooks"])
EVENT_STREAM = "dm-karo:webhook-events"


@router.get("", include_in_schema=False)
async def verify_meta_webhook(
    request: Request,
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    configured = request.app.state.settings.meta_webhook_verify_token
    expected = configured.get_secret_value() if configured else ""
    if (
        mode != "subscribe"
        or not expected
        or not verify_token
        or not challenge
        or not hmac.compare_digest(expected, verify_token)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed.")
    return PlainTextResponse(challenge, headers={"Cache-Control": "no-store"})


@router.post("", include_in_schema=False, status_code=status.HTTP_200_OK)
async def receive_meta_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    settings = request.app.state.settings
    if not settings.meta_app_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta webhook verification is not configured.",
        )
    await _rate_limit(request)
    body = await _read_limited_body(request, 1_000_000)
    if not verify_signature(
        settings.meta_app_secret.get_secret_value(),
        body,
        request.headers.get("X-Hub-Signature-256"),
    ):
        logger.warning("meta_webhook_signature_rejected")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook signature.")
    try:
        events = parse_webhook_payload(decode_request(body))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    redis = request.app.state.redis_client
    enqueued: set[tuple[str, str]] = set()
    for normalized in events:
        routes = list(
            (
                await session.scalars(
                    select(MetaWebhookAccountRoute).where(
                        MetaWebhookAccountRoute.platform == normalized["platform"],
                        MetaWebhookAccountRoute.platform_account_id == normalized["account_id"],
                    )
                )
            ).all()
        )
        if len(routes) != 1:
            logger.info(
                "meta_webhook_account_route_unavailable",
                extra={
                    "platform": normalized["platform"],
                    "route_count": len(routes),
                    "event_type": normalized["event_type"],
                },
            )
            continue
        route = routes[0]
        await set_tenant_organization(session, route.organization_id)
        account = await session.scalar(
            select(SocialAccount).where(
                SocialAccount.id == route.social_account_id,
                SocialAccount.organization_id == route.organization_id,
                SocialAccount.is_connected.is_(True),
            )
        )
        if account is None:
            await session.rollback()
            continue
        key = event_idempotency_key(normalized)
        event = await session.scalar(
            select(WebhookEvent).where(WebhookEvent.idempotency_key == key)
        )
        if event is None:
            event = WebhookEvent(
                organization_id=route.organization_id,
                social_account_id=route.social_account_id,
                platform=normalized["platform"],
                event_type=normalized["event_type"],
                idempotency_key=key,
                payload=normalized["payload"],
                processing_status="received",
                available_at=datetime.now(UTC),
            )
            session.add(event)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                await set_tenant_organization(session, route.organization_id)
                event = await session.scalar(
                    select(WebhookEvent).where(WebhookEvent.idempotency_key == key)
                )
        else:
            await session.commit()
        if event is not None and event.processing_status in {"received", "retry"}:
            enqueued.add((str(event.id), str(event.organization_id)))

    try:
        for event_id, organization_id in enqueued:
            await redis.xadd(
                EVENT_STREAM,
                {"event_id": event_id, "organization_id": organization_id},
                maxlen=100_000,
                approximate=True,
            )
    except RedisError as exc:
        logger.error("meta_webhook_queue_unavailable", extra={"event_count": len(enqueued)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook event queue is temporarily unavailable.",
        ) from exc
    return {"status": "accepted"}


async def _read_limited_body(request: Request, limit: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Webhook payload is too large.",
            )
        body.extend(chunk)
    return bytes(body)


async def _rate_limit(request: Request) -> None:
    peer = request.client.host if request.client else "unknown"
    key = "meta-webhook-rate:" + hashlib.sha256(peer.encode("utf-8")).hexdigest()
    script = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
    return count
    """
    try:
        count = int(
            await request.app.state.redis_client.eval(
                script,
                1,
                key,
            )
        )
    except RedisError as exc:
        logger.error("meta_webhook_rate_limit_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook intake is temporarily unavailable.",
        ) from exc
    if count > request.app.state.settings.webhook_rate_limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Webhook rate limit exceeded.",
            headers={"Retry-After": "60"},
        )
