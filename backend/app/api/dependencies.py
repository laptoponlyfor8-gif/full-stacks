from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_signed_token, has_expired
from app.db.session import get_db_session
from app.db.tenant import set_tenant_organization, set_tenant_user
from app.models import AuthSession, Organization, OrganizationMember, User
from app.models.enums import OrganizationRole

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    session_id: UUID
    organization_id: UUID
    role: OrganizationRole
    name: str
    email: str
    email_verified: bool


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = request.app.state.settings
    claims = decode_signed_token(settings, credentials.credentials, "access")
    try:
        user_id = UUID(claims["sub"])
        session_id = UUID(claims["sid"])
        organization_id = UUID(claims["org_id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    await set_tenant_user(session, user_id)
    user = await session.scalar(select(User).where(User.id == user_id))
    auth_session = await session.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    if (
        user is None
        or not user.is_active
        or not user.email_verified
        or user.auth_version != claims.get("ver")
        or auth_session is None
        or has_expired(auth_session.expires_at)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication session is no longer valid.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    membership = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization.",
        )
    await set_tenant_organization(session, organization_id)
    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id)
    )
    if organization is None or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization.",
        )
    return Principal(
        user_id=user.id,
        session_id=session_id,
        organization_id=organization.id,
        role=membership.role,
        name=user.name,
        email=user.email,
        email_verified=user.email_verified,
    )


def require_organization_roles(*allowed_roles: OrganizationRole):
    async def dependency(
        organization_id: UUID,
        principal: Principal = Depends(get_current_principal),
        session: AsyncSession = Depends(get_db_session),
    ) -> Principal:
        membership = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == principal.user_id,
            )
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )
        if allowed_roles and membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your organization role does not allow this action.",
            )
        await set_tenant_organization(session, organization_id)
        organization = await session.scalar(
            select(Organization).where(Organization.id == organization_id)
        )
        if organization is None or not organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )
        return Principal(
            user_id=principal.user_id,
            session_id=principal.session_id,
            organization_id=organization_id,
            role=membership.role,
            name=principal.name,
            email=principal.email,
            email_verified=principal.email_verified,
        )

    return dependency
