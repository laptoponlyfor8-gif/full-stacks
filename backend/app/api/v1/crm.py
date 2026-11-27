from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, get_current_principal
from app.core.config import Settings
from app.db.session import get_db_session
from app.models import (
    Automation,
    AutomationExecution,
    Contact,
    ContactNote,
    ContactTag,
    ContactTagAssignment,
    LeadActivity,
    Message,
    MessageDeliveryAttempt,
    SocialAccount,
)
from app.models.enums import AutomationStatus, LeadStatus, OrganizationRole, SocialPlatform
from app.schemas.crm import (
    AnalyticsResponse,
    ContactCreate,
    ContactNoteCreate,
    ContactNoteResponse,
    ContactPage,
    ContactResponse,
    ContactTagCreate,
    ContactTagResponse,
    ContactTagsUpdate,
    ContactUpdate,
    ConversationDetail,
    ConversationPage,
    ConversationSummary,
    LeadStatusUpdate,
    ManualMessageCreate,
    MessageResponse,
)
from app.services.automation_engine import (
    PermanentMetaError,
    TransientMetaError,
    send_meta_text,
)
from app.services.meta_oauth import account_token_context, decrypt_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Inbox and CRM"])
LEAD_STATUSES = {value.value for value in LeadStatus}


def _require_manager(principal: Principal) -> None:
    if principal.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization role does not allow this action.",
        )


async def _load_contact(
    session: AsyncSession, principal: Principal, contact_id: UUID
) -> Contact:
    contact = await session.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.organization_id == principal.organization_id,
        )
    )
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found.")
    return contact


async def _tag_names(
    session: AsyncSession, organization_id: UUID, contact_ids: list[UUID]
) -> dict[UUID, list[str]]:
    if not contact_ids:
        return {}
    rows = (
        await session.execute(
            select(ContactTagAssignment.contact_id, ContactTag.name)
            .join(
                ContactTag,
                and_(
                    ContactTag.organization_id == ContactTagAssignment.organization_id,
                    ContactTag.id == ContactTagAssignment.tag_id,
                ),
            )
            .where(
                ContactTagAssignment.organization_id == organization_id,
                ContactTagAssignment.contact_id.in_(contact_ids),
            )
            .order_by(ContactTag.name)
        )
    ).all()
    result: dict[UUID, list[str]] = {contact_id: [] for contact_id in contact_ids}
    for contact_id, name in rows:
        result[contact_id].append(name)
    return result


def _contact_response(
    contact: Contact, platform: SocialPlatform, tags: list[str] | None = None
) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        social_account_id=contact.social_account_id,
        platform=platform,
        platform_customer_id=contact.platform_customer_id,
        display_name=contact.display_name,
        lead_status=contact.lead_status,
        custom_fields=contact.custom_fields,
        first_contact_at=contact.first_contact_at,
        last_interaction_at=contact.last_interaction_at,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        tags=tags or [],
    )


async def _contact_rows(
    session: AsyncSession,
    principal: Principal,
    *,
    q: str | None,
    lead_status: LeadStatus | None,
    platform: SocialPlatform | None = None,
    offset: int,
    limit: int,
    inbox_only: bool = False,
) -> tuple[list[tuple[Contact, SocialPlatform]], int]:
    filters = [Contact.organization_id == principal.organization_id]
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                Contact.display_name.ilike(pattern),
                Contact.platform_customer_id.ilike(pattern),
            )
        )
    if lead_status is not None:
        filters.append(Contact.lead_status == lead_status.value)
    if platform is not None:
        filters.append(
            select(SocialAccount.id)
            .where(
                SocialAccount.id == Contact.social_account_id,
                SocialAccount.organization_id == Contact.organization_id,
                SocialAccount.platform == platform,
            )
            .exists()
        )
    has_messages = (
        select(Message.id)
        .where(
            Message.organization_id == principal.organization_id,
            Message.contact_id == Contact.id,
            Message.message_type.in_(("incoming", "manual", "private", "direct")),
        )
        .exists()
    )
    if inbox_only:
        filters.append(has_messages)
    base = (
        select(Contact, SocialAccount.platform)
        .join(
            SocialAccount,
            and_(
                SocialAccount.id == Contact.social_account_id,
                SocialAccount.organization_id == Contact.organization_id,
            ),
        )
        .where(*filters)
    )
    total = int(
        await session.scalar(select(func.count()).select_from(Contact).where(*filters)) or 0
    )
    rows = (
        await session.execute(
            base.order_by(Contact.last_interaction_at.desc().nullslast(), Contact.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [(row[0], row[1]) for row in rows], total


@router.get("/conversations", response_model=ConversationPage)
async def list_conversations(
    q: str | None = Query(default=None, max_length=200),
    platform: SocialPlatform | None = None,
    lead_status: LeadStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationPage:
    rows, total = await _contact_rows(
        session,
        principal,
        q=q,
        lead_status=lead_status,
        platform=platform,
        offset=offset,
        limit=limit,
        inbox_only=True,
    )
    items: list[ConversationSummary] = []
    for contact, account_platform in rows:
        if platform is not None and account_platform != platform:
            continue
        latest = await session.scalar(
            select(Message)
            .where(
                Message.organization_id == principal.organization_id,
                Message.contact_id == contact.id,
                Message.message_type.in_(("incoming", "manual", "private", "direct")),
            )
            .order_by(
                func.coalesce(Message.platform_created_at, Message.created_at).desc(),
                Message.created_at.desc(),
            )
            .limit(1)
        )
        if latest is None:
            continue
        unread_count = int(
            await session.scalar(
                select(func.count(Message.id)).where(
                    Message.organization_id == principal.organization_id,
                    Message.contact_id == contact.id,
                    Message.message_type == "incoming",
                    Message.is_read.is_(False),
                )
            )
            or 0
        )
        items.append(
            ConversationSummary(
                contact_id=contact.id,
                display_name=contact.display_name,
                platform=account_platform,
                platform_customer_id=contact.platform_customer_id,
                latest_message_preview=latest.message_content[:240],
                latest_message_at=latest.platform_created_at or latest.created_at,
                unread_count=unread_count,
                lead_status=contact.lead_status,
            )
        )
    return ConversationPage(items=items, total=total, offset=offset, limit=limit)


@router.get("/conversations/{contact_id}", response_model=ConversationDetail)
async def get_conversation(
    contact_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationDetail:
    contact = await _load_contact(session, principal, contact_id)
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == contact.social_account_id,
            SocialAccount.organization_id == principal.organization_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found.")
    total = int(
        await session.scalar(
            select(func.count(Message.id)).where(
                Message.organization_id == principal.organization_id,
                Message.contact_id == contact.id,
                Message.message_type.in_(("incoming", "manual", "private", "direct")),
            )
        )
        or 0
    )
    messages = list(
        (
            await session.scalars(
                select(Message)
                .where(
                    Message.organization_id == principal.organization_id,
                    Message.contact_id == contact.id,
                    Message.message_type.in_(("incoming", "manual", "private", "direct")),
                )
                .order_by(
                    func.coalesce(Message.platform_created_at, Message.created_at).desc(),
                    Message.created_at.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    messages.reverse()
    tags = await _tag_names(session, principal.organization_id, [contact.id])
    return ConversationDetail(
        contact=_contact_response(contact, account.platform, tags.get(contact.id)),
        messages=[MessageResponse.model_validate(message) for message in messages],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch("/conversations/{contact_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_conversation_read(
    contact_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await _load_contact(session, principal, contact_id)
    await session.execute(
        update(Message)
        .where(
            Message.organization_id == principal.organization_id,
            Message.contact_id == contact_id,
            Message.message_type == "incoming",
            Message.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await session.commit()


@router.post(
    "/conversations/{contact_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_manual_message(
    contact_id: UUID,
    body: ManualMessageCreate,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    contact = await _load_contact(session, principal, contact_id)
    idempotency_key = f"manual:{principal.organization_id}:{contact.id}:{body.idempotency_key}"
    existing = await session.scalar(
        select(Message).where(
            Message.idempotency_key == idempotency_key,
            Message.organization_id == principal.organization_id,
        )
    )
    if existing is not None:
        if existing.delivery_status == "sent":
            return MessageResponse.model_validate(existing)
        if existing.delivery_status in {"failed", "uncertain"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This message attempt already finished; use a new request identifier to retry.",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This message is already being processed.",
        )
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == contact.social_account_id,
            SocialAccount.organization_id == principal.organization_id,
            SocialAccount.is_connected.is_(True),
        )
    )
    if account is None or not account.encrypted_access_token:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The connected social account is unavailable.")
    latest_inbound = await session.scalar(
        select(Message)
        .where(
            Message.organization_id == principal.organization_id,
            Message.contact_id == contact.id,
            Message.message_type == "incoming",
        )
        .order_by(
            func.coalesce(Message.platform_created_at, Message.created_at).desc(),
            Message.created_at.desc(),
        )
        .limit(1)
    )
    now = datetime.now(UTC)
    if latest_inbound is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A customer message is required before replying.",
        )
    last_customer_message_at = latest_inbound.platform_created_at or latest_inbound.created_at
    if last_customer_message_at.tzinfo is None:
        last_customer_message_at = last_customer_message_at.replace(tzinfo=UTC)
    if now - last_customer_message_at > timedelta(hours=24) or last_customer_message_at > now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The supported messaging window has expired for this conversation.",
        )

    message = Message(
        organization_id=principal.organization_id,
        automation_id=None,
        social_account_id=account.id,
        contact_id=contact.id,
        recipient_platform_id=contact.platform_customer_id,
        message_type="manual",
        message_content=body.text,
        delivery_status="sending",
        idempotency_key=idempotency_key,
        is_read=True,
    )
    session.add(message)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A message with this request identifier already exists.",
        ) from exc
    attempt = MessageDeliveryAttempt(
        organization_id=principal.organization_id,
        message_id=message.id,
        attempt_number=1,
        status="sending",
        created_at=now,
    )
    session.add(attempt)
    await session.commit()

    try:
        settings: Settings = request.app.state.settings
        token = decrypt_token(
            settings,
            account.encrypted_access_token,
            context=account_token_context(
                account.organization_id,
                account.platform.value,
                account.platform_account_id,
            ),
        )
        external_id = await send_meta_text(
            settings,
            account,
            token=token,
            recipient_id=contact.platform_customer_id,
            text=body.text,
        )
    except (TransientMetaError, PermanentMetaError, ValueError, RuntimeError) as exc:
        category = str(exc) if isinstance(exc, (TransientMetaError, PermanentMetaError)) else "token_unavailable"
        message.delivery_status = "uncertain" if category == "delivery_outcome_unknown" else "failed"
        attempt.status = "failed"
        attempt.error_category = category
        if category == "invalid_token":
            account.is_connected = False
            account.encrypted_access_token = None
            account.updated_at = datetime.now(UTC)
            await session.execute(
                update(Automation)
                .where(
                    Automation.organization_id == principal.organization_id,
                    Automation.social_account_id == account.id,
                    Automation.status == AutomationStatus.ACTIVE,
                )
                .values(status=AutomationStatus.PAUSED, updated_at=datetime.now(UTC))
            )
        await session.commit()
        logger.warning(
            "Manual Meta message was not confirmed",
            extra={
                "organization_id": str(principal.organization_id),
                "social_account_id": str(account.id),
                "message_id": str(message.id),
                "error_category": category,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta did not confirm the message. Check the conversation before retrying.",
        ) from exc

    message.delivery_status = "sent"
    message.external_message_id = external_id
    message.platform_created_at = datetime.now(UTC)
    attempt.status = "sent"
    attempt.external_message_id = external_id
    contact.last_interaction_at = message.platform_created_at
    await session.commit()
    await session.refresh(message)
    return MessageResponse.model_validate(message)


@router.get("/contacts", response_model=ContactPage)
async def list_contacts(
    q: str | None = Query(default=None, max_length=200),
    lead_status: LeadStatus | None = None,
    platform: SocialPlatform | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactPage:
    rows, total = await _contact_rows(
        session,
        principal,
        q=q,
        lead_status=lead_status,
        platform=platform,
        offset=offset,
        limit=limit,
    )
    tags = await _tag_names(session, principal.organization_id, [row[0].id for row in rows])
    return ContactPage(
        items=[_contact_response(contact, platform, tags.get(contact.id)) for contact, platform in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactResponse:
    _require_manager(principal)
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == body.social_account_id,
            SocialAccount.organization_id == principal.organization_id,
            SocialAccount.is_connected.is_(True),
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected social account not found.")
    contact = Contact(
        organization_id=principal.organization_id,
        social_account_id=account.id,
        platform_customer_id=body.platform_customer_id,
        display_name=body.display_name,
        custom_fields=body.custom_fields,
    )
    session.add(contact)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This platform customer is already in your contacts.",
        ) from exc
    await session.refresh(contact)
    return _contact_response(contact, account.platform)


@router.get("/contacts/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactResponse:
    contact = await _load_contact(session, principal, contact_id)
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == contact.social_account_id,
            SocialAccount.organization_id == principal.organization_id,
        )
    )
    tags = await _tag_names(session, principal.organization_id, [contact.id])
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found.")
    return _contact_response(contact, account.platform, tags.get(contact.id))


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    body: ContactUpdate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactResponse:
    _require_manager(principal)
    contact = await _load_contact(session, principal, contact_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)
    contact.updated_at = datetime.now(UTC)
    await session.commit()
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == contact.social_account_id,
            SocialAccount.organization_id == principal.organization_id,
        )
    )
    tags = await _tag_names(session, principal.organization_id, [contact.id])
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found.")
    return _contact_response(contact, account.platform, tags.get(contact.id))


@router.get("/contacts/{contact_id}/notes", response_model=list[ContactNoteResponse])
async def list_contact_notes(
    contact_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[ContactNoteResponse]:
    await _load_contact(session, principal, contact_id)
    notes = (
        await session.scalars(
            select(ContactNote)
            .where(
                ContactNote.organization_id == principal.organization_id,
                ContactNote.contact_id == contact_id,
            )
            .order_by(ContactNote.created_at.desc())
            .limit(200)
        )
    ).all()
    return [ContactNoteResponse.model_validate(note) for note in notes]


@router.post(
    "/contacts/{contact_id}/notes",
    response_model=ContactNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact_note(
    contact_id: UUID,
    body: ContactNoteCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactNoteResponse:
    await _load_contact(session, principal, contact_id)
    note = ContactNote(
        organization_id=principal.organization_id,
        contact_id=contact_id,
        author_user_id=principal.user_id,
        content=body.content,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return ContactNoteResponse.model_validate(note)


@router.get("/tags", response_model=list[ContactTagResponse])
async def list_tags(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[ContactTagResponse]:
    tags = (
        await session.scalars(
            select(ContactTag)
            .where(ContactTag.organization_id == principal.organization_id)
            .order_by(ContactTag.name)
        )
    ).all()
    return [ContactTagResponse.model_validate(tag) for tag in tags]


@router.post("/tags", response_model=ContactTagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: ContactTagCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactTagResponse:
    _require_manager(principal)
    tag = ContactTag(organization_id=principal.organization_id, name=body.name)
    session.add(tag)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This tag already exists.") from exc
    await session.refresh(tag)
    return ContactTagResponse.model_validate(tag)


@router.put("/contacts/{contact_id}/tags", response_model=ContactResponse)
async def replace_contact_tags(
    contact_id: UUID,
    body: ContactTagsUpdate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactResponse:
    _require_manager(principal)
    contact = await _load_contact(session, principal, contact_id)
    unique_ids = list(dict.fromkeys(body.tag_ids))
    tags = list(
        (
            await session.scalars(
                select(ContactTag).where(
                    ContactTag.organization_id == principal.organization_id,
                    ContactTag.id.in_(unique_ids),
                )
            )
        ).all()
    ) if unique_ids else []
    if len(tags) != len(unique_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="One or more tags are unavailable.")
    await session.execute(
        delete(ContactTagAssignment).where(
            ContactTagAssignment.organization_id == principal.organization_id,
            ContactTagAssignment.contact_id == contact.id,
        )
    )
    session.add_all(
        ContactTagAssignment(
            organization_id=principal.organization_id,
            contact_id=contact.id,
            tag_id=tag_id,
        )
        for tag_id in unique_ids
    )
    await session.commit()
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == contact.social_account_id,
            SocialAccount.organization_id == principal.organization_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found.")
    return _contact_response(contact, account.platform, [tag.name for tag in tags])


@router.get("/leads", response_model=ContactPage)
async def list_leads(
    q: str | None = Query(default=None, max_length=200),
    lead_status: LeadStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactPage:
    rows, total = await _contact_rows(
        session, principal, q=q, lead_status=lead_status, offset=offset, limit=limit
    )
    tags = await _tag_names(session, principal.organization_id, [row[0].id for row in rows])
    return ContactPage(
        items=[_contact_response(contact, platform, tags.get(contact.id)) for contact, platform in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch("/leads/{contact_id}/status", response_model=ContactResponse)
async def update_lead_status(
    contact_id: UUID,
    body: LeadStatusUpdate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> ContactResponse:
    _require_manager(principal)
    contact = await _load_contact(session, principal, contact_id)
    previous_status = contact.lead_status
    if previous_status != body.status.value:
        contact.lead_status = body.status.value
        contact.updated_at = datetime.now(UTC)
        session.add(
            LeadActivity(
                organization_id=principal.organization_id,
                contact_id=contact.id,
                actor_user_id=principal.user_id,
                activity_type="status_changed",
                detail=f"{previous_status}->{body.status.value}",
            )
        )
        await session.commit()
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == contact.social_account_id,
            SocialAccount.organization_id == principal.organization_id,
        )
    )
    tags = await _tag_names(session, principal.organization_id, [contact.id])
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found.")
    return _contact_response(contact, account.platform, tags.get(contact.id))


@router.get("/leads/{contact_id}/activities")
async def list_lead_activities(
    contact_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    await _load_contact(session, principal, contact_id)
    activities = (
        await session.scalars(
            select(LeadActivity)
            .where(
                LeadActivity.organization_id == principal.organization_id,
                LeadActivity.contact_id == contact_id,
            )
            .order_by(LeadActivity.created_at.desc())
            .limit(200)
        )
    ).all()
    return [
        {
            "id": activity.id,
            "actor_user_id": activity.actor_user_id,
            "activity_type": activity.activity_type,
            "detail": activity.detail,
            "created_at": activity.created_at,
        }
        for activity in activities
    ]


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsResponse:
    now = datetime.now(UTC)
    end = date_to or now
    start = date_from or (end - timedelta(days=30))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if end <= start or end - start > timedelta(days=366):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a valid date range of 366 days or less.",
        )
    org_id = principal.organization_id
    accounts_count = int(
        await session.scalar(
            select(func.count(SocialAccount.id)).where(
                SocialAccount.organization_id == org_id,
                SocialAccount.is_connected.is_(True),
            )
        )
        or 0
    )
    active_automations = int(
        await session.scalar(
            select(func.count(Automation.id)).where(
                Automation.organization_id == org_id,
                Automation.status == AutomationStatus.ACTIVE,
            )
        )
        or 0
    )
    execution_counts = (
        await session.execute(
            select(AutomationExecution.status, func.count(AutomationExecution.id))
            .where(
                AutomationExecution.organization_id == org_id,
                AutomationExecution.started_at >= start,
                AutomationExecution.started_at < end,
            )
            .group_by(AutomationExecution.status)
        )
    ).all()
    execution_by_status = {name: count for name, count in execution_counts}

    message_time = func.coalesce(Message.platform_created_at, Message.created_at)
    message_rows = (
        await session.execute(
            select(
                SocialAccount.platform,
                Message.message_type,
                func.count(Message.id),
            )
            .join(
                SocialAccount,
                and_(
                    SocialAccount.id == Message.social_account_id,
                    SocialAccount.organization_id == Message.organization_id,
                ),
            )
            .where(
                Message.organization_id == org_id,
                message_time >= start,
                message_time < end,
                Message.message_type.in_(("incoming", "manual", "private", "direct")),
                Message.delivery_status.in_(("received", "sent")),
            )
            .group_by(SocialAccount.platform, Message.message_type)
        )
    ).all()
    sent_count = sum(count for _, kind, count in message_rows if kind != "incoming")
    received_count = sum(count for _, kind, count in message_rows if kind == "incoming")
    connected_platforms = (
        await session.execute(
            select(SocialAccount.platform, func.count(SocialAccount.id))
            .where(
                SocialAccount.organization_id == org_id,
                SocialAccount.is_connected.is_(True),
            )
            .group_by(SocialAccount.platform)
        )
    ).all()
    platform_totals: dict[str, dict[str, int]] = {}
    for platform_value, _count in connected_platforms:
        platform_name = platform_value.value if hasattr(platform_value, "value") else str(platform_value)
        platform_totals[platform_name] = {"sent": 0, "received": 0}
    for platform_value, kind, count in message_rows:
        platform_name = platform_value.value if hasattr(platform_value, "value") else str(platform_value)
        totals = platform_totals.setdefault(platform_name, {"sent": 0, "received": 0})
        totals["received" if kind == "incoming" else "sent"] += count

    contacts_count = int(
        await session.scalar(select(func.count(Contact.id)).where(Contact.organization_id == org_id)) or 0
    )
    new_leads = int(
        await session.scalar(
            select(func.count(Contact.id)).where(
                Contact.organization_id == org_id,
                Contact.lead_status == LeadStatus.NEW.value,
                Contact.created_at >= start,
                Contact.created_at < end,
            )
        )
        or 0
    )
    converted_leads = int(
        await session.scalar(
            select(func.count(func.distinct(LeadActivity.contact_id))).where(
                LeadActivity.organization_id == org_id,
                LeadActivity.activity_type == "status_changed",
                LeadActivity.detail.like("%->converted"),
                LeadActivity.created_at >= start,
                LeadActivity.created_at < end,
            )
        )
        or 0
    )
    coverage_start = await session.scalar(
        select(func.min(message_time)).where(Message.organization_id == org_id)
    )
    daily_rows = (
        await session.execute(
            select(
                func.date(message_time),
                Message.message_type,
                func.count(Message.id),
            )
            .where(
                Message.organization_id == org_id,
                message_time >= start,
                message_time < end,
                Message.message_type.in_(("incoming", "manual", "private", "direct")),
                Message.delivery_status.in_(("received", "sent")),
            )
            .group_by(func.date(message_time), Message.message_type)
            .order_by(func.date(message_time))
        )
    ).all()
    daily: dict[str, dict[str, int]] = {}
    for day_value, kind, count in daily_rows:
        day = day_value.isoformat() if hasattr(day_value, "isoformat") else str(day_value)
        entry = daily.setdefault(day, {"sent": 0, "received": 0})
        entry["received" if kind == "incoming" else "sent"] += count
    chart: list[dict[str, Any]] = []
    cursor = start.date()
    final_day = (end - timedelta(microseconds=1)).date()
    while cursor <= final_day:
        key = cursor.isoformat()
        counts = daily.get(key, {"sent": 0, "received": 0})
        chart.append({"date": key, **counts})
        cursor += timedelta(days=1)
    weekly_totals: dict[str, dict[str, int]] = {}
    for day_key, counts in daily.items():
        event_day = date.fromisoformat(day_key)
        monday = event_day - timedelta(days=event_day.weekday())
        key = monday.isoformat()
        totals = weekly_totals.setdefault(key, {"sent": 0, "received": 0})
        totals["sent"] += counts["sent"]
        totals["received"] += counts["received"]

    performance_rows = (
        await session.execute(
            select(
                Automation.id,
                Automation.name,
                AutomationExecution.status,
                func.count(AutomationExecution.id),
            )
            .join(
                AutomationExecution,
                and_(
                    AutomationExecution.automation_id == Automation.id,
                    AutomationExecution.organization_id == Automation.organization_id,
                ),
            )
            .where(
                Automation.organization_id == org_id,
                AutomationExecution.started_at >= start,
                AutomationExecution.started_at < end,
            )
            .group_by(Automation.id, Automation.name, AutomationExecution.status)
            .order_by(Automation.name)
        )
    ).all()
    performance: dict[UUID, dict[str, Any]] = {}
    for automation_id, name, execution_status, count in performance_rows:
        row = performance.setdefault(
            automation_id,
            {"automation_id": automation_id, "name": name, "executions": 0, "successful": 0, "failed": 0},
        )
        row["executions"] += count
        if execution_status == "sent":
            row["successful"] += count
        elif execution_status == "failed":
            row["failed"] += count

    metric = lambda value: {"value": int(value), "available": True}
    return AnalyticsResponse(
        date_from=start,
        date_to=end,
        coverage_start=coverage_start,
        connected_accounts=metric(accounts_count),
        active_automations=metric(active_automations),
        automation_executions=metric(sum(execution_by_status.values())),
        successful_executions=metric(execution_by_status.get("sent", 0)),
        failed_executions=metric(execution_by_status.get("failed", 0)),
        messages_sent=metric(sent_count),
        messages_received=metric(received_count),
        total_contacts=metric(contacts_count),
        new_leads=metric(new_leads),
        converted_leads=metric(converted_leads),
        daily_messages=chart,
        weekly_messages=[
            {"week_start": week_start, **counts}
            for week_start, counts in sorted(weekly_totals.items())
        ],
        platform_breakdown=[
            {"platform": platform, **counts}
            for platform, counts in sorted(platform_totals.items())
        ],
        automation_performance=list(performance.values()),
    )
