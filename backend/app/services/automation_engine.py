from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import has_expired
from app.db.tenant import set_tenant_organization
from app.models import (
    Automation,
    AutomationExecution,
    AutomationKeyword,
    Contact,
    Message,
    MessageDeliveryAttempt,
    SocialAccount,
    WebhookEvent,
)
from app.models.enums import AutomationStatus, KeywordMatchType, SocialPlatform
from app.services.meta_oauth import account_token_context, decrypt_token

logger = logging.getLogger(__name__)
_META_TIMEOUT_SECONDS = 12.0
_MAX_MESSAGE_LENGTH = 1000


class TransientMetaError(Exception):
    pass


class PermanentMetaError(Exception):
    pass


def match_keyword(text: str, keyword: str, match_type: KeywordMatchType) -> bool:
    normalized_text = _normalize(text)
    normalized_keyword = _normalize(keyword)
    if not normalized_text or not normalized_keyword:
        return False
    if match_type == KeywordMatchType.EXACT:
        return normalized_text == normalized_keyword
    if match_type == KeywordMatchType.CONTAINS:
        return normalized_keyword in normalized_text
    return f" {normalized_keyword} " in f" {normalized_text} "


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", folded).strip()


def _event_epoch(value: Any) -> float | None:
    try:
        if isinstance(value, (int, float)):
            timestamp = float(value)
            return timestamp / 1000 if timestamp > 100_000_000_000 else timestamp
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        return None
    return None


def _event_datetime(event: WebhookEvent) -> datetime | None:
    timestamp = _event_epoch(event.payload.get("timestamp"))
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _get_or_create_contact(
    session: AsyncSession,
    event: WebhookEvent,
    account: SocialAccount,
    customer_id: str,
) -> Contact:
    contact = await session.scalar(
        select(Contact).where(
            Contact.organization_id == event.organization_id,
            Contact.social_account_id == account.id,
            Contact.platform_customer_id == customer_id,
        )
    )
    occurred_at = _event_datetime(event)
    if contact is None:
        contact = Contact(
            organization_id=event.organization_id,
            social_account_id=account.id,
            platform_customer_id=customer_id,
            display_name="",
            first_contact_at=occurred_at,
            last_interaction_at=occurred_at,
        )
        session.add(contact)
        await session.flush()
    elif occurred_at is not None:
        first_contact_at = _as_utc(contact.first_contact_at) if contact.first_contact_at else None
        last_interaction_at = _as_utc(contact.last_interaction_at) if contact.last_interaction_at else None
        if first_contact_at is None or occurred_at < first_contact_at:
            contact.first_contact_at = occurred_at
        if last_interaction_at is None or occurred_at > last_interaction_at:
            contact.last_interaction_at = occurred_at
    return contact


def _within_private_reply_window(event: WebhookEvent) -> bool:
    event_time = _event_epoch(event.payload.get("timestamp"))
    if event_time is None:
        return False
    if event.payload.get("is_live") is True:
        return False
    age = datetime.now(UTC).timestamp() - event_time
    return 0 <= age <= 7 * 24 * 60 * 60


def _within_messaging_window(event: WebhookEvent) -> bool:
    event_time = _event_epoch(event.payload.get("timestamp"))
    return event_time is not None and 0 <= datetime.now(UTC).timestamp() - event_time <= 24 * 60 * 60


async def send_meta_text(
    settings: Settings,
    account: SocialAccount,
    *,
    token: str,
    recipient_id: str,
    text: str,
    comment_id: str | None = None,
    public_comment_id: str | None = None,
) -> str:
    if not text.strip() or len(text) > _MAX_MESSAGE_LENGTH:
        raise PermanentMetaError("invalid_message")
    if account.token_expires_at is not None and has_expired(account.token_expires_at):
        raise PermanentMetaError("expired_token")

    base = "https://graph.instagram.com" if account.platform == SocialPlatform.INSTAGRAM else "https://graph.facebook.com"
    if public_comment_id:
        path = (
            f"{base}/{settings.meta_graph_api_version}/{public_comment_id}/replies"
            if account.platform == SocialPlatform.INSTAGRAM
            else f"{base}/{settings.meta_graph_api_version}/{public_comment_id}/comments"
        )
        body = {"message": text}
    else:
        path = f"{base}/{settings.meta_graph_api_version}/{account.platform_account_id}/messages"
        recipient = {"comment_id": comment_id} if comment_id else {"id": recipient_id}
        body = {"recipient": recipient, "message": {"text": text}}

    try:
        async with httpx.AsyncClient(timeout=_META_TIMEOUT_SECONDS) as client:
            response = await client.post(
                path,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        payload = response.json()
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise PermanentMetaError("delivery_outcome_unknown") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise TransientMetaError("provider_unavailable") from exc
    if not isinstance(payload, dict):
        raise PermanentMetaError("malformed_provider_response")
    error = payload.get("error")
    if response.status_code == 429 or response.status_code >= 500:
        raise TransientMetaError("provider_temporary_error")
    if response.is_error or error:
        code = error.get("code") if isinstance(error, dict) else None
        raise PermanentMetaError("invalid_token" if code == 190 else "provider_rejected")
    message_id = payload.get("message_id") or payload.get("id")
    if not isinstance(message_id, (str, int)) or not str(message_id):
        raise PermanentMetaError("provider_missing_message_id")
    return str(message_id)


async def process_webhook_event(
    session: AsyncSession,
    settings: Settings,
    event_id: UUID,
    organization_id: UUID,
) -> None:
    await set_tenant_organization(session, organization_id)
    event = await session.scalar(
        select(WebhookEvent).where(
            WebhookEvent.id == event_id,
            WebhookEvent.organization_id == organization_id,
        )
    )
    if event is None:
        return
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == event.social_account_id,
            SocialAccount.organization_id == organization_id,
            SocialAccount.is_connected.is_(True),
        )
    )
    if account is None:
        event.processing_status = "ignored"
        event.processed_at = datetime.now(UTC)
        await session.commit()
        return
    if event.event_type == "direct_message":
        await _process_direct_message(session, settings, event, account)
    elif event.event_type == "comment":
        await _process_comment(session, settings, event, account)
    if event.processing_status == "processing":
        event.processing_status = "processed"
        event.error_category = None
    event.processing_started_at = None
    event.processed_at = datetime.now(UTC)
    await session.commit()


async def _process_comment(
    session: AsyncSession,
    settings: Settings,
    event: WebhookEvent,
    account: SocialAccount,
) -> None:
    if not event.payload.get("media_id") or not event.payload.get("text"):
        event.processing_status = "ignored"
        return
    if event.payload.get("actor_id") == account.platform_account_id:
        event.processing_status = "ignored"
        return
    actor_id = event.payload.get("actor_id")
    if isinstance(actor_id, str) and actor_id:
        await _get_or_create_contact(session, event, account, actor_id)
    if not _within_private_reply_window(event):
        event.processing_status = "ignored"
        event.error_category = "outside_private_reply_window"
        return
    automations = list(
        (
            await session.scalars(
                select(Automation).where(
                    Automation.organization_id == event.organization_id,
                    Automation.social_account_id == account.id,
                    Automation.platform_content_id == event.payload["media_id"],
                    Automation.trigger_type == "comment",
                    Automation.status == AutomationStatus.ACTIVE,
                ).order_by(Automation.created_at, Automation.id)
            )
        ).all()
    )
    for automation in automations:
        keywords = list(
            (
                await session.scalars(
                    select(AutomationKeyword).where(
                        AutomationKeyword.organization_id == event.organization_id,
                        AutomationKeyword.automation_id == automation.id,
                        AutomationKeyword.is_active.is_(True),
                    ).order_by(AutomationKeyword.id)
                )
            ).all()
        )
        matched = next(
            (
                rule
                for rule in keywords
                if match_keyword(event.payload["text"], rule.keyword, rule.match_type)
            ),
            None,
        )
        if matched is None:
            continue
        prior = await session.scalar(
            select(AutomationExecution).where(
                AutomationExecution.webhook_event_id == event.id,
                AutomationExecution.automation_id == automation.id,
            )
        )
        if prior and prior.status not in {"failed", "matched"}:
            continue
        execution = prior or AutomationExecution(
            organization_id=event.organization_id,
            webhook_event_id=event.id,
            automation_id=automation.id,
            status="matched",
            matched_keyword_id=matched.id,
            started_at=datetime.now(UTC),
        )
        if prior:
            execution.status = "matched"
            execution.error_category = None
            execution.started_at = datetime.now(UTC)
        else:
            session.add(execution)
        await session.flush()
        private_reply = automation.private_reply_text
        if private_reply:
            await _deliver_once(
                session,
                settings,
                event,
                account,
                execution,
                private_reply,
                action="private",
                recipient_id=event.payload.get("actor_id") or "",
                comment_id=event.payload["comment_id"],
            )
        if automation.public_reply_enabled and automation.public_reply_text:
            await _deliver_once(
                session,
                settings,
                event,
                account,
                execution,
                automation.public_reply_text,
                action="public",
                recipient_id="",
                public_comment_id=event.payload["comment_id"],
            )
        execution.finished_at = datetime.now(UTC)
    if not automations:
        event.processing_status = "ignored"


async def _process_direct_message(
    session: AsyncSession,
    settings: Settings,
    event: WebhookEvent,
    account: SocialAccount,
) -> None:
    actor_id = event.payload.get("actor_id")
    text = event.payload.get("text")
    if not actor_id or not text:
        event.processing_status = "ignored"
        return
    contact = await _get_or_create_contact(session, event, account, actor_id)
    inbound_key = f"meta:{event.platform}:{event.payload.get('message_id')}:incoming"
    inbound = await session.scalar(select(Message).where(Message.idempotency_key == inbound_key))
    if inbound is None:
        session.add(
            Message(
                organization_id=event.organization_id,
                automation_id=None,
                social_account_id=account.id,
                recipient_platform_id=actor_id,
                message_type="incoming",
                message_content=text[:5000],
                delivery_status="received",
                external_message_id=event.payload.get("message_id"),
                idempotency_key=inbound_key,
                contact_id=contact.id,
                platform_created_at=_event_datetime(event),
                is_read=False,
            )
        )
        await session.flush()
    if not _within_messaging_window(event):
        event.processing_status = "ignored"
        event.error_category = "outside_messaging_window"
        return
    automations = list(
        (
            await session.scalars(
                select(Automation).where(
                    Automation.organization_id == event.organization_id,
                    Automation.social_account_id == account.id,
                    Automation.trigger_type == "direct_message",
                    Automation.status == AutomationStatus.ACTIVE,
                ).order_by(Automation.created_at, Automation.id)
            )
        ).all()
    )
    for automation in automations:
        rules = list(
            (
                await session.scalars(
                    select(AutomationKeyword).where(
                        AutomationKeyword.organization_id == event.organization_id,
                        AutomationKeyword.automation_id == automation.id,
                        AutomationKeyword.is_active.is_(True),
                    ).order_by(AutomationKeyword.id)
                )
            ).all()
        )
        matched = next((rule for rule in rules if match_keyword(text, rule.keyword, rule.match_type)), None)
        if not matched or not automation.private_reply_text:
            continue
        prior = await session.scalar(
            select(AutomationExecution).where(
                AutomationExecution.webhook_event_id == event.id,
                AutomationExecution.automation_id == automation.id,
            )
        )
        if prior and prior.status not in {"failed", "matched"}:
            continue
        execution = prior or AutomationExecution(
            organization_id=event.organization_id,
            webhook_event_id=event.id,
            automation_id=automation.id,
            status="matched",
            matched_keyword_id=matched.id,
            started_at=datetime.now(UTC),
        )
        if prior:
            execution.status = "matched"
            execution.error_category = None
            execution.started_at = datetime.now(UTC)
        else:
            session.add(execution)
        await session.flush()
        await _deliver_once(
            session,
            settings,
            event,
            account,
            execution,
            automation.private_reply_text,
            action="direct",
            recipient_id=actor_id,
        )
        execution.finished_at = datetime.now(UTC)
        break


async def _deliver_once(
    session: AsyncSession,
    settings: Settings,
    event: WebhookEvent,
    account: SocialAccount,
    execution: AutomationExecution,
    content: str,
    *,
    action: str,
    recipient_id: str,
    comment_id: str | None = None,
    public_comment_id: str | None = None,
) -> None:
    identity = event.payload.get("comment_id") or event.payload.get("message_id") or str(event.id)
    idempotency_key = f"meta:{event.platform}:{identity}:{action}"
    message = await session.scalar(select(Message).where(Message.idempotency_key == idempotency_key))
    if message and message.delivery_status in {"sent", "uncertain", "sending"}:
        if message.delivery_status == "sending":
            message.delivery_status = "uncertain"
            previous_attempt = await session.scalar(
                select(MessageDeliveryAttempt)
                .where(MessageDeliveryAttempt.message_id == message.id)
                .order_by(MessageDeliveryAttempt.attempt_number.desc())
                .limit(1)
            )
            if previous_attempt and previous_attempt.status == "sending":
                previous_attempt.status = "failed"
                previous_attempt.error_category = "delivery_outcome_unknown"
        execution.status = "skipped"
        execution.error_category = "duplicate_delivery_prevented"
        return
    if message is None:
        actor_id = event.payload.get("actor_id")
        contact = (
            await _get_or_create_contact(session, event, account, actor_id)
            if isinstance(actor_id, str) and actor_id
            else None
        )
        message = Message(
            organization_id=event.organization_id,
            automation_id=execution.automation_id,
            social_account_id=account.id,
            recipient_platform_id=recipient_id or (event.payload.get("actor_id") or ""),
            message_type=action,
            message_content=content,
            delivery_status="sending",
            idempotency_key=idempotency_key,
            contact_id=contact.id if contact is not None else None,
            is_read=True,
        )
        session.add(message)
        await session.flush()
    else:
        message.delivery_status = "sending"
    attempt_number = int(
        (await session.scalar(
            select(MessageDeliveryAttempt.attempt_number)
            .where(MessageDeliveryAttempt.message_id == message.id)
            .order_by(MessageDeliveryAttempt.attempt_number.desc())
            .limit(1)
        )) or 0
    ) + 1
    attempt = MessageDeliveryAttempt(
        organization_id=event.organization_id,
        message_id=message.id,
        attempt_number=attempt_number,
        status="sending",
        created_at=datetime.now(UTC),
    )
    session.add(attempt)
    await session.flush()
    await session.commit()
    await set_tenant_organization(session, event.organization_id)
    token_context = account_token_context(
        account.organization_id,
        account.platform.value,
        account.platform_account_id,
    )
    try:
        token = decrypt_token(settings, account.encrypted_access_token or "", context=token_context)
        external_id = await send_meta_text(
            settings,
            account,
            token=token,
            recipient_id=recipient_id,
            text=content,
            comment_id=comment_id,
            public_comment_id=public_comment_id,
        )
    except TransientMetaError as exc:
        attempt.status = "failed"
        attempt.error_category = str(exc)
        message.delivery_status = "failed"
        execution.status = "failed"
        execution.error_category = str(exc)
        await session.commit()
        raise
    except (PermanentMetaError, ValueError, RuntimeError) as exc:
        category = str(exc) if isinstance(exc, PermanentMetaError) else "token_unavailable"
        attempt.status = "failed"
        attempt.error_category = category
        message.delivery_status = "uncertain" if category == "delivery_outcome_unknown" else "failed"
        execution.status = "failed"
        execution.error_category = category
        if category == "invalid_token":
            account.is_connected = False
            account.encrypted_access_token = None
            account.updated_at = datetime.now(UTC)
            await session.execute(
                update(Automation)
                .where(
                    Automation.organization_id == event.organization_id,
                    Automation.social_account_id == account.id,
                    Automation.status == AutomationStatus.ACTIVE,
                )
                .values(status=AutomationStatus.PAUSED, updated_at=datetime.now(UTC))
            )
        return
    attempt.status = "sent"
    attempt.external_message_id = external_id
    message.delivery_status = "sent"
    message.external_message_id = external_id
    message.platform_created_at = datetime.now(UTC)
    if message.contact_id is not None:
        contact = await session.scalar(
            select(Contact).where(
                Contact.id == message.contact_id,
                Contact.organization_id == event.organization_id,
            )
        )
        if contact is not None:
            contact.last_interaction_at = message.platform_created_at
    execution.status = "sent"
    await session.flush()
