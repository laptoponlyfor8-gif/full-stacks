import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, get_current_principal
from app.core.config import Settings
from app.core.security import (
    access_expiry,
    create_signed_token,
    decode_signed_token,
    hash_password,
    hash_token_identifier,
    has_expired,
    new_jti,
    password_hash_needs_rehash,
    refresh_expiry,
    reset_expiry,
    verification_expiry,
    verify_password,
)
from app.db.session import get_db_session
from app.db.tenant import set_tenant_organization, set_tenant_user
from app.models import (
    AuthSession,
    AuthToken,
    AuthTokenPurpose,
    Organization,
    OrganizationMember,
    RefreshToken,
    User,
)
from app.models.enums import OrganizationRole
from app.schemas.auth import (
    AuthenticatedUser,
    EmailRequest,
    GenericMessage,
    LoginRequest,
    OrganizationSummary,
    RegisterRequest,
    RegistrationResponse,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services.email import EmailDeliveryError, get_email_provider
from app.services.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _authenticated_user(
    user: User,
    organization: Organization,
    role: OrganizationRole,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        name=user.name,
        email=user.email,
        email_verified=user.email_verified,
        organization=OrganizationSummary(
            id=organization.id,
            name=organization.name,
            slug=organization.slug,
            role=role.value,
        ),
    )


def _issue_access_token(
    settings: Settings,
    user: User,
    auth_session: AuthSession,
    organization: Organization,
    role: OrganizationRole,
) -> str:
    token, _ = create_signed_token(
        settings,
        subject=user.id,
        token_use="access",
        expires_at=access_expiry(settings),
        extra_claims={
            "sid": str(auth_session.id),
            "org_id": str(organization.id),
            "role": role.value,
            "ver": user.auth_version,
        },
    )
    return token


def _issue_refresh_token(
    settings: Settings,
    user: User,
    auth_session: AuthSession,
    organization: Organization,
    role: OrganizationRole,
) -> tuple[str, RefreshToken]:
    token_id = new_jti()
    token, _ = create_signed_token(
        settings,
        subject=user.id,
        token_use="refresh",
        token_id=token_id,
        expires_at=auth_session.expires_at,
        extra_claims={
            "sid": str(auth_session.id),
            "org_id": str(organization.id),
            "role": role.value,
            "ver": user.auth_version,
        },
    )
    db_token = RefreshToken(
        id=uuid4(),
        auth_session_id=auth_session.id,
        user_id=user.id,
        token_hash=hash_token_identifier(token_id),
        expires_at=auth_session.expires_at,
    )
    return token, db_token


def _set_auth_cookies(
    response: Response,
    settings: Settings,
    refresh_token: str,
    expires_at: datetime,
) -> None:
    csrf_token = secrets.token_urlsafe(32)
    normalized_expires_at = (
        expires_at.replace(tzinfo=UTC)
        if expires_at.tzinfo is None
        else expires_at.astimezone(UTC)
    )
    max_age = max(0, int((normalized_expires_at - datetime.now(UTC)).total_seconds()))
    cookie_options = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
    }
    response.set_cookie(
        "dm_refresh",
        refresh_token,
        max_age=max_age,
        httponly=True,
        path="/api/v1/auth",
        **cookie_options,
    )
    response.set_cookie(
        "dm_csrf",
        csrf_token,
        max_age=max_age,
        httponly=False,
        path="/",
        **cookie_options,
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    options = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
    }
    response.delete_cookie("dm_refresh", path="/api/v1/auth", **options)
    response.delete_cookie("dm_csrf", path="/", **options)


def _require_csrf(request: Request, settings: Settings) -> None:
    cookie = request.cookies.get("dm_csrf")
    supplied = request.headers.get("X-CSRF-Token")
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") not in {
        allowed.rstrip("/") for allowed in settings.cors_allowed_origins
    }:
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")
    if not cookie or not supplied or not secrets.compare_digest(cookie, supplied):
        raise HTTPException(status_code=403, detail="The CSRF check failed.")


def _make_action_token(
    settings: Settings,
    user: User,
    purpose: AuthTokenPurpose,
) -> tuple[str, AuthToken]:
    if purpose == AuthTokenPurpose.PASSWORD_RESET:
        expires_at = reset_expiry(settings)
        token_use = "password_reset"
    else:
        expires_at = verification_expiry(settings)
        token_use = "email_verification"
    token_id = new_jti()
    token, _ = create_signed_token(
        settings,
        subject=user.id,
        token_use=token_use,
        token_id=token_id,
        expires_at=expires_at,
    )
    db_token = AuthToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=hash_token_identifier(token_id),
        purpose=purpose,
        expires_at=expires_at,
    )
    return token, db_token


async def _deliver_action_email(
    request: Request,
    recipient: str,
    purpose: AuthTokenPurpose,
    token: str,
) -> bool:
    settings = _settings(request)
    provider = get_email_provider(settings)
    if provider is None:
        return False
    if purpose == AuthTokenPurpose.PASSWORD_RESET:
        link = f"{settings.public_app_url}/reset-password?token={token}"
        subject = "Reset your DM Karo password"
        body = f"Use this one-time link to reset your password. It expires soon:\n\n{link}\n"
    else:
        link = f"{settings.public_app_url}/verify-email?token={token}"
        subject = "Verify your DM Karo email"
        body = f"Use this one-time link to verify your email address:\n\n{link}\n"
    try:
        await provider.send(recipient, subject, body)
        return True
    except EmailDeliveryError as exc:
        logger.warning(
            "authentication_email_delivery_failed",
            extra={"purpose": purpose.value, "error_type": type(exc).__name__},
        )
        return False


def _new_auth_response(
    settings: Settings,
    user: User,
    auth_session: AuthSession,
    organization: Organization,
    role: OrganizationRole,
    response: Response,
    *,
    refresh_token: str | None = None,
) -> tuple[TokenResponse, RefreshToken | None]:
    refresh_record: RefreshToken | None = None
    if refresh_token is None:
        refresh_token, refresh_record = _issue_refresh_token(
            settings,
            user,
            auth_session,
            organization,
            role,
        )
    _set_auth_cookies(response, settings, refresh_token, auth_session.expires_at)
    return (
        TokenResponse(
            access_token=_issue_access_token(
                settings,
                user,
                auth_session,
                organization,
                role,
            ),
            expires_in=settings.access_token_minutes * 60,
            user=_authenticated_user(user, organization, role),
        ),
        refresh_record,
    )


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> RegistrationResponse:
    settings = _settings(request)
    await enforce_rate_limit(
        request,
        action="register",
        limit=settings.auth_sensitive_rate_limit,
        identity=str(payload.email),
    )
    email = str(payload.email).lower()
    password_hash = await hash_password(payload.password)
    try:
        async with session.begin():
            existing = await session.scalar(select(User.id).where(User.email == email))
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists.",
                )
            user = User(
                name=payload.name,
                email=email,
                password_hash=password_hash,
                mobile_number=payload.mobile_number,
            )
            session.add(user)
            await session.flush()
            await set_tenant_user(session, user.id)
            business_slug = re.sub(
                r"[^a-z0-9]+",
                "-",
                payload.business_name.lower(),
            ).strip("-") or "workspace"
            slug = f"{business_slug[:60]}-{uuid4().hex[:8]}"
            organization = Organization(
                name=payload.business_name,
                slug=slug,
                owner_user_id=user.id,
            )
            session.add(organization)
            await session.flush()
            session.add(
                OrganizationMember(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=OrganizationRole.OWNER,
                )
            )
            verification_token, db_token = _make_action_token(
                settings,
                user,
                AuthTokenPurpose.EMAIL_VERIFICATION,
            )
            session.add(db_token)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc

    sent = await _deliver_action_email(
        request,
        email,
        AuthTokenPurpose.EMAIL_VERIFICATION,
        verification_token,
    )
    return RegistrationResponse(
        id=user.id,
        email=email,
        email_verification_sent=sent,
        message=(
            "Account created. Check your email to verify your address."
            if sent
            else "Account created, but email delivery is not configured. Contact support to verify your account."
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    settings = _settings(request)
    email = str(payload.email).lower()
    await enforce_rate_limit(
        request,
        action="login",
        limit=settings.auth_login_rate_limit,
        identity=email,
    )

    async with session.begin():
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            await hash_password(payload.password)
            valid_password = False
        else:
            valid_password = await verify_password(payload.password, user.password_hash)
        if user is None or not user.is_active or not valid_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email or password is incorrect.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Verify your email address before signing in.",
                headers={"X-Auth-Error": "email_not_verified"},
            )
        if password_hash_needs_rehash(user.password_hash):
            user.password_hash = await hash_password(payload.password)

        await set_tenant_user(session, user.id)
        memberships = (
            await session.scalars(
                select(OrganizationMember)
                .where(OrganizationMember.user_id == user.id)
                .order_by(OrganizationMember.created_at, OrganizationMember.id)
            )
        ).all()
        if not memberships:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization membership is available for this account.",
            )
        membership = memberships[0]
        await set_tenant_organization(session, membership.organization_id)
        organization = await session.scalar(
            select(Organization).where(Organization.id == membership.organization_id)
        )
        if organization is None or not organization.is_active:
            raise HTTPException(status_code=403, detail="Organization access is unavailable.")

        now = datetime.now(UTC)
        session_days = settings.refresh_token_days if payload.remember_me else 1
        auth_session = AuthSession(
            id=uuid4(),
            user_id=user.id,
            expires_at=now + timedelta(days=session_days),
        )
        session.add(auth_session)
        await session.flush()
        body, refresh_record = _new_auth_response(
            settings,
            user,
            auth_session,
            organization,
            membership.role,
            response,
        )
        if refresh_record is not None:
            session.add(refresh_record)
    return body


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    settings = _settings(request)
    _require_csrf(request, settings)
    raw_token = request.cookies.get("dm_refresh")
    if not raw_token:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    claims = decode_signed_token(settings, raw_token, "refresh")
    try:
        user_id = UUID(claims["sub"])
        session_id = UUID(claims["sid"])
        organization_id = UUID(claims["org_id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="The refresh session is invalid.") from exc

    replay_detected = False
    result: TokenResponse | None = None
    async with session.begin():
        await set_tenant_user(session, user_id)
        auth_session = await session.scalar(
            select(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.user_id == user_id)
            .with_for_update()
        )
        old_record = await session.scalar(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.auth_session_id == session_id,
                RefreshToken.token_hash == hash_token_identifier(claims["jti"]),
            )
            .with_for_update()
        )
        if old_record is None or auth_session is None:
            raise HTTPException(status_code=401, detail="The refresh session is invalid.")
        if old_record.revoked_at is not None:
            auth_session.revoked_at = datetime.now(UTC)
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.auth_session_id == auth_session.id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
            replay_detected = True
        else:
            user = await session.scalar(select(User).where(User.id == user_id))
            if (
                user is None
                or not user.is_active
                or not user.email_verified
                or user.auth_version != claims.get("ver")
                or auth_session.revoked_at is not None
                or has_expired(auth_session.expires_at)
            ):
                auth_session.revoked_at = datetime.now(UTC)
                raise HTTPException(status_code=401, detail="The refresh session has expired.")

            membership = await session.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == user_id,
                )
            )
            if membership is None:
                auth_session.revoked_at = datetime.now(UTC)
                raise HTTPException(status_code=403, detail="Organization access is unavailable.")
            await set_tenant_organization(session, organization_id)
            organization = await session.scalar(
                select(Organization).where(Organization.id == organization_id)
            )
            if organization is None or not organization.is_active:
                auth_session.revoked_at = datetime.now(UTC)
                raise HTTPException(status_code=403, detail="Organization access is unavailable.")

            raw_replacement, replacement_record = _issue_refresh_token(
                settings,
                user,
                auth_session,
                organization,
                membership.role,
            )
            session.add(replacement_record)
            await session.flush()
            old_record.revoked_at = datetime.now(UTC)
            old_record.replaced_by_id = replacement_record.id
            result, _ = _new_auth_response(
                settings,
                user,
                auth_session,
                organization,
                membership.role,
                response,
                refresh_token=raw_replacement,
            )
    if replay_detected:
        raise HTTPException(status_code=401, detail="The refresh session has been revoked.")
    if result is None:
        raise HTTPException(status_code=401, detail="The refresh session is invalid.")
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    settings = _settings(request)
    _require_csrf(request, settings)
    raw_token = request.cookies.get("dm_refresh")
    if raw_token:
        try:
            claims = decode_signed_token(settings, raw_token, "refresh")
            user_id = UUID(claims["sub"])
            session_id = UUID(claims["sid"])
            async with session.begin():
                await set_tenant_user(session, user_id)
                auth_session = await session.scalar(
                    select(AuthSession).where(
                        AuthSession.id == session_id,
                        AuthSession.user_id == user_id,
                    )
                )
                if auth_session and auth_session.revoked_at is None:
                    auth_session.revoked_at = datetime.now(UTC)
                    await session.execute(
                        update(RefreshToken)
                        .where(
                            RefreshToken.auth_session_id == session_id,
                            RefreshToken.revoked_at.is_(None),
                        )
                        .values(revoked_at=datetime.now(UTC))
                    )
        except HTTPException:
            pass
    _clear_auth_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/forgot-password", response_model=GenericMessage, status_code=202)
async def forgot_password(
    payload: EmailRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessage:
    settings = _settings(request)
    await enforce_rate_limit(
        request,
        action="forgot-password",
        limit=settings.auth_sensitive_rate_limit,
        identity=str(payload.email),
    )
    token_to_send: str | None = None
    recipient: str | None = None
    async with session.begin():
        email = str(payload.email).lower()
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None and user.is_active:
            await set_tenant_user(session, user.id)
            await session.execute(
                update(AuthToken)
                .where(
                    AuthToken.user_id == user.id,
                    AuthToken.purpose == AuthTokenPurpose.PASSWORD_RESET,
                    AuthToken.consumed_at.is_(None),
                )
                .values(consumed_at=datetime.now(UTC))
            )
            token_to_send, db_token = _make_action_token(
                settings,
                user,
                AuthTokenPurpose.PASSWORD_RESET,
            )
            session.add(db_token)
            recipient = user.email
    if token_to_send and recipient:
        await _deliver_action_email(
            request,
            recipient,
            AuthTokenPurpose.PASSWORD_RESET,
            token_to_send,
        )
    return GenericMessage(
        message="If an account exists for that email, password reset instructions will be sent."
    )


@router.post("/reset-password", response_model=GenericMessage)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessage:
    settings = _settings(request)
    await enforce_rate_limit(
        request,
        action="reset-password",
        limit=settings.auth_sensitive_rate_limit,
    )
    claims = decode_signed_token(settings, payload.token, "password_reset")
    user_id = UUID(claims["sub"])
    new_hash = await hash_password(payload.password)
    async with session.begin():
        await set_tenant_user(session, user_id)
        action_token = await session.scalar(
            select(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.token_hash == hash_token_identifier(claims["jti"]),
                AuthToken.purpose == AuthTokenPurpose.PASSWORD_RESET,
            )
            .with_for_update()
        )
        if (
            action_token is None
            or action_token.consumed_at is not None
            or has_expired(action_token.expires_at)
        ):
            raise HTTPException(status_code=400, detail="The password reset link is invalid or expired.")
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None or not user.is_active:
            raise HTTPException(status_code=400, detail="The password reset link is invalid or expired.")
        user.password_hash = new_hash
        user.auth_version += 1
        action_token.consumed_at = datetime.now(UTC)
        now = datetime.now(UTC)
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.purpose == AuthTokenPurpose.PASSWORD_RESET,
                AuthToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
    return GenericMessage(message="Your password has been reset. Sign in with your new password.")


@router.post("/verify-email", response_model=GenericMessage)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessage:
    settings = _settings(request)
    await enforce_rate_limit(
        request,
        action="verify-email",
        limit=settings.auth_sensitive_rate_limit,
    )
    claims = decode_signed_token(settings, payload.token, "email_verification")
    user_id = UUID(claims["sub"])
    async with session.begin():
        await set_tenant_user(session, user_id)
        action_token = await session.scalar(
            select(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.token_hash == hash_token_identifier(claims["jti"]),
                AuthToken.purpose == AuthTokenPurpose.EMAIL_VERIFICATION,
            )
            .with_for_update()
        )
        if (
            action_token is None
            or action_token.consumed_at is not None
            or has_expired(action_token.expires_at)
        ):
            raise HTTPException(status_code=400, detail="The verification link is invalid or expired.")
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None or not user.is_active:
            raise HTTPException(status_code=400, detail="The verification link is invalid or expired.")
        user.email_verified = True
        action_token.consumed_at = datetime.now(UTC)
    return GenericMessage(message="Email address verified. You can now sign in.")


@router.post("/resend-verification", response_model=GenericMessage, status_code=202)
async def resend_verification(
    payload: EmailRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> GenericMessage:
    settings = _settings(request)
    await enforce_rate_limit(
        request,
        action="resend-verification",
        limit=settings.auth_sensitive_rate_limit,
        identity=str(payload.email),
    )
    token_to_send: str | None = None
    recipient: str | None = None
    async with session.begin():
        user = await session.scalar(
            select(User).where(
                User.email == str(payload.email).lower(),
                User.is_active.is_(True),
                User.email_verified.is_(False),
            )
        )
        if user is not None:
            await set_tenant_user(session, user.id)
            await session.execute(
                update(AuthToken)
                .where(
                    AuthToken.user_id == user.id,
                    AuthToken.purpose == AuthTokenPurpose.EMAIL_VERIFICATION,
                    AuthToken.consumed_at.is_(None),
                )
                .values(consumed_at=datetime.now(UTC))
            )
            token_to_send, db_token = _make_action_token(
                settings,
                user,
                AuthTokenPurpose.EMAIL_VERIFICATION,
            )
            session.add(db_token)
            recipient = user.email
    if token_to_send and recipient:
        await _deliver_action_email(
            request,
            recipient,
            AuthTokenPurpose.EMAIL_VERIFICATION,
            token_to_send,
        )
    return GenericMessage(
        message="If the account needs verification and email delivery is available, instructions will be sent."
    )


@router.get("/me", response_model=AuthenticatedUser)
async def get_me(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUser:
    organization = await session.scalar(
        select(Organization).where(Organization.id == principal.organization_id)
    )
    if organization is None:
        raise HTTPException(status_code=403, detail="Organization access is unavailable.")
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="The authentication session is invalid.")
    return _authenticated_user(user, organization, principal.role)


@router.get("/organizations", response_model=list[OrganizationSummary])
async def get_user_organizations(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[OrganizationSummary]:
    memberships = (
        await session.scalars(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == principal.user_id)
            .order_by(OrganizationMember.created_at, OrganizationMember.id)
        )
    ).all()
    summaries: list[OrganizationSummary] = []
    for membership in memberships:
        await set_tenant_organization(session, membership.organization_id)
        organization = await session.scalar(
            select(Organization).where(Organization.id == membership.organization_id)
        )
        if organization is not None and organization.is_active:
            summaries.append(
                OrganizationSummary(
                    id=organization.id,
                    name=organization.name,
                    slug=organization.slug,
                    role=membership.role.value,
                )
            )
    return summaries
