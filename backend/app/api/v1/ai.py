from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.exceptions import RedisError
from sqlalchemy import case, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, get_current_principal
from app.core.config import Settings
from app.db.session import get_db_session
from app.db.tenant import set_tenant_organization
from app.models import (
    AIConversation,
    AIMessage,
    AIProviderConfiguration,
    AIUsageRecord,
    BusinessKnowledge,
)
from app.schemas.ai import (
    AIChatRequest,
    AIChatResponse,
    AIConversationResponse,
    AIAssistRequest,
    AIAssistResponse,
    AIMessageResponse,
    AIProviderStatus,
    AISettingsResponse,
    AISettingsUpdate,
    AIUsageSummary,
    BusinessKnowledgeResponse,
    BusinessKnowledgeUpdate,
)
from app.services.ai import (
    SelectedProvider,
    available_providers,
    estimated_cost,
    generate,
    load_knowledge,
    make_usage_record,
    selected_provider,
)
from app.services.ai_providers import AIInputTooLarge, AIProviderError, GeneratedText

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/providers", response_model=AISettingsResponse)
async def get_ai_settings(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AISettingsResponse:
    providers = available_providers(request.app.state.settings)
    saved = await session.scalar(
        select(AIProviderConfiguration).where(
            AIProviderConfiguration.organization_id == principal.organization_id
        )
    )
    configured = {item["provider"]: item for item in providers if item["configured"]}
    selected = configured.get(saved.provider) if saved else None
    if saved is not None:
        if selected and selected["model"] == saved.model:
            selected_provider_name, selected_model = saved.provider, saved.model
        else:
            selected_provider_name, selected_model = None, None
    else:
        selected_provider_name = "openai" if "openai" in configured else ("gemini" if "gemini" in configured else None)
        selected_model = configured[selected_provider_name]["model"] if selected_provider_name else None
    return AISettingsResponse(
        providers=[AIProviderStatus(**item) for item in providers],
        selected_provider=selected_provider_name,
        selected_model=selected_model,
    )


@router.put("/providers", response_model=AISettingsResponse)
async def update_ai_settings(
    payload: AISettingsUpdate,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AISettingsResponse:
    providers = available_providers(request.app.state.settings)
    choice = next((item for item in providers if item["provider"] == payload.provider), None)
    if choice is None or not choice["configured"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The {payload.provider} provider is not configured on this server.",
        )
    if payload.model != choice["model"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Select a model configured by the service operator.",
        )
    values = {"organization_id": principal.organization_id, "provider": payload.provider, "model": payload.model}
    dialect = session.get_bind().dialect.name
    statement = (
        sqlite_insert(AIProviderConfiguration)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["organization_id"],
            set_={
                "provider": payload.provider,
                "model": payload.model,
                "updated_at": datetime.now(UTC),
            },
        )
        if dialect == "sqlite"
        else pg_insert(AIProviderConfiguration)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["organization_id"],
            set_={
                "provider": payload.provider,
                "model": payload.model,
                "updated_at": datetime.now(UTC),
            },
        )
    )
    await session.execute(statement)
    await session.commit()
    await set_tenant_organization(session, principal.organization_id)
    return await get_ai_settings(request, principal, session)


@router.get("/conversations", response_model=list[AIConversationResponse])
async def list_ai_conversations(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[AIConversationResponse]:
    conversations = list(
        (
            await session.scalars(
                select(AIConversation)
                .where(AIConversation.organization_id == principal.organization_id)
                .order_by(AIConversation.updated_at.desc())
                .limit(50)
            )
        ).all()
    )
    return [
        AIConversationResponse(
            id=item.id,
            title=item.title,
            updated_at=item.updated_at,
            messages=[],
        )
        for item in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=AIConversationResponse)
async def get_ai_conversation(
    conversation_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AIConversationResponse:
    conversation = await _get_conversation(session, principal.organization_id, conversation_id)
    messages = list(
        (
            await session.scalars(
                select(AIMessage)
                .where(
                    AIMessage.organization_id == principal.organization_id,
                    AIMessage.conversation_id == conversation.id,
                )
                .order_by(AIMessage.created_at, AIMessage.id)
            )
        ).all()
    )
    return AIConversationResponse(
        id=conversation.id,
        title=conversation.title,
        updated_at=conversation.updated_at,
        messages=[AIMessageResponse.model_validate(message) for message in messages],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_ai_conversation(
    conversation_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    conversation = await _get_conversation(session, principal.organization_id, conversation_id)
    await session.delete(conversation)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chat", response_model=AIChatResponse)
async def chat(
    payload: AIChatRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AIChatResponse:
    settings: Settings = request.app.state.settings
    selection = await _provider_selection(session, settings, principal.organization_id)
    conversation = (
        await _get_conversation(session, principal.organization_id, payload.conversation_id)
        if payload.conversation_id
        else AIConversation(
            organization_id=principal.organization_id,
            title=payload.message.strip()[:157] + ("..." if len(payload.message.strip()) > 157 else ""),
        )
    )
    if conversation.id is None:
        session.add(conversation)
        await session.flush()
    previous_messages = list(
        (
            await session.scalars(
                select(AIMessage)
                .where(
                    AIMessage.organization_id == principal.organization_id,
                    AIMessage.conversation_id == conversation.id,
                )
                .order_by(AIMessage.created_at.desc(), AIMessage.id.desc())
                .limit(20)
            )
        ).all()
    )
    session.add(
        AIMessage(
            organization_id=principal.organization_id,
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
        )
    )
    conversation.updated_at = datetime.now(UTC)
    await session.flush()
    await _enforce_limits(request, principal.organization_id, settings)
    knowledge = await load_knowledge(session, principal.organization_id)
    await session.commit()
    await set_tenant_organization(session, principal.organization_id)

    context_messages = [
        {"role": item.role, "content": item.content}
        for item in reversed(previous_messages)
    ]
    context_messages.append({"role": "user", "content": payload.message})
    prompt = {
        "task": "Answer the customer's question about DM Karo. If the business knowledge does not answer a business-specific question, say so.",
        "conversation": context_messages,
        "business_knowledge": knowledge,
    }
    return await _complete(
        request,
        session,
        principal.organization_id,
        selection,
        purpose="chat",
        prompt=prompt,
        conversation=conversation,
    )


@router.post("/assist", response_model=AIAssistResponse)
async def assist(
    payload: AIAssistRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AIAssistResponse:
    settings: Settings = request.app.state.settings
    selection = await _provider_selection(session, settings, principal.organization_id)
    if payload.action == "translate" and not payload.language.strip():
        raise HTTPException(status_code=422, detail="Choose a target language for translation.")
    await _enforce_limits(request, principal.organization_id, settings)
    knowledge = await load_knowledge(session, principal.organization_id)
    prompt = {
        "task": payload.action,
        "customer_input": payload.input_text,
        "additional_context": payload.context,
        "target_language": payload.language,
        "business_knowledge": knowledge,
        "review_notice": "This output is an AI suggestion, not a verified fact or an instruction to send.",
    }
    result, cost = await _generate_and_track(
        request,
        session,
        principal.organization_id,
        selection,
        purpose=payload.action,
        prompt=prompt,
    )
    return AIAssistResponse(
        result=result.text,
        provider=selection.provider,
        model=selection.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        estimated_cost_usd=float(cost) if cost is not None else None,
    )


@router.get("/knowledge", response_model=BusinessKnowledgeResponse)
async def get_business_knowledge(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BusinessKnowledgeResponse:
    knowledge = await session.scalar(
        select(BusinessKnowledge).where(
            BusinessKnowledge.organization_id == principal.organization_id
        )
    )
    if knowledge is None:
        return BusinessKnowledgeResponse(
            business_name="",
            description="",
            products_services="",
            faqs="",
            website_information="",
            custom_instructions="",
            updated_at=None,
        )
    return BusinessKnowledgeResponse.model_validate(knowledge)


@router.put("/knowledge", response_model=BusinessKnowledgeResponse)
async def update_business_knowledge(
    payload: BusinessKnowledgeUpdate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BusinessKnowledgeResponse:
    values = {
        "organization_id": principal.organization_id,
        **payload.model_dump(),
        "updated_at": datetime.now(UTC),
    }
    dialect = session.get_bind().dialect.name
    statement = (
        sqlite_insert(BusinessKnowledge)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["organization_id"],
            set_={**payload.model_dump(), "updated_at": values["updated_at"]},
        )
        if dialect == "sqlite"
        else pg_insert(BusinessKnowledge)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["organization_id"],
            set_={**payload.model_dump(), "updated_at": values["updated_at"]},
        )
    )
    await session.execute(statement)
    await session.commit()
    await set_tenant_organization(session, principal.organization_id)
    knowledge = await session.scalar(
        select(BusinessKnowledge).where(
            BusinessKnowledge.organization_id == principal.organization_id
        )
    )
    if knowledge is None:
        raise HTTPException(status_code=500, detail="Business knowledge could not be saved.")
    return BusinessKnowledgeResponse.model_validate(knowledge)


@router.get("/usage", response_model=AIUsageSummary)
async def get_ai_usage(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AIUsageSummary:
    since = datetime.now(UTC) - timedelta(days=30)
    totals = (
        await session.execute(
            select(
                func.count(AIUsageRecord.id),
                func.sum(case((AIUsageRecord.request_status == "succeeded", 1), else_=0)),
                func.sum(case((AIUsageRecord.request_status == "failed", 1), else_=0)),
                func.sum(AIUsageRecord.input_tokens),
                func.sum(AIUsageRecord.output_tokens),
                func.sum(AIUsageRecord.estimated_cost_usd),
            ).where(
                AIUsageRecord.organization_id == principal.organization_id,
                AIUsageRecord.created_at >= since,
            )
        )
    ).one()
    return AIUsageSummary(
        since=since,
        until=datetime.now(UTC),
        request_count=int(totals[0] or 0),
        successful_count=int(totals[1] or 0),
        failed_count=int(totals[2] or 0),
        input_tokens=int(totals[3] or 0),
        output_tokens=int(totals[4] or 0),
        estimated_cost_usd=float(totals[5]) if totals[5] is not None else None,
        daily_request_limit=request.app.state.settings.ai_daily_request_limit,
    )


async def _provider_selection(
    session: AsyncSession,
    settings: Settings,
    organization_id: UUID,
) -> SelectedProvider:
    try:
        return await selected_provider(session, settings, organization_id)
    except AIProviderError as exc:
        _raise_provider_http_error(exc)


async def _complete(
    request: Request,
    session: AsyncSession,
    organization_id: UUID,
    selection: SelectedProvider,
    *,
    purpose: str,
    prompt: dict[str, object],
    conversation: AIConversation,
) -> AIChatResponse:
    try:
        result, cost = await _generate_and_track(
            request,
            session,
            organization_id,
            selection,
            purpose=purpose,
            prompt=prompt,
        )
    except HTTPException:
        raise
    await set_tenant_organization(session, organization_id)
    session.add(
        AIMessage(
            organization_id=organization_id,
            conversation_id=conversation.id,
            role="assistant",
            content=result.text,
            provider=selection.provider,
            model=selection.model,
        )
    )
    conversation.updated_at = datetime.now(UTC)
    await session.commit()
    return AIChatResponse(
        conversation_id=conversation.id,
        answer=result.text,
        provider=selection.provider,
        model=selection.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        estimated_cost_usd=float(cost) if cost is not None else None,
    )


async def _generate_and_track(
    request: Request,
    session: AsyncSession,
    organization_id: UUID,
    selection: SelectedProvider,
    *,
    purpose: str,
    prompt: dict[str, object],
) -> tuple[GeneratedText, object | None]:
    settings: Settings = request.app.state.settings
    try:
        result = await generate(settings, selection=selection, purpose=purpose, payload=prompt)
    except AIInputTooLarge as exc:
        await _save_usage(session, organization_id, selection, purpose, "failed")
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The combined prompt and saved business context exceed the configured input limit.",
        ) from exc
    except AIProviderError as exc:
        await _save_usage(session, organization_id, selection, purpose, "failed")
        _raise_provider_http_error(exc)
    cost = estimated_cost(settings, selection.provider, result)
    await _save_usage(session, organization_id, selection, purpose, "succeeded", result=result, cost=cost)
    return result, cost


async def _save_usage(
    session: AsyncSession,
    organization_id: UUID,
    selection: SelectedProvider,
    purpose: str,
    request_status: str,
    *,
    result: GeneratedText | None = None,
    cost: Decimal | None = None,
) -> None:
    session.add(
        make_usage_record(
            organization_id,
            selection,
            purpose,
            request_status,
            result=result,
            cost=cost,
        )
    )
    await session.commit()
    await set_tenant_organization(session, organization_id)


def _raise_provider_http_error(error: AIProviderError) -> None:
    if error.category in {"no_provider_configured", "selected_provider_not_configured", "provider_not_configured"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No configured AI provider is available. Configure an AI provider API key on the server.",
        ) from error
    if error.category == "input_too_large":
        raise HTTPException(status_code=413, detail="The AI input exceeds the configured limit.") from error
    if error.category == "provider_timeout":
        raise HTTPException(status_code=504, detail="The AI provider timed out. Please try again.") from error
    if error.category == "provider_rate_limited":
        raise HTTPException(status_code=503, detail="The AI provider is rate limiting requests. Please try again shortly.") from error
    if error.category in {"provider_temporarily_unavailable", "provider_request_failed"}:
        raise HTTPException(status_code=502, detail="The AI provider could not complete the request.") from error
    raise HTTPException(status_code=502, detail="The AI request could not be completed.") from error


async def _get_conversation(
    session: AsyncSession,
    organization_id: UUID,
    conversation_id: UUID,
) -> AIConversation:
    conversation = await session.scalar(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.organization_id == organization_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="AI conversation not found.")
    return conversation


async def _enforce_limits(request: Request, organization_id: UUID, settings: Settings) -> None:
    now = datetime.now(UTC)
    minute_key = f"ai:{{{organization_id}}}:minute"
    day_key = f"ai:{{{organization_id}}}:day:{now:%Y%m%d}"
    script = """
    local minute = redis.call('INCR', KEYS[1])
    if minute == 1 then redis.call('EXPIRE', KEYS[1], 60) end
    local daily = redis.call('INCR', KEYS[2])
    if daily == 1 then redis.call('EXPIRE', KEYS[2], 86400) end
    if minute > tonumber(ARGV[1]) then return -1 end
    if daily > tonumber(ARGV[2]) then return -2 end
    return daily
    """
    try:
        result = int(
            await request.app.state.redis_client.eval(
                script,
                2,
                minute_key,
                day_key,
                settings.ai_requests_per_minute,
                settings.ai_daily_request_limit,
            )
        )
    except RedisError as exc:
        logger.error("ai_rate_limit_unavailable", extra={"organization_id": str(organization_id)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI requests are temporarily unavailable because rate limiting is unavailable.",
        ) from exc
    if result == -1:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI request rate limit reached. Try again in a minute.",
            headers={"Retry-After": "60"},
        )
    if result == -2:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Your organization's daily AI request limit has been reached.",
            headers={"Retry-After": "3600"},
        )
