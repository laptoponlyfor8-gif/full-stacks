import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, get_current_principal
from app.core.config import Settings
from app.db.session import get_db_session
from app.models import (
    Automation,
    AutomationExecution,
    AutomationKeyword,
    Message,
    SocialAccount,
)
from app.models.enums import AutomationStatus
from app.schemas.automation import (
    AutomationCreate,
    AutomationExecutionResponse,
    AutomationResponse,
    AutomationUpdate,
    KeywordInput,
)
from app.services.meta_oauth import (
    MetaProviderError,
    account_token_context,
    decrypt_token,
    resolve_content_id,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/automations", tags=["Automations"])


@router.get("", response_model=list[AutomationResponse])
async def list_automations(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[AutomationResponse]:
    records = list(
        (
            await session.scalars(
                select(Automation)
                .where(Automation.organization_id == principal.organization_id)
                .order_by(Automation.created_at.desc())
            )
        ).all()
    )
    return [await _response(session, record) for record in records]


@router.post("", response_model=AutomationResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: AutomationCreate,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AutomationResponse:
    account = await _connected_account(session, principal, body.social_account_id)
    if account.platform != body.platform:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Platform does not match the selected account.")
    content_id = ""
    if body.trigger_type == "comment":
        content_id = await _resolve_content(request.app.state.settings, account, body.content_url)
    record = Automation(
        organization_id=principal.organization_id,
        social_account_id=account.id,
        name=body.name,
        content_url=body.content_url,
        platform_content_id=content_id,
        trigger_type=body.trigger_type,
        content_type=body.content_type,
        status=AutomationStatus.DRAFT,
        public_reply_enabled=body.public_reply_enabled,
        public_reply_text=body.public_reply_text,
        private_reply_text=body.private_reply_text,
    )
    session.add(record)
    await session.flush()
    await _replace_keywords(session, principal.organization_id, record.id, body.keywords)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more keyword rules conflict with this automation.",
        ) from exc
    await session.refresh(record)
    return await _response(session, record)


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    automation_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AutomationResponse:
    return await _response(session, await _load_automation(session, principal, automation_id))


@router.patch("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    automation_id: UUID,
    body: AutomationUpdate,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AutomationResponse:
    record = await _load_automation(session, principal, automation_id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return await _response(session, record)
    account = None
    if "social_account_id" in updates:
        account = await _connected_account(session, principal, updates.pop("social_account_id"))
        record.social_account_id = account.id
    if "platform" in updates:
        platform = updates.pop("platform")
        if account is None:
            account = await _connected_account(session, principal, record.social_account_id)
        if account.platform != platform:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Platform does not match the selected account.")
    if "content_url" in updates or account is not None:
        if record.trigger_type != "comment":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Direct-message automations do not use a post URL.")
        record.content_url = updates.pop("content_url", record.content_url)
        if account is None:
            account = await _connected_account(session, principal, record.social_account_id)
        record.platform_content_id = await _resolve_content(
            request.app.state.settings,
            account,
            record.content_url,
        )
    if "keywords" in updates:
        if record.status == AutomationStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pause the automation before changing keyword rules.",
            )
        await _replace_keywords(session, principal.organization_id, record.id, updates.pop("keywords"))
        await session.flush()
    requested_status = updates.pop("status", None)
    for key, value in updates.items():
        setattr(record, key, value)
    if requested_status is not None:
        if requested_status == AutomationStatus.ACTIVE:
            await _validate_activation(session, record)
        record.status = requested_status
    record.updated_at = datetime.now(UTC)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The automation update conflicts with an existing record.") from exc
    await session.refresh(record)
    return await _response(session, record)


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    record = await _load_automation(session, principal, automation_id)
    if record.status not in {AutomationStatus.DRAFT, AutomationStatus.PAUSED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pause the automation before deleting it.")
    await session.execute(
        delete(AutomationKeyword).where(
            AutomationKeyword.organization_id == principal.organization_id,
            AutomationKeyword.automation_id == record.id,
        )
    )
    await session.delete(record)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This automation has execution history and cannot be deleted.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{automation_id}/executions", response_model=list[AutomationExecutionResponse])
async def list_automation_executions(
    automation_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[AutomationExecutionResponse]:
    await _load_automation(session, principal, automation_id)
    executions = (
        await session.scalars(
            select(AutomationExecution)
            .where(
                AutomationExecution.organization_id == principal.organization_id,
                AutomationExecution.automation_id == automation_id,
            )
            .order_by(AutomationExecution.started_at.desc())
            .limit(100)
        )
    ).all()
    return [
        AutomationExecutionResponse(
            id=item.id,
            status=item.status,
            error_category=item.error_category,
            started_at=item.started_at,
            finished_at=item.finished_at,
        )
        for item in executions
    ]


async def _connected_account(session, principal: Principal, account_id: UUID) -> SocialAccount:
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == account_id,
            SocialAccount.organization_id == principal.organization_id,
            SocialAccount.is_connected.is_(True),
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected social account not found.")
    if not account.encrypted_access_token:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reconnect the social account before using it.")
    return account


async def _resolve_content(settings: Settings, account: SocialAccount, content_url: str) -> str:
    try:
        token = decrypt_token(
            settings,
            account.encrypted_access_token or "",
            context=account_token_context(
                account.organization_id,
                account.platform.value,
                account.platform_account_id,
            ),
        )
        return await resolve_content_id(
            settings,
            platform=account.platform.value,
            platform_account_id=account.platform_account_id,
            access_token=token,
            permalink=content_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except MetaProviderError as exc:
        logger.warning("automation_content_resolution_failed", extra={"platform": account.platform.value})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Meta could not verify this content permalink.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The connected account token is unavailable.") from exc


async def _load_automation(session, principal: Principal, automation_id: UUID) -> Automation:
    record = await session.scalar(
        select(Automation).where(
            Automation.id == automation_id,
            Automation.organization_id == principal.organization_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation not found.")
    return record


async def _replace_keywords(session, organization_id: UUID, automation_id: UUID, keywords: list[KeywordInput]) -> None:
    keywords = [
        item if isinstance(item, KeywordInput) else KeywordInput.model_validate(item)
        for item in keywords
    ]
    existing = list(
        (
            await session.scalars(
                select(AutomationKeyword).where(
                    AutomationKeyword.organization_id == organization_id,
                    AutomationKeyword.automation_id == automation_id,
                )
            )
        ).all()
    )
    referenced = set(
        (
            await session.scalars(
                select(AutomationExecution.matched_keyword_id).where(
                    AutomationExecution.organization_id == organization_id,
                    AutomationExecution.automation_id == automation_id,
                    AutomationExecution.matched_keyword_id.is_not(None),
                )
            )
        ).all()
    )
    incoming = {item.keyword.casefold(): item for item in keywords}
    old_by_keyword = {item.keyword.casefold(): item for item in existing}
    for normalized, rule in old_by_keyword.items():
        replacement = incoming.pop(normalized, None)
        if replacement is not None:
            rule.keyword = replacement.keyword
            rule.match_type = replacement.match_type
            rule.is_active = True
        elif rule.id in referenced:
            rule.is_active = False
        else:
            await session.delete(rule)
    for keyword in incoming.values():
        session.add(
            AutomationKeyword(
                organization_id=organization_id,
                automation_id=automation_id,
                keyword=keyword.keyword,
                match_type=keyword.match_type,
                is_active=True,
            )
        )
    await session.flush()


async def _validate_activation(session, record: Automation) -> None:
    count = await session.scalar(
        select(func.count()).select_from(AutomationKeyword).where(
            AutomationKeyword.organization_id == record.organization_id,
            AutomationKeyword.automation_id == record.id,
            AutomationKeyword.is_active.is_(True),
        )
    )
    if not count:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Add at least one active keyword before activating.")
    if record.trigger_type == "direct_message" and not record.private_reply_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A direct-message response is required.")
    if record.trigger_type == "comment" and not (record.private_reply_text or (record.public_reply_enabled and record.public_reply_text)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Configure a private or public reply before activating.")


async def _response(session, record: Automation) -> AutomationResponse:
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == record.social_account_id,
            SocialAccount.organization_id == record.organization_id,
        )
    )
    rules = list(
        (
            await session.scalars(
                select(AutomationKeyword).where(
                    AutomationKeyword.organization_id == record.organization_id,
                    AutomationKeyword.automation_id == record.id,
                ).where(AutomationKeyword.is_active.is_(True)).order_by(AutomationKeyword.id)
            )
        ).all()
    )
    executions = int(
        await session.scalar(
            select(func.count()).select_from(AutomationExecution).where(
                AutomationExecution.organization_id == record.organization_id,
                AutomationExecution.automation_id == record.id,
            )
        )
        or 0
    )
    sent = int(
        await session.scalar(
            select(func.count()).select_from(Message).where(
                Message.organization_id == record.organization_id,
                Message.automation_id == record.id,
                Message.delivery_status == "sent",
            )
        )
        or 0
    )
    failed = int(
        await session.scalar(
            select(func.count()).select_from(Message).where(
                Message.organization_id == record.organization_id,
                Message.automation_id == record.id,
                Message.delivery_status.in_(("failed", "uncertain")),
            )
        )
        or 0
    )
    return AutomationResponse(
        id=record.id,
        social_account_id=record.social_account_id,
        platform=account.platform if account else "instagram",
        account_name=account.account_name if account else "Unavailable account",
        name=record.name,
        trigger_type=record.trigger_type,
        content_type=record.content_type,
        content_url=record.content_url,
        status=record.status,
        keywords=[KeywordInput(keyword=rule.keyword, match_type=rule.match_type) for rule in rules],
        private_reply_text=record.private_reply_text,
        public_reply_enabled=record.public_reply_enabled,
        public_reply_text=record.public_reply_text,
        created_at=record.created_at,
        updated_at=record.updated_at,
        executions=executions,
        sent_messages=sent,
        failed_messages=failed,
    )
