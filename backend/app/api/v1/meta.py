import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, get_current_principal
from app.core.config import Settings
from app.core.security import has_expired
from app.db.session import get_db_session
from app.db.tenant import set_tenant_organization, set_tenant_user
from app.models import MetaWebhookAccountRoute, Organization, OrganizationMember, SocialAccount
from app.models.enums import SocialPlatform
from app.schemas.meta import (
    FacebookPageOption,
    FacebookPageSelection,
    OAuthStartResponse,
    SocialAccountResponse,
)
from app.services.meta_oauth import (
    OAUTH_STATE_TTL_SECONDS,
    PENDING_PAGE_TTL_SECONDS,
    MetaProviderError,
    account_token_context,
    build_authorization_url,
    connect_instagram,
    decrypt_token,
    encrypt_token,
    inspect_facebook_page_token,
    list_facebook_pages,
    make_oauth_state,
    pending_pages_key,
    refresh_instagram_token,
    state_key,
    subscribe_account_webhooks,
)
from app.services.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meta", tags=["Meta social accounts"])
FRONTEND_ERROR_CODES = {
    "access_denied": "authorization_denied",
    "configuration": "provider_not_configured",
    "provider": "provider_error",
    "invalid_state": "invalid_state",
}


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _callback_redirect(settings: Settings, **params: str) -> RedirectResponse:
    query = urlencode(params)
    return RedirectResponse(
        f"{settings.public_app_url}/dashboard/accounts?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Cache-Control": "no-store"},
    )


def _require_meta_configuration(settings: Settings, *, facebook: bool = False) -> None:
    if not all(
        (
            settings.meta_app_id,
            settings.meta_app_secret,
            settings.meta_redirect_uri,
            settings.meta_token_encryption_key.get_secret_value(),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta account connections are not configured.",
        )
    if facebook and not settings.meta_facebook_login_config_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Facebook Login for Business is not configured.",
        )


async def _load_oauth_state(request: Request, state: str) -> dict[str, Any] | None:
    try:
        payload = await request.app.state.redis_client.getdel(state_key(state))
    except RedisError as exc:
        logger.warning("meta_oauth_state_store_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta authorization is temporarily unavailable.",
        ) from exc
    if not payload:
        return None
    try:
        decoded = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    try:
        UUID(decoded["user_id"])
        UUID(decoded["organization_id"])
    except (KeyError, TypeError, ValueError):
        return None
    if decoded.get("platform") not in {"instagram", "facebook"}:
        return None
    return decoded


async def _set_oauth_state(request: Request, state: str, payload: str) -> None:
    try:
        stored = await request.app.state.redis_client.set(
            state_key(state),
            payload,
            ex=OAUTH_STATE_TTL_SECONDS,
            nx=True,
        )
    except RedisError as exc:
        logger.warning("meta_oauth_state_store_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta authorization is temporarily unavailable.",
        ) from exc
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta authorization could not be started. Please try again.",
        )


async def _authorized_organization_exists(
    session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
) -> bool:
    await set_tenant_user(session, user_id)
    membership = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if membership is None:
        logger.info("meta_oauth_membership_not_found")
        return False
    await set_tenant_organization(session, organization_id)
    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id)
    )
    return organization is not None and organization.is_active


def _social_response(account: SocialAccount) -> SocialAccountResponse:
    if not account.is_connected:
        connection_status = "disconnected"
    elif account.token_expires_at is not None and has_expired(account.token_expires_at):
        connection_status = "expired"
    else:
        connection_status = "connected"
    return SocialAccountResponse(
        id=account.id,
        platform=account.platform,
        platform_account_id=account.platform_account_id,
        account_name=account.account_name,
        created_at=account.created_at,
        token_expires_at=account.token_expires_at,
        is_connected=account.is_connected,
        connection_status=connection_status,
    )


async def _save_social_account(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: UUID,
    organization_id: UUID,
    platform: SocialPlatform,
    platform_account_id: str,
    account_name: str,
    access_token: str,
    token_expires_at: datetime | None,
) -> SocialAccount:
    if not await _authorized_organization_exists(
        session,
        user_id=user_id,
        organization_id=organization_id,
    ):
        raise PermissionError("The organization is no longer available.")
    context = account_token_context(
        organization_id,
        platform.value,
        platform_account_id,
    )
    encrypted_token = encrypt_token(settings, access_token, context=context)
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.organization_id == organization_id,
            SocialAccount.platform == platform,
            SocialAccount.platform_account_id == platform_account_id,
        )
    )
    if account is None:
        account = SocialAccount(
            organization_id=organization_id,
            platform=platform,
            platform_account_id=platform_account_id,
            account_name=account_name,
            encrypted_access_token=encrypted_token,
            token_expires_at=token_expires_at,
            is_connected=True,
        )
        session.add(account)
    else:
        account.account_name = account_name
        account.encrypted_access_token = encrypted_token
        account.token_expires_at = token_expires_at
        account.is_connected = True
        account.updated_at = datetime.now(UTC)
    await session.flush()
    await subscribe_account_webhooks(
        settings,
        platform=platform.value,
        platform_account_id=platform_account_id,
        access_token=access_token,
    )
    route = await session.scalar(
        select(MetaWebhookAccountRoute).where(
            MetaWebhookAccountRoute.organization_id == organization_id,
            MetaWebhookAccountRoute.social_account_id == account.id,
        )
    )
    if route is None:
        session.add(
            MetaWebhookAccountRoute(
                organization_id=organization_id,
                social_account_id=account.id,
                platform=platform.value,
                platform_account_id=platform_account_id,
            )
        )
    else:
        route.platform = platform.value
        route.platform_account_id = platform_account_id
    return account


@router.post(
    "/connect/{platform}",
    response_model=OAuthStartResponse,
)
async def start_connection(
    platform: SocialPlatform,
    request: Request,
    principal: Principal = Depends(get_current_principal),
) -> OAuthStartResponse:
    settings = _settings(request)
    _require_meta_configuration(settings, facebook=platform == SocialPlatform.FACEBOOK)
    await enforce_rate_limit(
        request,
        action="meta-oauth",
        limit=settings.auth_sensitive_rate_limit,
        identity=str(principal.user_id),
    )
    state, payload = make_oauth_state(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        platform=platform.value,
    )
    await _set_oauth_state(request, state, payload)
    try:
        authorization_url = build_authorization_url(
            settings,
            platform=platform.value,
            state=state,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return OAuthStartResponse(authorization_url=authorization_url)


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(
    request: Request,
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=256),
    error: str | None = Query(default=None, max_length=100),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    settings = _settings(request)
    if not state:
        return _callback_redirect(settings, oauth_error="invalid_state")
    oauth_state = await _load_oauth_state(request, state)
    if oauth_state is None:
        return _callback_redirect(settings, oauth_error="invalid_state")
    if error or not code:
        reason = "authorization_denied" if error == "access_denied" else "provider_error"
        return _callback_redirect(settings, oauth_error=reason)

    user_id = UUID(oauth_state["user_id"])
    organization_id = UUID(oauth_state["organization_id"])
    if not await _authorized_organization_exists(
        session,
        user_id=user_id,
        organization_id=organization_id,
    ):
        await session.rollback()
        return _callback_redirect(settings, oauth_error="invalid_state")

    try:
        if oauth_state["platform"] == SocialPlatform.INSTAGRAM.value:
            platform_account_id, account_name, _account_type, access_token, expires_at = (
                await connect_instagram(settings, code)
            )
            await _save_social_account(
                session,
                settings,
                user_id=user_id,
                organization_id=organization_id,
                platform=SocialPlatform.INSTAGRAM,
                platform_account_id=platform_account_id,
                account_name=account_name,
                access_token=access_token,
                token_expires_at=expires_at,
            )
            await session.commit()
            return _callback_redirect(settings, oauth_status="connected")

        pages = await list_facebook_pages(settings, code)
        flow_id = secrets.token_urlsafe(32)
        redis_pages: list[dict[str, str]] = []
        for page in pages:
            context = f"meta-pending-page:{organization_id}:{flow_id}:{page['id']}"
            redis_pages.append(
                {
                    "id": page["id"],
                    "name": page["name"],
                    "encrypted_access_token": encrypt_token(
                        settings,
                        page["access_token"],
                        context=context,
                    ),
                }
            )
        pending_payload = json.dumps(
            {
                "user_id": str(user_id),
                "organization_id": str(organization_id),
                "pages": redis_pages,
            },
            separators=(",", ":"),
        )
        stored = await request.app.state.redis_client.set(
            pending_pages_key(flow_id),
            pending_payload,
            ex=PENDING_PAGE_TTL_SECONDS,
            nx=True,
        )
        if not stored:
            raise RuntimeError("The Page selection could not be stored.")
        return _callback_redirect(
            settings,
            oauth_status="select_page",
            flow_id=flow_id,
        )
    except MetaProviderError as exc:
        logger.warning(
            "meta_oauth_provider_error",
            extra={"platform": oauth_state["platform"], "invalid_token": exc.invalid_token},
        )
        await session.rollback()
        return _callback_redirect(settings, oauth_error="provider_error")
    except (RedisError, PermissionError, RuntimeError) as exc:
        logger.warning(
            "meta_oauth_completion_failed",
            extra={"error_type": type(exc).__name__},
        )
        await session.rollback()
        return _callback_redirect(settings, oauth_error="provider_error")
@router.get("/facebook/pending/{flow_id}/pages", response_model=list[FacebookPageOption])
async def pending_facebook_pages(
    flow_id: str,
    request: Request,
    principal: Principal = Depends(get_current_principal),
) -> list[FacebookPageOption]:
    try:
        payload = await request.app.state.redis_client.get(pending_pages_key(flow_id))
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Page selection is temporarily unavailable.",
        ) from exc
    pending = _decode_pending_pages(payload)
    if not _pending_belongs_to_principal(pending, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page selection expired.")
    return [
        FacebookPageOption(
            platform_account_id=page["id"],
            account_name=page["name"],
        )
        for page in pending["pages"]
    ]


def _decode_pending_pages(payload: str | None) -> dict[str, Any] | None:
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("pages"), list) else None


def _pending_belongs_to_principal(
    pending: dict[str, Any] | None,
    principal: Principal,
) -> bool:
    return bool(
        pending
        and pending.get("user_id") == str(principal.user_id)
        and pending.get("organization_id") == str(principal.organization_id)
    )


@router.post(
    "/facebook/pending/{flow_id}/select",
    response_model=SocialAccountResponse,
)
async def select_facebook_page(
    flow_id: str,
    selection: FacebookPageSelection,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> SocialAccountResponse:
    settings = _settings(request)
    try:
        redis = request.app.state.redis_client
        key = pending_pages_key(flow_id)
        payload = await redis.get(key)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Page selection is temporarily unavailable.",
        ) from exc
    pending = _decode_pending_pages(payload)
    if not _pending_belongs_to_principal(pending, principal):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page selection expired.")
    page = next(
        (
            item
            for item in pending["pages"]
            if isinstance(item, dict) and item.get("id") == selection.platform_account_id
        ),
        None,
    )
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Authorized Page not found.")

    context = (
        f"meta-pending-page:{principal.organization_id}:{flow_id}:"
        f"{selection.platform_account_id}"
    )
    try:
        token = decrypt_token(
            settings,
            page["encrypted_access_token"],
            context=context,
        )
        token_expires_at = await inspect_facebook_page_token(settings, token)
        account = await _save_social_account(
            session,
            settings,
            user_id=principal.user_id,
            organization_id=principal.organization_id,
            platform=SocialPlatform.FACEBOOK,
            platform_account_id=selection.platform_account_id,
            account_name=page["name"],
            access_token=token,
            token_expires_at=token_expires_at,
        )
        await session.commit()
        await redis.delete(key)
    except MetaProviderError as exc:
        await session.rollback()
        if exc.invalid_token:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meta no longer accepts this Page token. Reconnect the Page.",
            ) from exc
        logger.warning("meta_facebook_page_validation_failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta could not verify the Page token. Please try again.",
        ) from exc
    except (ValueError, PermissionError, RedisError, RuntimeError) as exc:
        await session.rollback()
        logger.warning(
            "meta_facebook_page_selection_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The authorized Page could not be connected. Please try again.",
        ) from exc
    return _social_response(account)


@router.get("/accounts", response_model=list[SocialAccountResponse])
async def list_connected_accounts(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[SocialAccountResponse]:
    accounts = (
        await session.scalars(
            select(SocialAccount)
            .where(SocialAccount.organization_id == principal.organization_id)
            .order_by(SocialAccount.created_at, SocialAccount.id)
        )
    ).all()
    return [_social_response(account) for account in accounts]


@router.post("/accounts/{account_id}/refresh", response_model=SocialAccountResponse)
async def refresh_account_token(
    account_id: UUID,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> SocialAccountResponse:
    settings = _settings(request)
    _require_meta_configuration(settings)
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == account_id,
            SocialAccount.organization_id == principal.organization_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    if account.platform != SocialPlatform.INSTAGRAM or not account.is_connected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account must be reconnected through Meta.",
        )
    if account.token_expires_at is not None and has_expired(account.token_expires_at):
        account.is_connected = False
        account.encrypted_access_token = None
        account.updated_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Instagram token has expired. Reconnect the account.",
        )
    updated_at = (
        account.updated_at.replace(tzinfo=UTC)
        if account.updated_at.tzinfo is None
        else account.updated_at.astimezone(UTC)
    )
    if datetime.now(UTC) - updated_at < timedelta(hours=24):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meta permits token refresh only after the long-lived token is 24 hours old.",
        )

    context = account_token_context(
        account.organization_id,
        account.platform.value,
        account.platform_account_id,
    )
    if not account.encrypted_access_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reconnect the account to restore authorization.",
        )
    try:
        token = decrypt_token(
            settings,
            account.encrypted_access_token,
            context=context,
        )
        new_token, expires_at = await refresh_instagram_token(settings, token)
    except MetaProviderError as exc:
        if exc.invalid_token:
            account.is_connected = False
            account.encrypted_access_token = None
            account.updated_at = datetime.now(UTC)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meta no longer accepts this token. Reconnect the account.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta could not refresh the account token. Please try again.",
        ) from exc
    except ValueError as exc:
        logger.error("meta_token_decryption_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The account token could not be securely accessed.",
        ) from exc
    account.encrypted_access_token = encrypt_token(settings, new_token, context=context)
    account.token_expires_at = expires_at
    account.updated_at = datetime.now(UTC)
    await session.commit()
    return _social_response(account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(
    account_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.id == account_id,
            SocialAccount.organization_id == principal.organization_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    account.is_connected = False
    account.encrypted_access_token = None
    account.updated_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
